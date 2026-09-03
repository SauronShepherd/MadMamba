from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from madmamba import cli


class CliTests(unittest.TestCase):
    def test_no_command_prints_help_and_succeeds(self) -> None:
        stream = io.StringIO()
        with redirect_stdout(stream):
            result = cli.main([])
        self.assertEqual(0, result)
        self.assertIn("Local-first diagnostics", stream.getvalue())
        self.assertIn("doctor", stream.getvalue())

    def test_doctor_json_is_bounded_machine_readable_capability_output(self) -> None:
        stream = io.StringIO()
        with patch.object(cli, "package_version", return_value="0.1.test"), redirect_stdout(stream):
            result = cli.main(["doctor", "--json"])
        self.assertEqual(0, result)
        payload = json.loads(stream.getvalue())
        self.assertEqual("0.1.test", payload["madmambaVersion"])
        self.assertIsInstance(payload["pythonVersion"], str)
        self.assertIsInstance(payload["implementation"], str)
        self.assertIsInstance(payload["sysMonitoringAvailable"], bool)
        self.assertIsInstance(payload["freeThreaded"], bool)
        self.assertEqual(
            {
                "freeThreaded",
                "implementation",
                "madmambaVersion",
                "pythonVersion",
                "sysMonitoringAvailable",
            },
            set(payload),
        )

    def test_doctor_text_never_requires_monitoring_backend(self) -> None:
        stream = io.StringIO()
        with patch.object(cli.sys, "monitoring", None, create=True), redirect_stdout(stream):
            result = cli.main(["doctor"])
        self.assertEqual(0, result)
        self.assertIn("sys.monitoring: unavailable", stream.getvalue())

    def test_version_uses_argparse_version_exit_contract(self) -> None:
        stream = io.StringIO()
        with patch.object(cli, "package_version", return_value="0.1.test"), redirect_stdout(stream):
            with self.assertRaisesRegex(SystemExit, "0"):
                cli.main(["--version"])
        self.assertEqual("madmamba 0.1.test\n", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
