"""Transactional import, provenance, and count-only local coverage."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from .validation import DATASETS, ValidationError, parse_offset, read_export, validate

SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS subjects (subject TEXT PRIMARY KEY, account_hmac TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS records (
    subject TEXT NOT NULL, dataset TEXT NOT NULL, record_key TEXT NOT NULL,
    observed_at TEXT NOT NULL, local_date TEXT NOT NULL, payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL, first_imported_at TEXT NOT NULL, last_imported_at TEXT NOT NULL,
    PRIMARY KEY(subject, dataset, record_key));
CREATE INDEX IF NOT EXISTS records_coverage ON records(subject, dataset, local_date);
CREATE TABLE IF NOT EXISTS import_runs (
    id INTEGER PRIMARY KEY, imported_at TEXT NOT NULL, subject TEXT NOT NULL,
    source_sha256 TEXT NOT NULL, source_schema TEXT NOT NULL,
    inserted INTEGER NOT NULL, updated INTEGER NOT NULL, unchanged INTEGER NOT NULL,
    dataset_counts_json TEXT NOT NULL);
"""


def import_file(
    path: Path, db_path: Path, subject: str = "band9-local", utc_offset: str = "+08:00"
) -> dict:
    raw, payload = read_export(path)
    rows = validate(payload, utc_offset)
    return import_rows(
        rows, db_path, subject, utc_offset, hashlib.sha256(raw).hexdigest(), "1.0",
        {name: len(items) for name, items in payload["records"].items()},
    )


def import_rows(
    rows: list[dict], db_path: Path, subject: str, utc_offset: str,
    source_sha256: str, source_schema: str, dataset_counts: dict,
) -> dict:
    """Persist fully validated adapter rows with the shared transactional audit."""
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", subject):
        raise ValidationError("Subject must be a short local alias")
    parse_offset(utc_offset)
    if len({row["account"] for row in rows}) > 1:
        raise ValidationError("Multiple accounts in one import")
    identities = [(row["dataset"], row["id"]) for row in rows]
    if len(identities) != len(set(identities)):
        raise ValidationError("Duplicate record identities in one import")
    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    now = datetime.now(UTC).isoformat()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path, timeout=30)) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            raise ValidationError("Unsupported local database schema version")
        if (
            version == 0
            and conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()
        ):
            raise ValidationError(
                "Destination is an unrelated database; select a separate hub database"
            )
        conn.executescript(SCHEMA)
        conn.execute("PRAGMA user_version=1")
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT OR IGNORE INTO metadata VALUES('account_salt', ?)", (secrets.token_hex(32),)
            )
            salt = bytes.fromhex(
                conn.execute("SELECT value FROM metadata WHERE key='account_salt'").fetchone()[0]
            )
            conn.execute("INSERT OR IGNORE INTO metadata VALUES('utc_offset', ?)", (utc_offset,))
            if (
                conn.execute("SELECT value FROM metadata WHERE key='utc_offset'").fetchone()[0]
                != utc_offset
            ):
                raise ValidationError("UTC offset differs from database; use a separate database")
            if rows:
                account_hmac = hmac.new(
                    salt, rows[0]["account"].encode("utf-8"), hashlib.sha256
                ).hexdigest()
                bound = conn.execute(
                    "SELECT account_hmac FROM subjects WHERE subject=?", (subject,)
                ).fetchone()
                if bound and bound[0] != account_hmac:
                    raise ValidationError("Local subject is bound to a different account")
                conn.execute("INSERT OR IGNORE INTO subjects VALUES(?, ?)", (subject, account_hmac))
            for row in rows:
                record_key = hashlib.sha256(row["id"].encode("utf-8")).hexdigest()
                text = json.dumps(
                    row["payload"], ensure_ascii=False, sort_keys=True, allow_nan=False
                )
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                previous = conn.execute(
                    "SELECT payload_sha256 FROM records WHERE subject=? AND dataset=? AND record_key=?",
                    (subject, row["dataset"], record_key),
                ).fetchone()
                if previous and previous[0] == digest:
                    counts["unchanged"] += 1
                    continue
                counts["updated" if previous else "inserted"] += 1
                conn.execute(
                    """INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(subject,dataset,record_key) DO UPDATE SET
                    observed_at=excluded.observed_at, local_date=excluded.local_date,
                    payload_json=excluded.payload_json, payload_sha256=excluded.payload_sha256,
                    last_imported_at=excluded.last_imported_at""",
                    (
                        subject,
                        row["dataset"],
                        record_key,
                        row["observed_at"],
                        row["local_date"],
                        text,
                        digest,
                        now,
                        now,
                    ),
                )
            conn.execute(
                """INSERT INTO import_runs
                (imported_at, subject, source_sha256, source_schema, inserted, updated,
                 unchanged, dataset_counts_json) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    now,
                    subject,
                    source_sha256,
                    source_schema,
                    counts["inserted"],
                    counts["updated"],
                    counts["unchanged"],
                    json.dumps(dataset_counts, sort_keys=True),
                ),
            )
    return {**counts, "datasets": dataset_counts}


def summary(db_path: Path, subject: str = "band9-local") -> dict:
    if not db_path.is_file():
        raise ValidationError("Local hub database does not exist; import first")
    with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        if conn.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ValidationError("Unsupported local database schema version")
        coverage = {name: {"rows": 0, "first_date": None, "last_date": None} for name in DATASETS}
        for name, count, first, last in conn.execute(
            "SELECT dataset, COUNT(*), MIN(local_date), MAX(local_date) FROM records WHERE subject=? GROUP BY dataset",
            (subject,),
        ):
            coverage[name] = {"rows": count, "first_date": first, "last_date": last}
        latest = conn.execute(
            "SELECT dataset_counts_json FROM import_runs WHERE subject=? ORDER BY id DESC LIMIT 1",
            (subject,),
        ).fetchone()
        latest_counts = json.loads(latest[0]) if latest else {}
        return {
            "integrity": conn.execute("PRAGMA quick_check").fetchone()[0],
            "total_rows": sum(item["rows"] for item in coverage.values()),
            "coverage": coverage,
            "latest_import_datasets": latest_counts,
            "live_device_compatibility": "not_verified",
        }
