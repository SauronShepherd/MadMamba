from __future__ import annotations

import sys
import threading
from dataclasses import dataclass, field
from typing import Protocol


class MonitoringUnavailableError(RuntimeError):
    """Raised when no cooperative monitoring tool slot can be acquired."""


class MonitoringBackend(Protocol):
    def get_tool(self, tool_id: int) -> str | None: ...

    def use_tool_id(self, tool_id: int, name: str) -> None: ...

    def free_tool_id(self, tool_id: int) -> None: ...


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


@dataclass(slots=True)
class MonitoringLease:
    """Ownership token for one cooperatively acquired monitoring tool ID."""

    tool_id: int
    tool_name: str
    _backend: MonitoringBackend = field(repr=False)
    _released: bool = field(default=False, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

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
