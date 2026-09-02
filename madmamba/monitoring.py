from __future__ import annotations

import sys
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol


class MonitoringUnavailableError(RuntimeError):
    """Raised when no cooperative monitoring tool slot can be acquired."""


MonitoringCallback = Callable[..., object]


class MonitoringBackend(Protocol):
    def get_tool(self, tool_id: int) -> str | None: ...

    def use_tool_id(self, tool_id: int, name: str) -> None: ...

    def free_tool_id(self, tool_id: int) -> None: ...

    def register_callback(
        self, tool_id: int, event: int, callback: MonitoringCallback | None
    ) -> MonitoringCallback | None: ...

    def set_events(self, tool_id: int, event_set: int) -> None: ...


class SysMonitoringBackend:
    """Thin adapter around CPython's public ``sys.monitoring`` API."""

    def __init__(self) -> None:
        monitoring = getattr(sys, "monitoring", None)
        if monitoring is None:
            raise MonitoringUnavailableError("sys.monitoring is unavailable on this interpreter")
        self._monitoring = monitoring

    def get_tool(self, tool_id: int) -> str | None:
        return self._monitoring.get_tool(tool_id)

    def use_tool_id(self, tool_id: int, name: str) -> None:
        self._monitoring.use_tool_id(tool_id, name)

    def free_tool_id(self, tool_id: int) -> None:
        self._monitoring.free_tool_id(tool_id)

    def register_callback(
        self, tool_id: int, event: int, callback: MonitoringCallback | None
    ) -> MonitoringCallback | None:
        return self._monitoring.register_callback(tool_id, event, callback)

    def set_events(self, tool_id: int, event_set: int) -> None:
        self._monitoring.set_events(tool_id, event_set)


@dataclass(slots=True)
class MonitoringLease:
    """Ownership token for one cooperatively acquired monitoring tool ID."""

    tool_id: int
    tool_name: str
    _backend: MonitoringBackend = field(repr=False)
    _released: bool = field(default=False, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def owns_slot(self) -> bool:
        """Return whether this lease still owns its monitoring tool slot."""

        with self._lock:
            return not self._released and self._backend.get_tool(self.tool_id) == self.tool_name

    def release(self) -> bool:
        """Release only the slot this lease still owns.

        Returning ``False`` means teardown was already completed or ownership
        changed externally. In either case MadMamba deliberately leaves the
        current owner untouched.
        """

        with self._lock:
            if self._released:
                return False
            if self._backend.get_tool(self.tool_id) != self.tool_name:
                self._released = True
                return False
            self._backend.free_tool_id(self.tool_id)
            self._released = True
            return True

    def __enter__(self) -> MonitoringLease:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()


@dataclass(slots=True)
class MonitoringSession:
    """Active callbacks and event mask owned by one monitoring lease."""

    lease: MonitoringLease
    events: int
    callback_events: tuple[int, ...]
    _closed: bool = field(default=False, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def close(self) -> bool:
        """Disable events, unregister callbacks, then release the owned tool ID.

        If the lease no longer owns the slot, cleanup deliberately does nothing
        to the replacement owner's callbacks or event mask.
        """

        with self._lock:
            if self._closed:
                return False
            self._closed = True
            if not self.lease.owns_slot():
                self.lease.release()
                return False
            backend = self.lease._backend
            backend.set_events(self.lease.tool_id, 0)
            for event in reversed(self.callback_events):
                backend.register_callback(self.lease.tool_id, event, None)
            return self.lease.release()

    def __enter__(self) -> MonitoringSession:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


def start_monitoring_session(
    lease: MonitoringLease,
    callbacks: Mapping[int, MonitoringCallback],
    *,
    events: int,
) -> MonitoringSession:
    """Register every callback before enabling any monitoring event.

    Registration is transactional with respect to event activation: if any
    callback registration or ``set_events`` fails, events remain disabled and
    callbacks installed by this call are removed. The lease itself remains
    owned by the caller so it can choose whether to retry with a reduced scope.
    """

    if events <= 0:
        raise ValueError("events must be a positive event mask")
    if not callbacks:
        raise ValueError("at least one callback is required")
    if any(event <= 0 for event in callbacks):
        raise ValueError("callback event IDs must be positive")
    if not lease.owns_slot():
        raise MonitoringUnavailableError("monitoring lease no longer owns its tool ID")

    backend = lease._backend
    registered: list[int] = []
    try:
        for event, callback in callbacks.items():
            backend.register_callback(lease.tool_id, event, callback)
            registered.append(event)
        backend.set_events(lease.tool_id, events)
    except BaseException:
        if lease.owns_slot():
            backend.set_events(lease.tool_id, 0)
            for event in reversed(registered):
                backend.register_callback(lease.tool_id, event, None)
        raise
    return MonitoringSession(lease, events, tuple(registered))


def acquire_monitoring_lease(
    *,
    backend: MonitoringBackend | None = None,
    candidate_ids: tuple[int, ...] = tuple(range(6)),
    tool_name: str = "madmamba",
) -> MonitoringLease:
    """Acquire the first available monitoring tool ID without eviction.

    CPython exposes six tool slots (0..5). A slot is only attempted after it is
    observed free, and a racing claim is handled by trying the next candidate.
    Existing owners are never freed or replaced.
    """

    if not tool_name.strip():
        raise ValueError("tool_name must not be empty")
    if not candidate_ids or len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("candidate_ids must be a non-empty unique sequence")
    if any(tool_id < 0 or tool_id > 5 for tool_id in candidate_ids):
        raise ValueError("monitoring tool IDs must be between 0 and 5")

    monitoring = SysMonitoringBackend() if backend is None else backend
    for tool_id in candidate_ids:
        if monitoring.get_tool(tool_id) is not None:
            continue
        try:
            monitoring.use_tool_id(tool_id, tool_name)
        except ValueError:
            # A cooperative peer may have claimed the slot after get_tool().
            continue
        if monitoring.get_tool(tool_id) == tool_name:
            return MonitoringLease(tool_id, tool_name, monitoring)

    raise MonitoringUnavailableError("no sys.monitoring tool ID is available")
