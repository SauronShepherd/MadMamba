from __future__ import annotations

import threading

from .monitoring import MonitoringSession
from .runtime import CoverageGapError, InterpreterRuntimeRegistry, RuntimeKernel


class MonitoringAlreadyAttachedError(RuntimeError):
    """Raised when an interpreter kernel already owns a monitoring session."""


class InterpreterMonitoringSessions:
    """Own at most one monitoring session for each live interpreter kernel."""

    def __init__(self, runtimes: InterpreterRuntimeRegistry) -> None:
        self._runtimes = runtimes
        self._lock = threading.RLock()
        self._sessions: dict[int, tuple[RuntimeKernel, MonitoringSession]] = {}

    def attach(self, kernel: RuntimeKernel, session: MonitoringSession) -> None:
        """Attach ``session`` only while ``kernel`` is the live interpreter owner."""

        with self._lock:
            if self._runtimes.get(kernel.interpreter_key) is not kernel:
                raise CoverageGapError(
                    f"interpreter {kernel.interpreter_key} is not owned by this runtime kernel"
                )
            current = self._sessions.get(kernel.interpreter_key)
            if current is not None:
                raise MonitoringAlreadyAttachedError(
                    f"interpreter {kernel.interpreter_key} already has a monitoring session"
                )
            self._sessions[kernel.interpreter_key] = (kernel, session)

    def get(self, kernel: RuntimeKernel) -> MonitoringSession | None:
        """Return the session owned by this exact kernel generation."""

        with self._lock:
            current = self._sessions.get(kernel.interpreter_key)
            if current is None or current[0] is not kernel:
                return None
            return current[1]

    def detach(
        self,
        kernel: RuntimeKernel,
        *,
        expected_session: MonitoringSession | None = None,
    ) -> bool:
        """Detach and close only the session owned by this exact kernel generation."""

        with self._lock:
            current = self._sessions.get(kernel.interpreter_key)
            if current is None or current[0] is not kernel:
                return False
            if expected_session is not None and current[1] is not expected_session:
                return False
            session = current[1]
            del self._sessions[kernel.interpreter_key]
        session.close()
        return True

    def attached_interpreters(self) -> tuple[int, ...]:
        """Return a stable snapshot of interpreter keys with active session ownership."""

        with self._lock:
            return tuple(sorted(self._sessions))
