from __future__ import annotations

import runpy
import sys
from collections.abc import Sequence

from .lifecycle import managed_application_runtime


def _system_exit_code(exc: SystemExit) -> int:
    if exc.code is None:
        return 0
    if isinstance(exc.code, int):
        return exc.code
    print(exc.code, file=sys.stderr)
    return 1


def run_python_script(application: Sequence[str]) -> int:
    """Execute one Python script or module inside the target interpreter lifecycle.

    The target keeps normal Python ``sys.argv`` semantics and inherited stdio.
    A leading ``-m <module>`` executes the module as ``__main__``. ``SystemExit``
    is translated to the same process exit status conventions as the Python
    command line while other exceptions deliberately retain their traceback.
    """

    command = list(application)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("run-python requires a Python script or -m module")

    module_name: str | None = None
    if command[0] == "-m":
        if len(command) < 2 or not command[1].strip():
            raise ValueError("run-python -m requires a module name")
        module_name = command[1]
        target_argv = [module_name, *command[2:]]
    else:
        target_argv = [command[0], *command[1:]]

    previous_argv = sys.argv
    sys.argv = target_argv
    try:
        with managed_application_runtime():
            try:
                if module_name is None:
                    runpy.run_path(command[0], run_name="__main__")
                else:
                    runpy.run_module(module_name, run_name="__main__", alter_sys=False)
            except SystemExit as exc:
                return _system_exit_code(exc)
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
