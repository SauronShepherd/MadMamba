from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from .bundle import DiagnosticBundleWriter
from .monitoring import (
    MonitoringSession,
    MonitoringUnavailableError,
    acquire_monitoring_lease,
    start_monitoring_session,
)


def _event_value(name: str) -> int | None:
    monitoring = getattr(sys, "monitoring", None)
    events = getattr(monitoring, "events", None)
    value = getattr(events, name, None)
    return int(value) if isinstance(value, int) and value > 0 else None


def create_diagnostic_monitoring_session(
    writer: DiagnosticBundleWriter,
) -> MonitoringSession | None:
    """Attach a bounded privacy-preserving producer to public ``sys.monitoring`` events."""

    selected: list[tuple[str, int]] = []
    for name in ("PY_START", "PY_RETURN", "RAISE"):
        value = _event_value(name)
        if value is not None:
            selected.append((name, value))
    if not selected:
        return None

    try:
        lease = acquire_monitoring_lease()
    except MonitoringUnavailableError:
        return None

    callbacks: dict[int, Callable[..., object]] = {}
    mask = 0
    for event_name, event_value in selected:
        mask |= event_value

        def callback(*args: Any, _event_name: str = event_name) -> object:
            # Keep only structural event metadata. Code/frame objects and exception
            # values supplied by CPython are deliberately neither retained nor serialized.
            offset = next((value for value in args[1:] if isinstance(value, int)), None)
            try:
                writer.write(
                    "python.monitoring",
                    {"event": _event_name, "bytecodeOffset": offset},
                )
            except Exception:
                # Instrumentation must never replace application control flow.
                return None
            return None

        callbacks[event_value] = callback

    try:
        return start_monitoring_session(lease, callbacks, events=mask)
    except BaseException:
        lease.release()
        raise
