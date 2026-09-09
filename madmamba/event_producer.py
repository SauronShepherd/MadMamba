from __future__ import annotations

import os
import sys
import threading
from collections.abc import Callable
from time import monotonic
from typing import Any

from .bundle import DiagnosticBundleWriter
from .monitoring import (
    MonitoringSession,
    MonitoringUnavailableError,
    acquire_monitoring_lease,
    start_monitoring_session,
)

_DEFAULT_MAX_EVENTS_PER_SECOND = 1000


class _EventBudget:
    """Small lock-protected one-second budget for instrumentation callbacks."""

    def __init__(self, limit: int) -> None:
        self.limit = max(1, limit)
        self._lock = threading.Lock()
        self._window_started = monotonic()
        self._emitted = 0
        self._throttle_notice_emitted = False

    def permit(self) -> tuple[bool, bool]:
        """Return (event_allowed, emit_throttle_notice)."""

        now = monotonic()
        with self._lock:
            if now - self._window_started >= 1.0:
                self._window_started = now
                self._emitted = 0
                self._throttle_notice_emitted = False
            if self._emitted < self.limit:
                self._emitted += 1
                return True, False
            if not self._throttle_notice_emitted:
                self._throttle_notice_emitted = True
                return False, True
            return False, False


def _configured_event_budget() -> int:
    raw = os.environ.get("MADMAMBA_MAX_EVENTS_PER_SECOND", "").strip()
    if not raw:
        return _DEFAULT_MAX_EVENTS_PER_SECOND
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_EVENTS_PER_SECOND
    return max(1, value)


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

    budget = _EventBudget(_configured_event_budget())
    callbacks: dict[int, Callable[..., object]] = {}
    mask = 0
    for event_name, event_value in selected:
        mask |= event_value

        def callback(*args: Any, _event_name: str = event_name) -> object:
            allowed, throttle_notice = budget.permit()
            try:
                if throttle_notice:
                    writer.write(
                        "python.monitoring.throttled",
                        {"limitPerSecond": budget.limit},
                    )
                if not allowed:
                    return None
                # Keep only structural event metadata. Code/frame objects and exception
                # values supplied by CPython are deliberately neither retained nor serialized.
                offset = next((value for value in args[1:] if isinstance(value, int)), None)
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
