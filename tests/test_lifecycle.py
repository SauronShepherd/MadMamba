from __future__ import annotations

import unittest
from unittest.mock import Mock

from madmamba.lifecycle import InterpreterRuntimeLifecycle
from madmamba.monitoring import MonitoringSession


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


if __name__ == "__main__":
    unittest.main()
