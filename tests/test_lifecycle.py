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

    def test_explicit_close_is_generation_guarded(self) -> None:
        lifecycle = InterpreterRuntimeLifecycle()
        stale = lifecycle.bootstrap(903)
        self.assertTrue(lifecycle.close(stale))
        replacement = lifecycle.bootstrap(903)

        self.assertFalse(lifecycle.close(stale))
        self.assertIs(replacement, lifecycle.runtimes.require(903))

    def test_managed_scope_never_steals_existing_kernel(self) -> None:
        lifecycle = InterpreterRuntimeLifecycle()
        existing = lifecycle.bootstrap(904)

        with self.assertRaisesRegex(RuntimeAlreadyBootstrappedError, "already has"):
            with lifecycle.managed(904):
                self.fail("managed scope must not reuse an existing owner")

        self.assertIs(existing, lifecycle.runtimes.require(904))

    def test_monitoring_attach_failure_cleans_new_claim(self) -> None:
        lifecycle = InterpreterRuntimeLifecycle()
        session = Mock(spec=MonitoringSession)
        lifecycle.monitoring.attach = Mock(side_effect=RuntimeError("attach failed"))

        with self.assertRaisesRegex(RuntimeError, "attach failed"):
            with lifecycle.managed(905, monitoring_session=session):
                self.fail("scope should not open when monitoring attachment fails")

        self.assertIsNone(lifecycle.runtimes.get(905))


if __name__ == "__main__":
    unittest.main()
