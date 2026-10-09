"""Reproducible synthetic bridge export -> hub import. No network or account."""

from __future__ import annotations

import argparse
import json
import runpy
import socket
from pathlib import Path

from healthhub.store import import_file, summary
from healthhub.validation import validate

ROOT = Path(__file__).resolve().parents[1]


def blocked(*args, **kwargs):
    raise RuntimeError("PoC forbids network access")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, default=ROOT / "work/upstream")
    args = parser.parse_args()
    socket.create_connection = blocked
    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked
    from mi_fitness_mcp.export import export_database
    from mi_fitness_mcp.storage import Database

    demo_path = args.upstream / "examples/synthetic_demo.py"
    if not demo_path.is_file():
        raise SystemExit("Install the optional bridge and its pinned example checkout first.")
    base = ROOT / "data/poc"
    base.mkdir(parents=True, exist_ok=True)
    seed = runpy.run_path(str(demo_path))["seed"]
    seed(Database(base / "synthetic_bridge.db"))
    export_database(base / "synthetic_bridge.db", base / "inbox/synthetic_bridge.json")
    csv_paths = export_database(base / "synthetic_bridge.db", base / "csv", output_format="csv")
    source = base / "inbox/synthetic_bridge.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    assert len(validate(payload)) == 4
    first = import_file(source, base / "synthetic_hub.db", subject="synthetic-demo")
    replay = import_file(source, base / "synthetic_hub.db", subject="synthetic-demo")
    assert replay["inserted"] == 0 and replay["updated"] == 0 and replay["unchanged"] == 4
    state = summary(base / "synthetic_hub.db", subject="synthetic-demo")
    assert state["integrity"] == "ok" and state["total_rows"] == 4
    assert len(csv_paths) == 10
    report = {
        "synthetic_only": True,
        "network_blocked": True,
        "bridge_rows": 4,
        "csv_files": len(csv_paths),
        "first_import": first,
        "replay_import": replay,
        "sqlite_integrity": state["integrity"],
        "total_hub_rows": state["total_rows"],
        "live_band9_compatibility": "not_verified",
    }
    (base / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
