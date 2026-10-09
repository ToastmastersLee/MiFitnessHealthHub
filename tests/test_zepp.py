"""Synthetic CSV fixtures only; network is disabled by conftest."""

import csv
import json
import sqlite3

import pytest

from healthhub.validation import ValidationError
from healthhub.zepp import HEADERS, import_zepp, read_zepp
from healthhub.zepp_report import analyze, write_report


def sleep(day="2020-01-02", **changes):
    return {"date": day, "deepSleepTime": "60", "shallowSleepTime": "360",
            "wakeTime": "30", "start": "2020-01-01 15:00:00+0000",
            "stop": "2020-01-01 22:30:00+0000", "REMTime": "", "naps": "", **changes}


def sport(**changes):
    return {"type": "123", "startTime": "2020-01-01 23:30:00+0000",
            "sportTime(s)": "1500", "distance(m)": "5000", "calories(kcal)": "300",
            "maxPace(/meter)": "0.2", "minPace(/meter)": "0.4",
            "avgPace(/meter)": "0.3", **changes}


def export(tmp_path, records=None):
    root = tmp_path / "123456_987654"
    root.mkdir()
    for dataset, columns in HEADERS.items():
        directory = root / dataset
        directory.mkdir()
        with (directory / "synthetic.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, columns.split(","), escapechar="\\", doublequote=False)
            writer.writeheader()
            writer.writerows((records or {}).get(dataset, []))
    (root / "USER").mkdir()
    (root / "USER" / "profile.csv").write_bytes(b"\xffdo not read me")
    return root


def test_real_dialect_naps_unknown_rem_and_local_dates(tmp_path):
    naps = json.dumps([{"start": "2020-01-02 04:00:00+0000",
                        "end": "2020-01-02 04:30:00+0000"}])
    folder = export(tmp_path, {"SLEEP": [sleep(naps=naps)], "SPORT": [sport()]})
    parsed = read_zepp(folder)
    by_name = {r["dataset"]: r for r in parsed["rows"]}
    s = by_name["zepp_sleep"]
    assert s["payload"]["raw"]["naps"] == naps
    assert s["payload"]["normalized"]["rem_minutes"] is None
    assert s["payload"]["normalized"]["time_asleep_minutes"] == 420
    assert s["payload"]["normalized"]["naps"][0]["duration_minutes"] == 30
    w = by_name["zepp_sport"]
    assert w["local_date"] == "2020-01-02"
    assert w["payload"]["normalized"]["type_code"] == "123"
    assert w["payload"]["normalized"]["derived_pace_sec_per_km"] == 300
    assert "USER" not in {f["dataset"] for f in parsed["files"]}


@pytest.mark.parametrize("changes,flag", [
    ({"stop": "2020-01-01 15:00:00+0000"}, "nonpositive_session"),
    ({"stop": "2020-01-03 15:00:00+0000"}, "session_exceeds_24h"),
    ({"deepSleepTime": ""}, "missing_required_stage_duration"),
    ({"shallowSleepTime": "300"}, "stage_span_mismatch"),
])
def test_invalid_sleep_preserved_but_excluded(tmp_path, changes, flag):
    folder = export(tmp_path, {"SLEEP": [sleep(**changes)]})
    row = read_zepp(folder)["rows"][0]["payload"]
    assert not row["normalized"]["valid_main_sleep"]
    assert row["normalized"]["time_asleep_minutes"] is None
    assert flag in row["quality_flags"]


def test_idempotence_update_account_binding_and_source_immutable(tmp_path):
    folder = export(tmp_path, {"SLEEP": [sleep()], "SPORT": [sport()]})
    before = read_zepp(folder)["source_sha256"]
    db = tmp_path / "data" / "hub.db"
    assert import_zepp(folder, db)["inserted"] == 2
    assert import_zepp(folder, db)["unchanged"] == 2
    assert read_zepp(folder)["source_sha256"] == before
    path = folder / "SPORT" / "synthetic.csv"
    path.write_text(path.read_text().replace(",5000,", ",6000,"))
    assert import_zepp(folder, db)["updated"] == 1
    renamed = folder.with_name("999999_987654")
    folder.rename(renamed)
    with pytest.raises(ValidationError, match="different account"):
        import_zepp(renamed, db)
    assert analyze(db)["coverage"]["zepp_sport"]["rows"] == 1


@pytest.mark.parametrize("value", ["nan", "inf", "-1", "bad"])
def test_bad_export_does_not_write_database(tmp_path, value):
    folder = export(tmp_path, {"SLEEP": [sleep()], "SPORT": [sport(**{"distance(m)": value})]})
    db = tmp_path / "data" / "hub.db"
    with pytest.raises(ValidationError):
        import_zepp(folder, db)
    assert not db.exists()


def test_duplicate_primary_key_rejected(tmp_path):
    folder = export(tmp_path, {"SLEEP": [sleep(), sleep()]})
    with pytest.raises(ValidationError, match="Duplicate"):
        read_zepp(folder)


def test_detailed_nonempty_schema_must_be_reviewed(tmp_path):
    folder = export(tmp_path, {"SLEEP_MINUTE": [{"date": "2020-01-01", "time": "00:00",
                                               "stage": "1", "hr": "60", "respiratory_rate": "12"}]})
    with pytest.raises(ValidationError, match="additional adapter"):
        read_zepp(folder)


def test_body_nulls_and_malformed_naps_preserved(tmp_path):
    body = {name: "null" for name in HEADERS["BODY"].split(",")}
    body["time"] = "2020-01-01 01:00:00+0000"
    folder = export(tmp_path, {"SLEEP": [sleep(naps="unparsed")], "BODY": [body]})
    rows = read_zepp(folder)["rows"]
    assert len(rows) == 2
    s = next(r for r in rows if r["dataset"] == "zepp_sleep")
    assert s["payload"]["normalized"]["valid_main_sleep"]
    assert "naps_unparsed_excluded_from_main_sleep" in s["payload"]["quality_flags"]


def test_report_metrics_missing_days_and_private_output(tmp_path):
    folder = export(tmp_path, {"SLEEP": [sleep(), sleep("2020-01-04",
                                    stop="2020-01-01 15:00:00+0000")], "SPORT": [sport()]})
    db = tmp_path / "data" / "hub.db"
    import_zepp(folder, db)
    report = analyze(db)
    year = report["annual"][0]
    assert year["window_days"] == 3
    assert year["valid_sleep_days"] == 1
    assert year["invalid_sleep_days"] == 1
    assert year["missing_sleep_days"] == 1
    assert year["mean_sleep_hours"] == 7
    assert year["workout_distance_km"] == 5
    with pytest.raises(ValidationError, match="private"):
        write_report(db, tmp_path / "public")
    output = tmp_path / "private" / "report"
    assert write_report(db, output)["integrity"] == "ok"
    text = (output / "history.html").read_text(encoding="utf-8")
    assert "__DATA__" not in text and "123456" not in text
    assert '<script src=' not in text and 'fetch(' not in text
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 3


def test_extra_columns_and_bad_csv_width_rejected(tmp_path):
    folder = export(tmp_path)
    path = folder / "ACTIVITY" / "synthetic.csv"
    path.write_text("date,steps,distance,runDistance,calories,extra\n")
    with pytest.raises(ValidationError, match="columns"):
        read_zepp(folder)
    path.write_text(HEADERS["ACTIVITY"] + "\n2020-01-01,1\n")
    with pytest.raises(ValidationError, match="width"):
        read_zepp(folder)
