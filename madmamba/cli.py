from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version

from .bundle_inspect import inspect_bundle
from .bundle_reader import DiagnosticBundleIntegrityError
from .lifecycle import InterpreterRuntimeLifecycle, RuntimeLifecycleStatus, application_lifecycle


def package_version() -> str:
    """Return the installed package version without importing packaging helpers."""

    try:
        return version("madmamba")
    except PackageNotFoundError:
        return "0.1.0.dev0"


def _lifecycle_payload(status: RuntimeLifecycleStatus) -> dict[str, object]:
    return {
        "interpreterKey": status.interpreter_key,
        "kernelLive": status.kernel_live,
        "monitoringAttached": status.monitoring_attached,
        "monitoringDegraded": status.monitoring_degraded,
        "monitoringEvents": status.monitoring_events,
        "monitoringToolId": status.monitoring_tool_id,
    }


def _is_free_threaded() -> bool:
    checker = getattr(sys, "_is_gil_enabled", None)
    if callable(checker):
        return not bool(checker())
    return bool(getattr(sys.flags, "gil", 1) == 0)


def doctor_payload(lifecycle: InterpreterRuntimeLifecycle | None = None) -> dict[str, object]:
    """Return bounded, non-secret runtime capability and lifecycle diagnostics."""

    monitoring = getattr(sys, "monitoring", None)
    owner = application_lifecycle() if lifecycle is None else lifecycle
    return {
        "madmambaVersion": package_version(),
        "pythonVersion": platform.python_version(),
        "implementation": platform.python_implementation(),
        "sysMonitoringAvailable": monitoring is not None,
        "freeThreaded": _is_free_threaded(),
        "runtimeLifecycle": _lifecycle_payload(owner.status()),
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
    subcommands.add_parser(
        "run",
        help="Run an application without changing its arguments or stdio. Use -- before the target command when needed.",
    )
    subcommands.add_parser(
        "run-python",
        help="Run a Python script inside MadMamba's target-interpreter runtime lifecycle. Use -- before target arguments when needed.",
    )
    bundle_inspect = subcommands.add_parser(
        "bundle-inspect",
        help="Validate and summarize a diagnostic bundle without exposing payload contents.",
    )
    bundle_inspect.add_argument("directory", help="Diagnostic bundle directory.")
    bundle_inspect.add_argument(
        "--recover-open",
        action="store_true",
        help="Recover complete records from an interrupted OPEN bundle.",
    )
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
    except PermissionError:
        return 126
    except FileNotFoundError:
        return 127


def run_python_application(application: Sequence[str]) -> int:
    """Launch the conservative Python target bootstrap in the child interpreter."""

    command = list(application)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("run-python requires a Python script")
    try:
        return subprocess.run(
            [sys.executable, "-m", "madmamba.bootstrap", "--", *command],
            check=False,
        ).returncode
    except PermissionError:
        return 126
    except FileNotFoundError:
        return 127


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args, remainder = parser.parse_known_args(argv)
    if args.command is None:
        if remainder:
            parser.error(f"unrecognized arguments: {' '.join(remainder)}")
        parser.print_help()
        return 0
    if args.command == "doctor":
        if remainder:
            parser.error(f"unrecognized arguments: {' '.join(remainder)}")
        payload = doctor_payload()
        if args.as_json:
            print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        else:
            lifecycle = payload["runtimeLifecycle"]
            assert isinstance(lifecycle, dict)
            print(f"MadMamba {payload['madmambaVersion']}")
            print(f"Python {payload['pythonVersion']} ({payload['implementation']})")
            print(f"sys.monitoring: {'available' if payload['sysMonitoringAvailable'] else 'unavailable'}")
            print(f"free-threaded: {'yes' if payload['freeThreaded'] else 'no'}")
            print(f"runtime kernel: {'live' if lifecycle['kernelLive'] else 'inactive'}")
            if lifecycle["kernelLive"]:
                monitoring_state = "attached" if lifecycle["monitoringAttached"] else "not attached"
                if lifecycle["monitoringDegraded"]:
                    monitoring_state += " (degraded)"
                print(f"runtime monitoring: {monitoring_state}")
        return 0
    if args.command == "run":
        try:
            return run_application(remainder)
        except ValueError as exc:
            parser.error(str(exc))
    if args.command == "run-python":
        try:
            return run_python_application(remainder)
        except ValueError as exc:
            parser.error(str(exc))
    if args.command == "bundle-inspect":
        if remainder:
            parser.error(f"unrecognized arguments: {' '.join(remainder)}")
        try:
            payload = inspect_bundle(args.directory, recover_open=args.recover_open)
        except DiagnosticBundleIntegrityError as exc:
            print(f"madmamba: bundle integrity error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return 0
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())