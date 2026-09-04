from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from madmamba.bootstrap import run_python_script
from madmamba.lifecycle import application_lifecycle


class BootstrapTests(unittest.TestCase):
    def test_run_python_script_preserves_argv_and_owns_runtime_only_during_target(self) -> None:
        lifecycle = application_lifecycle()
        self.assertFalse(lifecycle.status().kernel_live)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "target.py"
            script.write_text(
                "import json,sys\n"
                "from madmamba.lifecycle import application_lifecycle\n"
                "print(json.dumps({'argv': sys.argv, 'live': application_lifecycle().status().kernel_live}))\n",
                encoding="utf-8",
            )
            stream = io.StringIO()
            with redirect_stdout(stream):
                result = run_python_script([str(script), "a b", "--flag=value"])
        self.assertEqual(0, result)
        payload = json.loads(stream.getvalue())
        self.assertEqual([str(script), "a b", "--flag=value"], payload["argv"])
        self.assertTrue(payload["live"])
        self.assertFalse(lifecycle.status().kernel_live)

    def test_run_python_cli_propagates_target_system_exit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "exit_target.py"
            script.write_text("raise SystemExit(23)\n", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-m", "madmamba", "run-python", "--", str(script)],
                check=False,
                text=True,
                capture_output=True,
            )
        self.assertEqual(23, completed.returncode)
        self.assertEqual("", completed.stdout)
        self.assertEqual("", completed.stderr)

    def test_string_system_exit_matches_python_cli_convention(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "message_exit.py"
            script.write_text("raise SystemExit('target failed')\n", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-m", "madmamba", "run-python", str(script)],
                check=False,
                text=True,
                capture_output=True,
            )
        self.assertEqual(1, completed.returncode)
        self.assertEqual("", completed.stdout)
        self.assertEqual("target failed\n", completed.stderr)


if __name__ == "__main__":
    unittest.main()
