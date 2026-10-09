import copy
import json
import sqlite3

import pytest

from healthhub.cli import main
from healthhub.store import import_file, summary
from healthhub.validation import ValidationError, validate


def envelope():
    return {
        "schema_version": "1.0",
        "source": "mi_fitness_data_bridge",
        "records": {
            "daily_activity": [
                {
                    "id": "synthetic-a",
                    "user_id": "synthetic-user",
                    "date": "2026-10-01",
                    "steps": 8000,
                    "distance_m": 5200,
                    "active_kcal": 300,
                }
            ],
            "sleep": [
                {
                    "id": "synthetic-s",
                    "user_id": "synthetic-user",
                    "start_at": "2026-10-01T23:00:00",
                    "end_at": "2026-10-02T07:00:00",
                    "sleep_score": None,
                    "duration_minutes": 480,
                }
            ],
            "heart_rate": [
                {
                    "id": "synthetic-h",
                    "user_id": "synthetic-user",
                    "timestamp": "2026-10-01T23:30:00Z",
                    "bpm": 70,
                }
            ],
            "spo2": [],
        },
    }


@pytest.fixture
def files(tmp_path):
    source = tmp_path / "合成.json"
    source.write_text(json.dumps(envelope()), encoding="utf-8")
    return source, tmp_path / "健康.db"


def rewrite(source, change):
    payload = envelope()
    change(payload)
    source.write_text(json.dumps(payload), encoding="utf-8")


def test_import_replay_update_and_integrity(files):
    source, db = files
    assert import_file(source, db)["inserted"] == 3
    assert import_file(source, db)["unchanged"] == 3
    rewrite(source, lambda p: p["records"]["daily_activity"][0].update(steps=8100))
    result = import_file(source, db)
    assert (result["inserted"], result["updated"], result["unchanged"]) == (0, 1, 2)
    state = summary(db)
    assert state["integrity"] == "ok"
    assert state["total_rows"] == 3
    assert state["coverage"]["heart_rate"]["first_date"] == "2026-10-02"
    assert state["coverage"]["sleep"]["first_date"] == "2026-10-01"
    assert state["latest_import_datasets"]["spo2"] == 0
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM import_runs").fetchone()[0] == 3
        stored = " ".join(r[0] for r in conn.execute("SELECT payload_json FROM records"))
    assert "user_id" not in stored
    assert "synthetic-user" not in stored
    assert '"sleep_score": null' in stored


@pytest.mark.parametrize(
    "metric,value",
    [
        ("steps", -1),
        ("steps", 0.5),
        ("steps", True),
        ("distance_m", "bad"),
        ("active_kcal", float("nan")),
        ("active_kcal", float("inf")),
    ],
)
def test_invalid_metrics_rejected(files, metric, value):
    source, db = files
    rewrite(source, lambda p: p["records"]["daily_activity"][0].update({metric: value}))
    with pytest.raises(ValidationError):
        import_file(source, db)
    assert not db.exists()


@pytest.mark.parametrize(
    "key",
    [
        "passToken",
        "pass_token",
        "PASSWORD",
        "Authorization",
        "api-key",
        "access_token",
        "cookie",
        "ssecurity",
    ],
)
def test_credentials_rejected_without_echo(files, key):
    source, db = files
    rewrite(source, lambda p: p.update(extra={"nested": [{key: "synthetic-secret-never-echo"}]}))
    with pytest.raises(ValidationError) as error:
        import_file(source, db)
    assert "synthetic-secret-never-echo" not in str(error.value)
    assert not db.exists()


def test_credential_inside_serialized_json_rejected(files):
    source, db = files
    rewrite(
        source,
        lambda p: p["records"]["sleep"][0].update(stages='[{"passToken":"synthetic-secret"}]'),
    )
    with pytest.raises(ValidationError):
        import_file(source, db)
    assert not db.exists()


@pytest.mark.parametrize("value", ["2026-02-30", "20261001", None, "arbitrary-private-text"])
def test_date_errors_do_not_echo_input(files, value):
    source, db = files
    rewrite(source, lambda p: p["records"]["daily_activity"][0].update(date=value))
    with pytest.raises(ValidationError) as error:
        import_file(source, db)
    assert "arbitrary-private-text" not in str(error.value)


def test_bad_later_row_leaves_existing_database_unchanged(files):
    source, db = files
    import_file(source, db)

    def change(p):
        p["records"]["daily_activity"][0]["steps"] = 9999
        p["records"]["heart_rate"][0]["bpm"] = -1

    rewrite(source, change)
    with pytest.raises(ValidationError):
        import_file(source, db)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM import_runs").fetchone()[0] == 1
        activity = json.loads(
            conn.execute(
                "SELECT payload_json FROM records WHERE dataset='daily_activity'"
            ).fetchone()[0]
        )
    assert activity["steps"] == 8000


def test_subject_account_binding_rolls_back(files):
    source, db = files
    import_file(source, db)

    def change(p):
        for rows in p["records"].values():
            for row in rows:
                row["user_id"] = "synthetic-other-account"

    rewrite(source, change)
    with pytest.raises(ValidationError, match="different account"):
        import_file(source, db)
    assert summary(db)["total_rows"] == 3
    assert import_file(source, db, subject="second-local-subject")["inserted"] == 3


def test_mixed_accounts_rejected(files):
    source, db = files
    rewrite(source, lambda p: p["records"]["sleep"][0].update(user_id="synthetic-other-account"))
    with pytest.raises(ValidationError, match="Multiple accounts"):
        import_file(source, db)
    assert not db.exists()


def test_duplicate_id_rejected():
    payload = envelope()
    payload["records"]["sleep"].append(copy.deepcopy(payload["records"]["sleep"][0]))
    with pytest.raises(ValidationError, match="Duplicate record"):
        validate(payload)


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.update(schema_version="2.0"),
        lambda p: p.update(source="other-source"),
        lambda p: p["records"].update(unknown=[]),
        lambda p: p["records"]["sleep"][0].update(end_at="2026-09-30T10:00:00"),
        lambda p: p["records"]["sleep"][0].update(sleep_score=101),
        lambda p: p["records"]["heart_rate"][0].update(timestamp="2026-10-01"),
        lambda p: p["records"]["daily_activity"][0].pop("id"),
    ],
)
def test_schema_guards(change):
    payload = envelope()
    change(payload)
    with pytest.raises(ValidationError):
        validate(payload)


def test_offset_change_refused(files):
    source, db = files
    import_file(source, db)
    with pytest.raises(ValidationError, match="UTC offset differs"):
        import_file(source, db, utc_offset="+00:00")


def test_unrelated_database_not_modified(files):
    source, db = files
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE original (value TEXT)")
    with pytest.raises(ValidationError, match="unrelated database"):
        import_file(source, db)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [
            ("original",)
        ]


def test_empty_and_missing_datasets_distinguished(files):
    source, db = files
    source.write_text(
        json.dumps(
            {"schema_version": "1.0", "source": "mi_fitness_data_bridge", "records": {"sleep": []}}
        ),
        encoding="utf-8",
    )
    assert import_file(source, db)["inserted"] == 0
    state = summary(db)
    assert state["latest_import_datasets"] == {"sleep": 0}
    assert state["live_device_compatibility"] == "not_verified"


def test_additive_columns_preserved(files):
    source, db = files
    rewrite(source, lambda p: p["records"]["daily_activity"][0].update(new_metric=None))
    import_file(source, db)
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT payload_json FROM records WHERE dataset='daily_activity'"
        ).fetchone()[0]
    assert '"new_metric": null' in row


def test_cli_and_local_sync(files, capsys):
    source, db = files
    assert main(["validate", str(source)]) == 0
    assert main(["sync", "--db", str(db), "--inbox", str(source.parent)]) == 0
    assert main(["sync", "--db", str(db), "--inbox", str(source.parent)]) == 0
    assert main(["summary", "--db", str(db)]) == 0
    output = capsys.readouterr().out
    assert '"unchanged": 3' in output
    assert '"total_rows": 3' in output
    assert "synthetic-user" not in output
    assert '"steps"' not in output


def test_invalid_json_and_duplicate_keys_safe(files, capsys):
    source, db = files
    for text in [
        '{"private":"synthetic-secret",',
        '{"schema_version":"1.0","schema_version":"2.0"}',
    ]:
        source.write_text(text, encoding="utf-8")
        assert main(["import", str(source), "--db", str(db)]) == 1
    assert "synthetic-secret" not in capsys.readouterr().out


def test_missing_summary_does_not_create_file(tmp_path):
    db = tmp_path / "missing.db"
    with pytest.raises(ValidationError):
        summary(db)
    assert not db.exists()


@pytest.mark.parametrize("offset", ["Asia/Shanghai", "+14:01", "+08:99", "+99:00"])
def test_invalid_offset(offset):
    with pytest.raises(ValidationError):
        validate(envelope(), offset)
