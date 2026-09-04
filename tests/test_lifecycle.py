from __future__ import annotations

import unittest
from unittest.mock import Mock

from madmamba.lifecycle import InterpreterRuntimeLifecycle
from madmamba.monitoring import MonitoringSession
from madmamba.runtime import RuntimeAlreadyBootstrappedError


class InterpreterRuntimeLifecycleTests(unittest.TestCase):
    def test_managed_scope_unregisters_kernel_on_success(self) -> None:
        lifecycle = InterpreterRuntimeLifecycle()
        with lifecycle.managed(901) as kernel:
            self.assertIs(kernel, lifecycle.runtimes.require(901))
        self.assertIsNone(lifecycle.runtimes.get(901))

    def test_managed_scope_closes_monitoring_on_exception(self) -> None:
        lifecycle = InterpreterRuntimeLifecycle()
        session = Mock(spec=MonitoringSession)
        with self.assertRaisesRegex(RuntimeError, "boom"):
            with lifecycle.managed(902, monitoring_session=session) as kernel:
                self.assertIs(session, lifecycle.monitoring.get(kernel))
                raise RuntimeError("boom")
        session.close.assert_called_once_with()
        self.assertIsNone(lifecycle.runtimes.get(902))

    def test_managed_scope_never_steals_existing_kernel(self) -> None:
        lifecycle = InterpreterRuntimeLifecycle()
        existing = lifecycle.bootstrap(903)
        with self.assertRaisesRegex(RuntimeAlreadyBootstrappedError, "already has"):
            with lifecycle.managed(903):
                self.fail("managed scope must not reuse an existing owner")
        self.assertIs(existing, lifecycle.runtimes.require(903))

    def test_monitoring_attach_failure_cleans_new_claim(self) -> None:
        lifecycle = InterpreterRuntimeLifecycle()
        session = Mock(spec=MonitoringSession)
        lifecycle.monitoring.attach = Mock(side_effect=RuntimeError("attach failed"))
        with self.assertRaisesRegex(RuntimeError, "attach failed"):
            with lifecycle.managed(904, monitoring_session=session):
                self.fail("scope should not open")
        self.assertIsNone(lifecycle.runtimes.get(904))

    def test_status_does_not_bootstrap_missing_runtime(self) -> None:
        lifecycle = InterpreterRuntimeLifecycle()
        status = lifecycle.status(905)
        self.assertFalse(status.kernel_live)
        self.assertFalse(status.monitoring_attached)
        self.assertFalse(status.monitoring_degraded)
        self.assertEqual((), lifecycle.runtimes.registered_interpreters())

    def test_status_reports_live_runtime_without_monitoring_as_degraded(self) -> None:
        lifecycle = InterpreterRuntimeLifecycle()
        lifecycle.bootstrap(906)
        status = lifecycle.status(906)
        self.assertTrue(status.kernel_live)
        self.assertFalse(status.monitoring_attached)
        self.assertTrue(status.monitoring_degraded)
        self.assertEqual(0, status.monitoring_events)
        self.assertIsNone(status.monitoring_tool_id)


if __name__ == "__main__":
    unittest.main()
