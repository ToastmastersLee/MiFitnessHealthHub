import json

import pytest

from healthhub.store import import_file, summary
from healthhub.validation import ValidationError


def all_datasets():
    base = {
        "user_id": "synthetic-all-datasets",
        "provider": "mi_fitness",
        "source_type": "cloud_session",
    }
    datasets = {
        "daily_activity": {"date": "2026-10-01", "steps": 0},
        "sleep": {
            "start_at": "2026-10-01T23:00:00+08:00",
            "end_at": "2026-10-02T07:00:00+08:00",
            "sleep_score": None,
        },
        "workouts": {
            "start_at": "2026-10-01T18:00:00+08:00",
            "end_at": "2026-10-01T18:30:00+08:00",
            "activity_type": "walking",
        },
        "workout_detail": {
            "timestamp": "2026-10-01T18:01:00+08:00",
            "offset_seconds": 60,
            "heart_rate_bpm": 100,
        },
        "workout_gps": {
            "timestamp": "2026-10-01T18:01:00+08:00",
            "offset_seconds": 60,
            "latitude": 0,
            "longitude": 0,
        },
        "body_measurements": {"timestamp": "2026-10-01T08:00:00+08:00", "weight_kg": 70},
        "heart_rate": {"timestamp": "2026-10-01T08:00:00+08:00", "bpm": 70},
        "spo2": {"timestamp": "2026-10-01T08:00:00+08:00", "spo2_pct": 98},
        "stress": {"timestamp": "2026-10-01T08:00:00+08:00", "stress_score": 20},
        "abnormal_heart_beat": {
            "start_at": "2026-10-01T08:00:00+08:00",
            "end_at": "2026-10-01T08:00:10+08:00",
            "duration_seconds": 10,
        },
    }
    return {
        "schema_version": "1.0",
        "source": "mi_fitness_data_bridge",
        "records": {
            name: [{**base, "id": f"synthetic-{name}", **row}] for name, row in datasets.items()
        },
    }


def test_all_ten_datasets(tmp_path):
    source, db = tmp_path / "synthetic.json", tmp_path / "synthetic.db"
    source.write_text(json.dumps(all_datasets()), encoding="utf-8")
    assert import_file(source, db)["inserted"] == 10
    assert import_file(source, db)["unchanged"] == 10
    state = summary(db)
    assert len(state["coverage"]) == 10
    assert all(row["rows"] == 1 for row in state["coverage"].values())


@pytest.mark.parametrize(
    "dataset,metric,value",
    [
        ("spo2", "spo2_pct", 101),
        ("stress", "stress_score", -1),
        ("workout_gps", "latitude", 91),
        ("workout_gps", "longitude", -181),
        ("body_measurements", "weight_kg", -1),
        ("heart_rate", "bpm", None),
    ],
)
def test_dataset_specific_errors(tmp_path, dataset, metric, value):
    payload = all_datasets()
    payload["records"][dataset][0][metric] = value
    source, db = tmp_path / "synthetic.json", tmp_path / "synthetic.db"
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValidationError):
        import_file(source, db)
    assert not db.exists()
