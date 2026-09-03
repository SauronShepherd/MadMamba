from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from .monitoring import MonitoringSession
from .runtime import InterpreterRuntimeRegistry, RuntimeKernel
from .runtime_monitoring import InterpreterMonitoringSessions


class InterpreterRuntimeLifecycle:
    """High-level owner for one process' interpreter-local runtime resources.

    The lifecycle keeps runtime-kernel registration and optional ``sys.monitoring``
    ownership behind one API so callers do not have to reproduce teardown ordering.
    ``managed()`` is exception-safe and always performs generation-guarded cleanup.
    """

    def __init__(self, runtimes: InterpreterRuntimeRegistry | None = None) -> None:
        self.runtimes = runtimes or InterpreterRuntimeRegistry()
        self.monitoring = InterpreterMonitoringSessions(self.runtimes)

    def bootstrap(self, interpreter_key: int | None = None) -> RuntimeKernel:
        """Bootstrap or return the exact runtime kernel for an interpreter."""

        return self.runtimes.bootstrap(interpreter_key)

    def attach_monitoring(self, kernel: RuntimeKernel, session: MonitoringSession) -> None:
        """Attach monitoring to the exact live runtime generation."""

        self.monitoring.attach(kernel, session)

    def close(self, kernel: RuntimeKernel) -> bool:
        """Close monitoring and unregister the exact runtime generation."""

        return self.monitoring.teardown(kernel)

    @contextmanager
    def managed(
        self,
        interpreter_key: int | None = None,
        *,
        monitoring_session: MonitoringSession | None = None,
    ) -> Iterator[RuntimeKernel]:
        """Own one runtime generation for a bounded bootstrap/use/teardown scope."""

        kernel = self.bootstrap(interpreter_key)
        if monitoring_session is not None:
            self.attach_monitoring(kernel, monitoring_session)
        try:
            yield kernel
        finally:
            self.close(kernel)
