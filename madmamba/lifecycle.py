from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from .bundle import DiagnosticBundleWriter
from .monitoring import MonitoringSession
from .runtime import InterpreterRuntimeRegistry, RuntimeKernel, current_interpreter_key
from .runtime_monitoring import InterpreterMonitoringSessions


@dataclass(frozen=True, slots=True)
class RuntimeLifecycleStatus:
    """Stable diagnostics for one interpreter lifecycle slot."""

    interpreter_key: int
    kernel_live: bool
    monitoring_attached: bool
    monitoring_degraded: bool
    monitoring_events: int = 0
    monitoring_tool_id: int | None = None


class InterpreterRuntimeLifecycle:
    """High-level owner for interpreter-local runtime resources."""

    def __init__(self, runtimes: InterpreterRuntimeRegistry | None = None) -> None:
        self.runtimes = runtimes or InterpreterRuntimeRegistry()
        self.monitoring = InterpreterMonitoringSessions(self.runtimes)
        self._managed_kernel: ContextVar[RuntimeKernel | None] = ContextVar(
            f"madmamba_managed_kernel_{id(self)}", default=None
        )

    def bootstrap(self, interpreter_key: int | None = None) -> RuntimeKernel:
        return self.runtimes.bootstrap(interpreter_key)

    def attach_monitoring(self, kernel: RuntimeKernel, session: MonitoringSession) -> None:
        self.monitoring.attach(kernel, session)

    def close(self, kernel: RuntimeKernel) -> bool:
        return self.monitoring.teardown(kernel)

    def status(self, interpreter_key: int | None = None) -> RuntimeLifecycleStatus:
        """Return bounded lifecycle diagnostics without creating runtime state."""

        key = current_interpreter_key() if interpreter_key is None else interpreter_key
        kernel = self.runtimes.get(key)
        if kernel is None:
            return RuntimeLifecycleStatus(
                interpreter_key=key,
                kernel_live=False,
                monitoring_attached=False,
                monitoring_degraded=False,
            )
        monitoring = self.monitoring.status(kernel)
        return RuntimeLifecycleStatus(
            interpreter_key=key,
            kernel_live=monitoring.kernel_live,
            monitoring_attached=monitoring.attached,
            monitoring_degraded=monitoring.degraded,
            monitoring_events=monitoring.events,
            monitoring_tool_id=monitoring.tool_id,
        )

    @staticmethod
    def _bundle_payload(status: RuntimeLifecycleStatus) -> dict[str, object]:
        """Return bounded lifecycle metadata suitable for local diagnostic bundles."""

        return {
            "interpreterKey": status.interpreter_key,
            "kernelLive": status.kernel_live,
            "monitoringAttached": status.monitoring_attached,
            "monitoringDegraded": status.monitoring_degraded,
            "monitoringEvents": status.monitoring_events,
            "monitoringToolId": status.monitoring_tool_id,
        }

    @contextmanager
    def managed(
        self,
        interpreter_key: int | None = None,
        *,
        monitoring_session: MonitoringSession | None = None,
        diagnostic_writer: DiagnosticBundleWriter | None = None,
    ) -> Iterator[RuntimeKernel]:
        """Own or borrow one runtime generation for a bounded lifecycle scope.

        Nested scopes in the same execution context borrow the outer kernel instead
        of attempting a second exclusive claim. Only the outer scope owns monitoring,
        bundle lifecycle events and teardown. Explicitly targeting a different
        interpreter while nested remains an error rather than silently crossing
        interpreter boundaries.
        """

        borrowed = self._managed_kernel.get()
        if borrowed is not None:
            if interpreter_key is not None and interpreter_key != borrowed.interpreter_key:
                raise ValueError("nested runtime scope cannot change interpreter")
            yield borrowed
            return

        kernel = self.runtimes.claim(interpreter_key)
        token = self._managed_kernel.set(kernel)
        try:
            if monitoring_session is not None:
                self.attach_monitoring(kernel, monitoring_session)
            if diagnostic_writer is not None:
                diagnostic_writer.write(
                    "runtime.started",
                    self._bundle_payload(self.status(kernel.interpreter_key)),
                )
            yield kernel
        finally:
            try:
                if diagnostic_writer is not None:
                    diagnostic_writer.write(
                        "runtime.stopped",
                        self._bundle_payload(self.status(kernel.interpreter_key)),
                    )
            finally:
                try:
                    self.close(kernel)
                finally:
                    self._managed_kernel.reset(token)


_application_lifecycle = InterpreterRuntimeLifecycle()


def application_lifecycle() -> InterpreterRuntimeLifecycle:
    """Return the interpreter-local application lifecycle owner without bootstrapping it."""

    return _application_lifecycle


@contextmanager
def managed_application_runtime(
    *,
    monitoring_session: MonitoringSession | None = None,
    diagnostic_writer: DiagnosticBundleWriter | None = None,
) -> Iterator[RuntimeKernel]:
    """Own the shared in-process runtime used by diagnostics and instrumentation."""

    with _application_lifecycle.managed(
        monitoring_session=monitoring_session,
        diagnostic_writer=diagnostic_writer,
    ) as kernel:
        yield kernel
