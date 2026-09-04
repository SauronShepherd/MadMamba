from __future__ import annotations

import threading
from dataclasses import dataclass

from .monitoring import MonitoringSession
from .runtime import CoverageGapError, InterpreterRuntimeRegistry, RuntimeKernel


class MonitoringAlreadyAttachedError(RuntimeError):
    """Raised when an interpreter kernel already owns a monitoring session."""


@dataclass(frozen=True, slots=True)
class MonitoringRuntimeStatus:
    """Observable monitoring state for one exact interpreter kernel generation."""

    interpreter_key: int
    kernel_live: bool
    attached: bool
    tool_id: int | None = None
    events: int = 0
    callback_events: tuple[int, ...] = ()
    owns_tool_slot: bool = False

    @property
    def degraded(self) -> bool:
        """Return whether the kernel is live without an active owned monitoring session."""

        return self.kernel_live and (not self.attached or not self.owns_tool_slot)


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

    def status(self, kernel: RuntimeKernel) -> MonitoringRuntimeStatus:
        """Return diagnostics for this exact kernel generation without fallback."""

        with self._lock:
            kernel_live = self._runtimes.get(kernel.interpreter_key) is kernel
            current = self._sessions.get(kernel.interpreter_key)
            if current is None or current[0] is not kernel:
                return MonitoringRuntimeStatus(kernel.interpreter_key, kernel_live, False)
            session = current[1]
            return MonitoringRuntimeStatus(
                interpreter_key=kernel.interpreter_key,
                kernel_live=kernel_live,
                attached=True,
                tool_id=session.lease.tool_id,
                events=session.events,
                callback_events=session.callback_events,
                owns_tool_slot=session.lease.owns_slot(),
            )

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

    def teardown(self, kernel: RuntimeKernel) -> bool:
        """Close monitoring and unregister one exact interpreter generation."""

        with self._lock:
            if self._runtimes.get(kernel.interpreter_key) is not kernel:
                return False
            current = self._sessions.get(kernel.interpreter_key)
            session = None
            if current is not None and current[0] is kernel:
                session = current[1]
                del self._sessions[kernel.interpreter_key]
            removed = self._runtimes.unregister(
                kernel.interpreter_key,
                expected_kernel=kernel,
            )
            if removed is not kernel:
                if session is not None:
                    self._sessions[kernel.interpreter_key] = (kernel, session)
                return False
        if session is not None:
            session.close()
        return True

    def attached_interpreters(self) -> tuple[int, ...]:
        """Return a stable snapshot of interpreter keys with active session ownership."""

        with self._lock:
            return tuple(sorted(self._sessions))
