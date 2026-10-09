from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

from .store import import_file, summary
from .validation import ValidationError, read_export, validate
from .zepp import import_zepp, read_zepp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline personal health data import and validation")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "import", "sync", "summary", "validate-zepp", "import-zepp",
                 "zepp-report"):
        p = sub.add_parser(name)
        p.add_argument("--utc-offset", default=os.getenv("HEALTHHUB_UTC_OFFSET", "+08:00"))
        p.add_argument("--subject", default=("zepp-life" if "zepp" in name else
                                            os.getenv("HEALTHHUB_SUBJECT", "band9-local")))
        p.add_argument(
            "--db", type=Path, default=Path(os.getenv("HEALTHHUB_DB", "data/healthhub.db"))
        )
        if name in {"validate", "import"}:
            p.add_argument("input", type=Path)
        if name in {"validate-zepp", "import-zepp"}:
            p.add_argument("input", type=Path)
        if name == "zepp-report":
            p.add_argument("--output", type=Path, default=Path("private/analysis/zepp-life"))
        if name == "sync":
            p.add_argument(
                "--inbox", type=Path, default=Path(os.getenv("HEALTHHUB_INBOX", "data/inbox"))
            )
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-zepp":
            export = read_zepp(args.input, args.utc_offset)
            result = {"valid": True, "rows": len(export["rows"]), "files": export["files"]}
        elif args.command == "import-zepp":
            result = import_zepp(args.input, args.db, args.subject, args.utc_offset)
        elif args.command == "zepp-report":
            from .zepp_report import write_report

            result = write_report(args.db, args.output, args.subject)
        elif args.command == "validate":
            _, payload = read_export(args.input)
            rows = validate(payload, args.utc_offset)
            result = {"valid": True, "rows": len(rows)}
        elif args.command == "import":
            result = import_file(args.input, args.db, args.subject, args.utc_offset)
        elif args.command == "summary":
            result = summary(args.db, args.subject)
        else:
            if not args.inbox.is_dir():
                raise ValidationError("Inbox does not exist; create it and add bridge JSON exports")
            results = [
                import_file(path, args.db, args.subject, args.utc_offset)
                for path in sorted(args.inbox.glob("*.json"))
                if path.is_file()
            ]
            result = {
                "files": len(results),
                **{
                    key: sum(item[key] for item in results)
                    for key in ("inserted", "updated", "unchanged")
                },
            }
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except ValidationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True))
    except (OSError, sqlite3.Error):
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Local file/database operation failed; check paths and permissions",
                }
            )
        )
    return 1
