"""Validate bridge JSON without reporting personal values in exceptions."""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DATASETS = {
    "daily_activity": "date",
    "sleep": "start_at",
    "workouts": "start_at",
    "workout_detail": "timestamp",
    "workout_gps": "timestamp",
    "body_measurements": "timestamp",
    "heart_rate": "timestamp",
    "spo2": "timestamp",
    "stress": "timestamp",
    "abnormal_heart_beat": "start_at",
}
FORBIDDEN = {
    "passtoken",
    "token",
    "password",
    "secret",
    "authorization",
    "cookie",
    "cookies",
    "accesstoken",
    "refreshtoken",
    "apikey",
    "servicetoken",
    "ssecurity",
}
NONNEGATIVE = {
    "steps",
    "total_steps",
    "distance_m",
    "active_kcal",
    "total_kcal",
    "floors",
    "active_minutes",
    "duration_minutes",
    "duration_seconds",
    "time_asleep_minutes",
    "time_awake_minutes",
    "calories_kcal",
    "offset_seconds",
    "heart_rate_bpm",
    "bpm",
    "avg_heart_rate_bpm",
    "min_heart_rate_bpm",
    "max_heart_rate_bpm",
    "bmi",
    "muscle_mass_kg",
    "bone_mass_kg",
    "basal_metabolism_kcal",
    "cadence",
    "speed_mps",
    "pace_sec_per_km",
    "accuracy",
    "hdop",
}
PERCENTAGES = {
    "spo2_pct",
    "avg_spo2_pct",
    "stress_score",
    "sleep_score",
    "body_fat_pct",
    "water_pct",
}


class ValidationError(ValueError):
    """Safe message: no account IDs, measurements or file contents."""


def parse_offset(value: str) -> timezone:
    if not re.fullmatch(r"[+-]\d{2}:\d{2}", value):
        raise ValidationError("UTC offset must use +HH:MM or -HH:MM")
    hours, minutes = map(int, value[1:].split(":"))
    if minutes > 59 or hours > 14 or (hours == 14 and minutes):
        raise ValidationError("UTC offset is outside the supported range")
    return timezone(timedelta(minutes=(hours * 60 + minutes) * (1 if value[0] == "+" else -1)))


def parse_timestamp(value: Any, local_tz: timezone) -> datetime:
    if not isinstance(value, str) or "T" not in value and " " not in value:
        raise ValidationError("Timestamp must be an ISO datetime")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValidationError("Timestamp must be an ISO datetime") from None
    return (parsed.replace(tzinfo=local_tz) if parsed.tzinfo is None else parsed).astimezone(
        local_tz
    )


def _scan(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if re.sub(r"[^a-z0-9]", "", key.casefold()) in FORBIDDEN:
                raise ValidationError("Credential field detected; entire input rejected")
            _scan(item)
    elif isinstance(value, list):
        for item in value:
            _scan(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValidationError("Non-finite number detected")
    elif isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        # Bridge encodes sleep stages as a JSON string; inspect embedded JSON too.
        try:
            embedded = json.loads(value)
        except ValueError:
            return
        _scan(embedded)


def _number(row: dict, key: str, minimum: float, maximum: float | None = None) -> None:
    value = row.get(key)
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationError("Metric must be a finite number or null")
    if value < minimum or maximum is not None and value > maximum:
        raise ValidationError("Metric outside the supported schema range")


def validate(payload: Any, utc_offset: str = "+08:00") -> list[dict]:
    local_tz = parse_offset(utc_offset)
    _scan(payload)
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        raise ValidationError("Unsupported JSON envelope schema_version; expected 1.0")
    if payload.get("source") != "mi_fitness_data_bridge":
        raise ValidationError("Unsupported JSON envelope source")
    groups = payload.get("records")
    if not isinstance(groups, dict) or not groups:
        raise ValidationError("records must contain at least one dataset")
    result: list[dict] = []
    seen = set()
    accounts = set()
    for dataset, rows in groups.items():
        if dataset not in DATASETS:
            raise ValidationError("Unsupported dataset; update integration before import")
        if not isinstance(rows, list):
            raise ValidationError("Dataset records must be a list")
        for row in rows:
            if not isinstance(row, dict):
                raise ValidationError("Each record must be an object")
            identity = row.get("id")
            if not isinstance(identity, str) or not identity.strip():
                raise ValidationError("Each record requires a nonempty bridge id")
            account = row.get("user_id")
            if not isinstance(account, str) or not account.strip():
                raise ValidationError("Each record requires a nonempty bridge user_id")
            accounts.add(account)
            if (dataset, identity) in seen:
                raise ValidationError("Duplicate record identity within input")
            seen.add((dataset, identity))
            timestamp = row.get(DATASETS[dataset])
            if dataset == "daily_activity":
                try:
                    day = date.fromisoformat(timestamp)
                except (ValueError, TypeError):
                    raise ValidationError("Activity date must use YYYY-MM-DD") from None
                if day.isoformat() != timestamp:
                    raise ValidationError("Activity date must use YYYY-MM-DD")
                observed_at = timestamp
                local_date = timestamp
            else:
                start = parse_timestamp(timestamp, local_tz)
                observed_at = start.isoformat()
                local_date = start.date().isoformat()
                if dataset in {"sleep", "workouts", "abnormal_heart_beat"}:
                    end = parse_timestamp(row.get("end_at"), local_tz)
                    if end < start:
                        raise ValidationError("Session end precedes start")
            for field in NONNEGATIVE:
                _number(row, field, 0)
            for field in PERCENTAGES:
                _number(row, field, 0, 100)
            _number(row, "weight_kg", 0)
            _number(row, "latitude", -90, 90)
            _number(row, "longitude", -180, 180)
            if "steps" in row and row["steps"] is not None and int(row["steps"]) != row["steps"]:
                raise ValidationError("Step count must be an integer")
            required = {
                "daily_activity": ("steps",),
                "heart_rate": ("bpm",),
                "spo2": ("spo2_pct",),
                "stress": ("stress_score",),
                "body_measurements": ("weight_kg",),
                "workout_gps": ("latitude", "longitude"),
            }.get(dataset, ())
            if any(row.get(field) is None for field in required):
                raise ValidationError("Dataset is missing a required metric")
            clean = dict(row)
            del clean["user_id"]
            # Source cache bookkeeping is not a health measurement; exclude it from change detection.
            for field in ("created_at", "updated_at", "collected_at"):
                clean.pop(field, None)
            result.append(
                {
                    "dataset": dataset,
                    "id": identity,
                    "account": account,
                    "observed_at": observed_at,
                    "local_date": local_date,
                    "payload": clean,
                }
            )
    if len(accounts) > 1:
        raise ValidationError("Multiple accounts in input; use separate local subjects")
    return result


def read_export(path: Path) -> tuple[bytes, dict]:
    raw = path.read_bytes()
    try:

        def unique_object(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise ValidationError("Duplicate JSON object key")
                obj[key] = value
            return obj

        payload = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_object)
    except (UnicodeError, ValueError):
        raise ValidationError("Invalid UTF-8 JSON export") from None
    return raw, payload
