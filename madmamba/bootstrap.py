from __future__ import annotations

import runpy
import sys
from collections.abc import Sequence

from .lifecycle import managed_application_runtime


def run_python_script(application: Sequence[str]) -> int:
    """Execute one Python script inside the target interpreter lifecycle.

    The script keeps normal Python ``sys.argv`` semantics and inherited stdio.
    ``SystemExit`` is translated to the same process exit status conventions as
    the Python command line while other exceptions are deliberately allowed to
    propagate with their traceback.
    """

    command = list(application)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("run-python requires a Python script")

    previous_argv = sys.argv
    sys.argv = [command[0], *command[1:]]
    try:
        with managed_application_runtime():
            try:
                runpy.run_path(command[0], run_name="__main__")
            except SystemExit as exc:
                if exc.code is None:
                    return 0
                if isinstance(exc.code, int):
                    return exc.code
                print(exc.code, file=sys.stderr)
                return 1
        return 0
    finally:
        sys.argv = previous_argv


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run_python_script(sys.argv[1:] if argv is None else argv)
    except ValueError as exc:
        print(f"madmamba bootstrap: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
