"""Offline official Zepp Life CSV adapter; never read the USER profile."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from datetime import date, datetime
from pathlib import Path

from .store import import_rows
from .validation import ValidationError, parse_offset

HEADERS = {
    "ACTIVITY": "date,steps,distance,runDistance,calories",
    "SLEEP": "date,deepSleepTime,shallowSleepTime,wakeTime,start,stop,REMTime,naps",
    "SPORT": (
        "type,startTime,sportTime(s),maxPace(/meter),minPace(/meter),"
        "distance(m),avgPace(/meter),calories(kcal)"
    ),
    "HEARTRATE": "time,heartRate",
    "BODY": (
        "time,weight,height,bmi,fatRate,bodyWaterRate,boneMass,metabolism,"
        "muscleRate,visceralFat"
    ),
    "ACTIVITY_MINUTE": "date,time,steps",
    "ACTIVITY_STAGE": "date,start,stop,distance,calories,steps",
    "HEALTH_DATA": "date,time,arm,calf,chest,hip,thigh,waist",
    "HEARTRATE_AUTO": "date,time,heartRate",
    "SLEEP_MINUTE": "date,time,stage,hr,respiratory_rate",
}
SUPPORTED = {"ACTIVITY", "SLEEP", "SPORT", "HEARTRATE", "BODY"}


def number(value: str, *, required: bool = False) -> float | None:
    if value in ("", "null") and not required:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Invalid CSV number") from exc
    if not math.isfinite(result) or result < 0:
        raise ValidationError("CSV number must be finite and nonnegative")
    return result


def timestamp(value: str, offset) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Invalid CSV timestamp") from exc
    if result.tzinfo is None:
        raise ValidationError("Zepp timestamp requires an explicit UTC offset")
    return result.astimezone(offset)


def normalize(dataset: str, raw: dict, offset) -> tuple[str, str, str, dict, list]:
    flags: list[str] = []
    normalized = {}
    if dataset in {"ACTIVITY", "SLEEP"}:
        try:
            day = date.fromisoformat(raw["date"]).isoformat()
        except ValueError as exc:
            raise ValidationError("Invalid CSV date") from exc
        key, observed = day, day
        if dataset == "ACTIVITY":
            steps = number(raw["steps"])
            if steps is not None and not steps.is_integer():
                raise ValidationError("Steps must be an integer")
            normalized = {"steps": int(steps) if steps is not None else None}
            for field in ("distance", "runDistance", "calories"):
                number(raw[field])  # Units/meaning are unverified: preserve raw only.
        else:
            start, stop = (timestamp(raw[field], offset) for field in ("start", "stop"))
            minutes = {field: number(raw[field]) for field in (
                "deepSleepTime", "shallowSleepTime", "wakeTime", "REMTime"
            )}
            span = (stop - start).total_seconds() / 60
            observed = start.isoformat()
            normalized = {
                "start_at": start.isoformat(), "end_at": stop.isoformat(),
                "deep_minutes": minutes["deepSleepTime"],
                "light_minutes": minutes["shallowSleepTime"],
                "awake_minutes": minutes["wakeTime"], "rem_minutes": minutes["REMTime"],
                "time_asleep_minutes": None, "valid_main_sleep": False,
            }
            if span <= 0:
                flags.append("nonpositive_session")
            elif span > 24 * 60:
                flags.append("session_exceeds_24h")
            if any(minutes[field] is None for field in (
                "deepSleepTime", "shallowSleepTime", "wakeTime"
            )):
                flags.append("missing_required_stage_duration")
            elif span > 0:
                # A blank REM remains unknown. A zero contribution is used only
                # for this consistency check; duration itself comes from time.
                stage_sum = sum(value or 0 for value in minutes.values())
                if abs(span - stage_sum) > 1:
                    flags.append("stage_span_mismatch")
                asleep = span - minutes["wakeTime"]
                if asleep <= 0:
                    flags.append("nonpositive_asleep_duration")
                if not flags:
                    normalized["time_asleep_minutes"] = asleep
                    normalized["valid_main_sleep"] = True
            if minutes["REMTime"] is None:
                flags.append("rem_unknown")
            normalized["naps"] = []
            if raw["naps"]:
                try:
                    naps = json.loads(raw["naps"])
                    if not isinstance(naps, list):
                        raise ValueError
                    for nap in naps:
                        if not isinstance(nap, dict) or set(nap) != {"start", "end"}:
                            raise ValueError
                        begin, end = (timestamp(nap[field], offset) for field in ("start", "end"))
                        duration = (end - begin).total_seconds() / 60
                        if not 0 < duration <= 24 * 60:
                            raise ValueError
                        normalized["naps"].append({"start_at": begin.isoformat(),
                                                   "end_at": end.isoformat(),
                                                   "duration_minutes": duration})
                    flags.append("naps_excluded_from_main_sleep")
                except (ValueError, TypeError, KeyError, ValidationError):
                    normalized["naps"] = []
                    flags.append("naps_unparsed_excluded_from_main_sleep")
            if stop.date().isoformat() != day:
                flags.append("source_date_differs_from_local_stop")
    else:
        time_field = "startTime" if dataset == "SPORT" else "time"
        dt = timestamp(raw[time_field], offset)
        day, observed = dt.date().isoformat(), dt.isoformat()
        key = observed
        if dataset == "SPORT":
            if not re.fullmatch(r"\d+", raw["type"]):
                raise ValidationError("Invalid sport type code")
            key = raw["type"] + ":" + observed
            duration = number(raw["sportTime(s)"], required=True)
            distance = number(raw["distance(m)"], required=True)
            calories = number(raw["calories(kcal)"])
            for field in ("maxPace(/meter)", "minPace(/meter)", "avgPace(/meter)"):
                number(raw[field])
            normalized = {
                "start_at": observed, "type_code": raw["type"],
                "duration_seconds": duration, "distance_m": distance,
                "calories_kcal": calories,
                "derived_pace_sec_per_km": duration / distance * 1000 if distance else None,
            }
            flags.append("sport_type_mapping_unverified")
        else:
            for field, value in raw.items():
                if field != "time":
                    number(value)
    return key, observed, day, normalized, flags


def read_zepp(folder: Path, utc_offset: str = "+08:00") -> dict:
    """Validate the entire export before any database write. No paths in audit."""
    offset = parse_offset(utc_offset)
    if not folder.is_dir() or folder.is_symlink():
        raise ValidationError("Zepp export directory does not exist or is a symlink")
    match = re.fullmatch(r"(\d+)_(\d+)", folder.name)
    if not match:
        raise ValidationError("Keep the official numeric export directory name for account binding")
    account = "zepp-life:" + match[1]
    rows, files, identities = [], [], set()
    source_hash = hashlib.sha256()
    for child in sorted(folder.iterdir()):
        if child.name == "USER":
            continue  # Do not open, hash, copy, or ingest the account/profile file.
        if child.is_symlink() or not child.is_dir() or child.name not in HEADERS:
            raise ValidationError("Unexpected export entry; schema review required")
        csv_files = list(child.iterdir())
        if len(csv_files) != 1 or csv_files[0].suffix.lower() != ".csv":
            raise ValidationError("Expected exactly one CSV in each dataset directory")
        path = csv_files[0]
        if path.is_symlink() or not path.is_file():
            raise ValidationError("Invalid CSV file")
        blob = path.read_bytes()
        try:
            reader = csv.DictReader(io.StringIO(blob.decode("utf-8-sig"), newline=""),
                                    strict=True, escapechar="\\")
            if reader.fieldnames != HEADERS[child.name].split(","):
                raise ValidationError("Unexpected CSV columns; schema review required")
            records = list(reader)
        except (UnicodeError, csv.Error) as exc:
            raise ValidationError("CSV decoding or syntax failed") from exc
        if any(None in row or None in row.values() for row in records):
            raise ValidationError("CSV row width differs from header")
        if records and child.name not in SUPPORTED:
            raise ValidationError("Nonempty detailed dataset requires an additional adapter")
        source_hash.update(child.name.encode() + b"\0" + blob)
        files.append({
            "dataset": child.name, "rows": len(records),
            "sha256": hashlib.sha256(blob).hexdigest(),
        })
        for raw in records:
            key, observed, day, normalized, flags = normalize(child.name, raw, offset)
            identity = (child.name, key)
            if identity in identities:
                raise ValidationError("Duplicate identities in Zepp export")
            identities.add(identity)
            rows.append({
                "id": key, "account": account, "dataset": "zepp_" + child.name.lower(),
                "observed_at": observed, "local_date": day,
                "payload": {
                    "source": "zepp_life_official_csv", "raw": raw,
                    "normalized": normalized, "quality_flags": flags,
                },
            })
    if not {"SLEEP", "ACTIVITY"}.issubset({file["dataset"] for file in files}):
        raise ValidationError("Export must include SLEEP and ACTIVITY datasets")
    return {"rows": rows, "files": files, "source_sha256": source_hash.hexdigest()}


def import_zepp(
    folder: Path, db_path: Path, subject: str = "zepp-life", utc_offset: str = "+08:00"
) -> dict:
    export = read_zepp(folder, utc_offset)
    result = import_rows(
        export["rows"], db_path, subject, utc_offset, export["source_sha256"],
        "zepp-life-csv-v1", {"zepp_" + file["dataset"].lower(): file["rows"]
                             for file in export["files"]},
    )
    return {**result, "source_sha256": export["source_sha256"], "files": export["files"]}
