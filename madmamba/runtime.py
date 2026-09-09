from __future__ import annotations

import os
import threading
from dataclasses import dataclass


class CoverageGapError(LookupError):
    """Raised when the current interpreter has not been bootstrapped."""


class RuntimeAlreadyBootstrappedError(RuntimeError):
    """Raised when exclusive lifecycle ownership is requested twice."""


@dataclass(frozen=True, slots=True)
class RuntimeKernel:
    """Identity and ownership root for one instrumented interpreter."""

    process_id: int
    interpreter_key: int


# Imported modules are interpreter-local in CPython, so this object is created once
# per interpreter. Keeping a strong reference prevents its identity from being
# recycled, unlike a user-reassignable object such as ``sys.modules``.
_INTERPRETER_TOKEN = object()


def current_interpreter_key() -> int:
    """Return a stable process-local identity for the current Python interpreter.

    The module-level token is created independently in each interpreter and remains
    strongly referenced for the lifetime of that interpreter. User code cannot
    invalidate the key by reassigning ``sys.modules`` during a managed runtime.
    """

    return id(_INTERPRETER_TOKEN)


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

    def claim(self, interpreter_key: int | None = None) -> RuntimeKernel:
        """Atomically create one exclusively owned interpreter generation.

        Managed lifecycle scopes use this instead of idempotent ``bootstrap`` so a
        nested or racing owner cannot accidentally inherit and later tear down a
        kernel that belongs to another scope.
        """

        key = current_interpreter_key() if interpreter_key is None else interpreter_key
        with self._lock:
            if key in self._kernels:
                raise RuntimeAlreadyBootstrappedError(
                    f"interpreter {key} already has a live runtime kernel"
                )
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

    def unregister(
        self,
        interpreter_key: int | None = None,
        *,
        expected_kernel: RuntimeKernel | None = None,
    ) -> RuntimeKernel | None:
        """Remove one interpreter kernel without deleting a replacement owner.

        ``expected_kernel`` acts as a compare-and-remove guard for teardown paths.
        A stale cleanup callback therefore cannot unregister a newer kernel that
        reused the same interpreter key after the old owner was removed.
        """

        key = current_interpreter_key() if interpreter_key is None else interpreter_key
        with self._lock:
            kernel = self._kernels.get(key)
            if kernel is None:
                return None
            if expected_kernel is not None and kernel is not expected_kernel:
                return None
            del self._kernels[key]
            return kernel

    def registered_interpreters(self) -> tuple[int, ...]:
        """Return a stable snapshot of explicitly bootstrapped interpreter keys."""

        with self._lock:
            return tuple(sorted(self._kernels))
