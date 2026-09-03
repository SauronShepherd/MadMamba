from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from .monitoring import MonitoringSession
from .runtime import InterpreterRuntimeRegistry, RuntimeKernel
from .runtime_monitoring import InterpreterMonitoringSessions


class InterpreterRuntimeLifecycle:
    """High-level owner for interpreter-local runtime resources."""

    def __init__(self, runtimes: InterpreterRuntimeRegistry | None = None) -> None:
        self.runtimes = runtimes or InterpreterRuntimeRegistry()
        self.monitoring = InterpreterMonitoringSessions(self.runtimes)

    def bootstrap(self, interpreter_key: int | None = None) -> RuntimeKernel:
        return self.runtimes.bootstrap(interpreter_key)

    def attach_monitoring(self, kernel: RuntimeKernel, session: MonitoringSession) -> None:
        self.monitoring.attach(kernel, session)

    def close(self, kernel: RuntimeKernel) -> bool:
        return self.monitoring.teardown(kernel)

    @contextmanager
    def managed(
        self,
        interpreter_key: int | None = None,
        *,
        monitoring_session: MonitoringSession | None = None,
    ) -> Iterator[RuntimeKernel]:
        """Own one exclusive runtime generation for a bounded lifecycle scope."""

        kernel = self.runtimes.claim(interpreter_key)
        try:
            if monitoring_session is not None:
                self.attach_monitoring(kernel, monitoring_session)
            yield kernel
        finally:
            self.close(kernel)
