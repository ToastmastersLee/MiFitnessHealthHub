"""Run selected upstream offline tests and/or the original synthetic demo."""

from __future__ import annotations

import argparse
import ipaddress
import os
import runpy
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_CONNECT = socket.socket.connect
ORIGINAL_CONNECT_EX = socket.socket.connect_ex
ORIGINAL_CREATE_CONNECTION = socket.create_connection


def blocked(*args, **kwargs):
    raise RuntimeError("Bridge verification forbids network access")


def ensure_local(address):
    # Windows asyncio creates its self-pipe with a local TCP socketpair.
    # Permit numeric loopback only, never DNS or external Xiaomi endpoints.
    if not isinstance(address, tuple):
        blocked()
    try:
        if not ipaddress.ip_address(address[0]).is_loopback:
            blocked()
    except ValueError:
        blocked()


def local_connect(sock, address):
    ensure_local(address)
    return ORIGINAL_CONNECT(sock, address)


def local_connect_ex(sock, address):
    ensure_local(address)
    return ORIGINAL_CONNECT_EX(sock, address)


def local_create_connection(address, *args, **kwargs):
    ensure_local(address)
    return ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    upstream = ROOT / "work/upstream"
    temp = ROOT / "work/bridge-verification"
    temp.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(temp)
    os.environ["TMP"] = os.environ["TEMP"] = str(temp)
    socket.create_connection = local_create_connection
    socket.socket.connect = local_connect
    socket.socket.connect_ex = local_connect_ex
    if args.demo:
        runpy.run_path(str(upstream / "examples/synthetic_demo.py"), run_name="__main__")
        return 0
    import pytest

    # These suites use temporary local storage and patched auth/config; no real account.
    sys.path.insert(0, str(upstream / "src"))
    return pytest.main(
        [
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(temp / "pytest"),
            str(upstream / "tests/test_export.py"),
            str(upstream / "tests/test_cli_security.py"),
            str(upstream / "tests/test_db_path_override.py"),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
