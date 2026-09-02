from __future__ import annotations

import unittest

from madmamba.monitoring import MonitoringUnavailableError, acquire_monitoring_lease


class FakeMonitoring:
    def __init__(self, owners: dict[int, str] | None = None, racing_ids: set[int] | None = None) -> None:
        self.owners = dict(owners or {})
        self.racing_ids = set(racing_ids or set())
        self.freed: list[int] = []

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
        self.freed.append(tool_id)
        self.owners.pop(tool_id, None)


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
