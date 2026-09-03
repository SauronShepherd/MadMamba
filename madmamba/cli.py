from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from typing import Sequence


def package_version() -> str:
    """Return the installed package version without importing packaging helpers."""

    try:
        return version("madmamba")
    except PackageNotFoundError:
        return "0.1.0.dev0"


def doctor_payload() -> dict[str, object]:
    """Return bounded, non-secret runtime capability diagnostics."""

    monitoring = getattr(sys, "monitoring", None)
    return {
        "madmambaVersion": package_version(),
        "pythonVersion": platform.python_version(),
        "implementation": platform.python_implementation(),
        "sysMonitoringAvailable": monitoring is not None,
        "freeThreaded": bool(getattr(sys.flags, "gil", 1) == 0),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="madmamba",
        description="Local-first diagnostics for Python and PySpark.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {package_version()}")
    subcommands = parser.add_subparsers(dest="command")
    doctor = subcommands.add_parser("doctor", help="Report local runtime capabilities.")
    doctor.add_argument("--json", action="store_true", dest="as_json", help="Emit machine-readable JSON.")
    run = subcommands.add_parser("run", help="Run an application without changing its arguments or stdio.")
    run.add_argument("application", nargs=argparse.REMAINDER, help="Application command, optionally after --.")
    return parser


def run_application(application: Sequence[str]) -> int:
    """Run a child application with inherited stdio and return its exit status."""

    command = list(application)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("run requires an application command")
    try:
        return subprocess.run(command, check=False).returncode
    except FileNotFoundError:
        return 127


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "doctor":
        payload = doctor_payload()
        if args.as_json:
            print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        else:
            print(f"MadMamba {payload['madmambaVersion']}")
            print(f"Python {payload['pythonVersion']} ({payload['implementation']})")
            print(f"sys.monitoring: {'available' if payload['sysMonitoringAvailable'] else 'unavailable'}")
            print(f"free-threaded: {'yes' if payload['freeThreaded'] else 'no'}")
        return 0
    if args.command == "run":
        try:
            return run_application(args.application)
        except ValueError as exc:
            parser.error(str(exc))
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
