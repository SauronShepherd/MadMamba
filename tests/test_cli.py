from __future__ import annotations

import io
import json
import subprocess
import sys
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
        self.assertIn("run", stream.getvalue())

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

    def test_run_preserves_argument_vector_and_exit_status(self) -> None:
        script = "import json,sys; print(json.dumps(sys.argv[1:])); raise SystemExit(23)"
        completed = subprocess.run(
            [sys.executable, "-m", "madmamba", "run", "--", sys.executable, "-c", script, "a b", "--flag=value"],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(23, completed.returncode)
        self.assertEqual(["a b", "--flag=value"], json.loads(completed.stdout))
        self.assertEqual("", completed.stderr)

    def test_run_does_not_capture_child_standard_streams(self) -> None:
        marker = object()
        completed = unittest.mock.Mock(returncode=7)
        with patch.object(cli.subprocess, "run", return_value=completed) as run:
            result = cli.run_application(["python", "app.py", "x"])
        self.assertEqual(7, result)
        run.assert_called_once_with(["python", "app.py", "x"], check=False)
        self.assertIsNot(marker, completed)

    def test_run_missing_application_maps_to_shell_not_found_status(self) -> None:
        with patch.object(cli.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(127, cli.run_application(["definitely-not-a-command"]))


if __name__ == "__main__":
    unittest.main()
