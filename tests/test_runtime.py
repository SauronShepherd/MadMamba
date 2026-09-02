from __future__ import annotations

import threading
import unittest

from madmamba.runtime import CoverageGapError, InterpreterRuntimeRegistry, current_interpreter_key


class InterpreterRuntimeRegistryTests(unittest.TestCase):
    def test_current_interpreter_bootstrap_is_stable(self) -> None:
        registry = InterpreterRuntimeRegistry()
        first = registry.bootstrap()
        second = registry.bootstrap()

        self.assertIs(first, second)
        self.assertEqual(current_interpreter_key(), first.interpreter_key)
        self.assertEqual((first.interpreter_key,), registry.registered_interpreters())

    def test_unbootstrapped_interpreter_is_reported_as_coverage_gap(self) -> None:
        registry = InterpreterRuntimeRegistry()

        self.assertIsNone(registry.get(987654321))
        with self.assertRaisesRegex(CoverageGapError, "has not been bootstrapped"):
            registry.require(987654321)

    def test_registry_never_falls_back_to_another_interpreter(self) -> None:
        registry = InterpreterRuntimeRegistry()
        first = registry.bootstrap(101)
        second = registry.bootstrap(202)

        self.assertIs(first, registry.require(101))
        self.assertIs(second, registry.require(202))
        self.assertIsNot(first, second)
        self.assertEqual((101, 202), registry.registered_interpreters())

    def test_concurrent_bootstrap_creates_one_kernel_per_interpreter(self) -> None:
        registry = InterpreterRuntimeRegistry()
        barrier = threading.Barrier(16)
        kernels = []
        failures = []
        result_lock = threading.Lock()

        def bootstrap() -> None:
            try:
                barrier.wait()
                kernel = registry.bootstrap(303)
                with result_lock:
                    kernels.append(kernel)
            except BaseException as exc:  # pragma: no cover - diagnostic path
                with result_lock:
                    failures.append(exc)

        threads = [threading.Thread(target=bootstrap) for _ in range(16)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        self.assertFalse(failures)
        self.assertEqual(16, len(kernels))
        self.assertEqual(1, len({id(kernel) for kernel in kernels}))
        self.assertEqual((303,), registry.registered_interpreters())


if __name__ == "__main__":
    unittest.main()
