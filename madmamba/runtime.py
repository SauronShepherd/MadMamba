from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass


class CoverageGapError(LookupError):
    """Raised when the current interpreter has not been bootstrapped."""


@dataclass(frozen=True, slots=True)
class RuntimeKernel:
    """Identity and ownership root for one instrumented interpreter."""

    process_id: int
    interpreter_key: int


def current_interpreter_key() -> int:
    """Return a process-local identity for the current Python interpreter.

    ``sys.modules`` is interpreter-local in CPython. Its object identity therefore
    gives MadMamba a cheap, non-global key without depending on unstable private
    subinterpreter APIs.
    """

    return id(sys.modules)


class InterpreterRuntimeRegistry:
    """Thread-safe registry that never falls back across interpreters."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._kernels: dict[int, RuntimeKernel] = {}

    def bootstrap(self, interpreter_key: int | None = None) -> RuntimeKernel:
        """Create or return the kernel owned by ``interpreter_key``."""

        key = current_interpreter_key() if interpreter_key is None else interpreter_key
        with self._lock:
            kernel = self._kernels.get(key)
            if kernel is None:
                kernel = RuntimeKernel(process_id=os.getpid(), interpreter_key=key)
                self._kernels[key] = kernel
            return kernel

    def get(self, interpreter_key: int | None = None) -> RuntimeKernel | None:
        """Return the exact interpreter kernel, or ``None`` for a coverage gap."""

        key = current_interpreter_key() if interpreter_key is None else interpreter_key
        with self._lock:
            return self._kernels.get(key)

    def require(self, interpreter_key: int | None = None) -> RuntimeKernel:
        """Return the exact interpreter kernel or raise an explicit coverage gap."""

        key = current_interpreter_key() if interpreter_key is None else interpreter_key
        kernel = self.get(key)
        if kernel is None:
            raise CoverageGapError(f"interpreter {key} has not been bootstrapped")
        return kernel

    def registered_interpreters(self) -> tuple[int, ...]:
        """Return a stable snapshot of explicitly bootstrapped interpreter keys."""

        with self._lock:
            return tuple(sorted(self._kernels))
