from __future__ import annotations

import unittest
from unittest.mock import Mock

from madmamba.monitoring import MonitoringSession
from madmamba.runtime import CoverageGapError, InterpreterRuntimeRegistry
from madmamba.runtime_monitoring import InterpreterMonitoringSessions, MonitoringAlreadyAttachedError


class InterpreterMonitoringSessionsTests(unittest.TestCase):
    def test_attach_requires_the_live_kernel_generation(self) -> None:
        runtimes = InterpreterRuntimeRegistry()
        owner = runtimes.bootstrap(101)
        runtimes.unregister(101, expected_kernel=owner)
        sessions = InterpreterMonitoringSessions(runtimes)
        with self.assertRaisesRegex(CoverageGapError, "is not owned"):
            sessions.attach(owner, Mock(spec=MonitoringSession))

    def test_one_kernel_cannot_attach_two_sessions(self) -> None:
        runtimes = InterpreterRuntimeRegistry()
        owner = runtimes.bootstrap(202)
        sessions = InterpreterMonitoringSessions(runtimes)
        first = Mock(spec=MonitoringSession)
        second = Mock(spec=MonitoringSession)
        sessions.attach(owner, first)
        with self.assertRaisesRegex(MonitoringAlreadyAttachedError, "already has"):
            sessions.attach(owner, second)
        self.assertIs(first, sessions.get(owner))
        second.close.assert_not_called()

    def test_detach_closes_exact_owned_session_once(self) -> None:
        runtimes = InterpreterRuntimeRegistry()
        owner = runtimes.bootstrap(303)
        sessions = InterpreterMonitoringSessions(runtimes)
        monitoring = Mock(spec=MonitoringSession)
        sessions.attach(owner, monitoring)
        self.assertTrue(sessions.detach(owner, expected_session=monitoring))
        self.assertFalse(sessions.detach(owner, expected_session=monitoring))
        monitoring.close.assert_called_once_with()

    def test_status_reports_live_unattached_kernel_as_degraded(self) -> None:
        runtimes = InterpreterRuntimeRegistry()
        owner = runtimes.bootstrap(606)
        sessions = InterpreterMonitoringSessions(runtimes)
        status = sessions.status(owner)
        self.assertTrue(status.kernel_live)
        self.assertFalse(status.attached)
        self.assertTrue(status.degraded)
        self.assertIsNone(status.tool_id)

    def test_status_reports_owned_session_details(self) -> None:
        runtimes = InterpreterRuntimeRegistry()
        owner = runtimes.bootstrap(707)
        sessions = InterpreterMonitoringSessions(runtimes)
        monitoring = Mock(spec=MonitoringSession)
        monitoring.lease.tool_id = 3
        monitoring.lease.owns_slot.return_value = True
        monitoring.events = 12
        monitoring.callback_events = (4, 8)
        sessions.attach(owner, monitoring)
        status = sessions.status(owner)
        self.assertTrue(status.kernel_live)
        self.assertTrue(status.attached)
        self.assertFalse(status.degraded)
        self.assertEqual(3, status.tool_id)
        self.assertEqual(12, status.events)
        self.assertEqual((4, 8), status.callback_events)

    def test_teardown_closes_session_and_unregisters_kernel(self) -> None:
        runtimes = InterpreterRuntimeRegistry()
        owner = runtimes.bootstrap(808)
        sessions = InterpreterMonitoringSessions(runtimes)
        monitoring = Mock(spec=MonitoringSession)
        sessions.attach(owner, monitoring)
        self.assertTrue(sessions.teardown(owner))
        self.assertIsNone(runtimes.get(808))
        self.assertIsNone(sessions.get(owner))
        monitoring.close.assert_called_once_with()

    def test_stale_teardown_never_removes_replacement_owner(self) -> None:
        runtimes = InterpreterRuntimeRegistry()
        stale = runtimes.bootstrap(909)
        sessions = InterpreterMonitoringSessions(runtimes)
        runtimes.unregister(909, expected_kernel=stale)
        replacement = runtimes.bootstrap(909)
        replacement_session = Mock(spec=MonitoringSession)
        sessions.attach(replacement, replacement_session)
        self.assertFalse(sessions.teardown(stale))
        self.assertIs(replacement, runtimes.get(909))
        self.assertIs(replacement_session, sessions.get(replacement))
        replacement_session.close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
