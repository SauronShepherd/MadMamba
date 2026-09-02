from __future__ import annotations

import unittest

from madmamba.monitoring import (
    MonitoringUnavailableError,
    acquire_monitoring_lease,
    start_monitoring_session,
)


class FakeMonitoring:
    def __init__(self, owners: dict[int, str] | None = None, racing_ids: set[int] | None = None) -> None:
        self.owners = dict(owners or {})
        self.racing_ids = set(racing_ids or set())
        self.freed: list[int] = []
        self.operations: list[tuple[object, ...]] = []
        self.callbacks: dict[tuple[int, int], object] = {}
        self.event_masks: dict[int, int] = {}
        self.fail_registration_event: int | None = None

    def get_tool(self, tool_id: int) -> str | None:
        return self.owners.get(tool_id)

    def use_tool_id(self, tool_id: int, name: str) -> None:
        if tool_id in self.racing_ids:
            self.racing_ids.remove(tool_id)
            self.owners[tool_id] = "racing-tool"
            raise ValueError("tool already in use")
        if tool_id in self.owners:
            raise ValueError("tool already in use")
        self.owners[tool_id] = name

    def free_tool_id(self, tool_id: int) -> None:
        self.operations.append(("free", tool_id))
        self.freed.append(tool_id)
        self.owners.pop(tool_id, None)

    def register_callback(self, tool_id: int, event: int, callback: object | None) -> object | None:
        self.operations.append(("callback", tool_id, event, callback is not None))
        if callback is not None and event == self.fail_registration_event:
            raise RuntimeError("registration failed")
        key = (tool_id, event)
        previous = self.callbacks.get(key)
        if callback is None:
            self.callbacks.pop(key, None)
        else:
            self.callbacks[key] = callback
        return previous

    def set_events(self, tool_id: int, event_set: int) -> None:
        self.operations.append(("events", tool_id, event_set))
        self.event_masks[tool_id] = event_set


class MonitoringLeaseTests(unittest.TestCase):
    def test_acquire_skips_existing_tools_without_eviction(self) -> None:
        backend = FakeMonitoring({0: "debugger", 1: "coverage"})
        lease = acquire_monitoring_lease(backend=backend, candidate_ids=(0, 1, 2))
        self.assertEqual(2, lease.tool_id)
        self.assertEqual("debugger", backend.owners[0])
        self.assertEqual("coverage", backend.owners[1])
        self.assertEqual("madmamba", backend.owners[2])
        self.assertEqual([], backend.freed)

    def test_racing_claim_moves_to_next_free_slot(self) -> None:
        backend = FakeMonitoring(racing_ids={0})
        lease = acquire_monitoring_lease(backend=backend, candidate_ids=(0, 1))
        self.assertEqual(1, lease.tool_id)
        self.assertEqual("racing-tool", backend.owners[0])
        self.assertEqual("madmamba", backend.owners[1])

    def test_release_is_idempotent_and_frees_owned_slot(self) -> None:
        backend = FakeMonitoring()
        lease = acquire_monitoring_lease(backend=backend, candidate_ids=(3,))
        self.assertTrue(lease.release())
        self.assertFalse(lease.release())
        self.assertEqual([3], backend.freed)

    def test_release_never_frees_replacement_owner(self) -> None:
        backend = FakeMonitoring()
        lease = acquire_monitoring_lease(backend=backend, candidate_ids=(4,))
        backend.owners[4] = "replacement-tool"
        self.assertFalse(lease.release())
        self.assertEqual("replacement-tool", backend.owners[4])
        self.assertEqual([], backend.freed)

    def test_callbacks_are_registered_before_events_are_enabled(self) -> None:
        backend = FakeMonitoring()
        lease = acquire_monitoring_lease(backend=backend, candidate_ids=(2,))
        callback = lambda *args: None
        session = start_monitoring_session(lease, {1: callback, 4: callback}, events=5)
        self.assertEqual(
            [("callback", 2, 1, True), ("callback", 2, 4, True), ("events", 2, 5)],
            backend.operations,
        )
        session.close()

    def test_close_disables_events_before_callbacks_and_tool_release(self) -> None:
        backend = FakeMonitoring()
        lease = acquire_monitoring_lease(backend=backend, candidate_ids=(2,))
        callback = lambda *args: None
        session = start_monitoring_session(lease, {1: callback, 4: callback}, events=5)
        backend.operations.clear()
        self.assertTrue(session.close())
        self.assertEqual(
            [("events", 2, 0), ("callback", 2, 4, False), ("callback", 2, 1, False), ("free", 2)],
            backend.operations,
        )
        self.assertFalse(session.close())

    def test_partial_registration_rolls_back_without_enabling_events(self) -> None:
        backend = FakeMonitoring()
        backend.fail_registration_event = 4
        lease = acquire_monitoring_lease(backend=backend, candidate_ids=(2,))
        callback = lambda *args: None
        with self.assertRaisesRegex(RuntimeError, "registration failed"):
            start_monitoring_session(lease, {1: callback, 4: callback}, events=5)
        self.assertEqual(0, backend.event_masks[2])
        self.assertNotIn((2, 1), backend.callbacks)
        self.assertTrue(lease.owns_slot())

    def test_stale_session_never_touches_replacement_owner(self) -> None:
        backend = FakeMonitoring()
        lease = acquire_monitoring_lease(backend=backend, candidate_ids=(2,))
        session = start_monitoring_session(lease, {1: lambda *args: None}, events=1)
        backend.owners[2] = "replacement-tool"
        backend.operations.clear()
        self.assertFalse(session.close())
        self.assertEqual([], backend.operations)
        self.assertEqual("replacement-tool", backend.owners[2])

    def test_no_available_slot_is_explicit_degraded_capability(self) -> None:
        backend = FakeMonitoring({0: "debugger", 1: "coverage"})
        with self.assertRaisesRegex(MonitoringUnavailableError, "no sys.monitoring tool ID"):
            acquire_monitoring_lease(backend=backend, candidate_ids=(0, 1))

    def test_invalid_candidate_inventory_is_rejected(self) -> None:
        backend = FakeMonitoring()
        for candidate_ids in ((), (1, 1), (-1,), (6,)):
            with self.subTest(candidate_ids=candidate_ids):
                with self.assertRaises(ValueError):
                    acquire_monitoring_lease(backend=backend, candidate_ids=candidate_ids)


if __name__ == "__main__":
    unittest.main()
