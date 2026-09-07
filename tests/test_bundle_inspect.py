from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from madmamba import cli
from madmamba.bundle import DiagnosticBundleWriter
from madmamba.bundle_inspect import inspect_bundle


class BundleInspectTests(unittest.TestCase):
    def test_final_bundle_summary_is_integrity_checked_and_payload_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            writer = DiagnosticBundleWriter(root)
            writer.append("runtime", {"secret": "must-not-appear"})
            writer.append("runtime", {"value": 2})
            writer.append("spark", {"stage": 3})
            writer.close()

            summary = inspect_bundle(root)

            self.assertEqual(
                {
                    "discardedTailBytes": 0,
                    "recordTypes": {"runtime": 2, "spark": 1},
                    "records": 3,
                    "recovered": False,
                    "state": "FINAL",
                },
                summary,
            )
            self.assertNotIn("secret", json.dumps(summary))

    def test_open_bundle_requires_explicit_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            writer = DiagnosticBundleWriter(root)
            writer.append("runtime", {"value": 1})

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                result = cli.main(["bundle-inspect", str(root)])

            self.assertEqual(2, result)
            self.assertIn("pass --recover-open", stderr.getvalue())
            writer.close()

    def test_open_bundle_cli_recovers_only_complete_records_and_reports_tail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            writer = DiagnosticBundleWriter(root)
            writer.append("runtime", {"value": 1})
            segment = root / "events.jsonl"
            with segment.open("ab") as stream:
                stream.write(b'{"recordType":"runtime"')

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = cli.main(["bundle-inspect", str(root), "--recover-open"])

            self.assertEqual(0, result)
            summary = json.loads(stdout.getvalue())
            self.assertEqual("OPEN", summary["state"])
            self.assertTrue(summary["recovered"])
            self.assertEqual(1, summary["records"])
            self.assertEqual({"runtime": 1}, summary["recordTypes"])
            self.assertGreater(summary["discardedTailBytes"], 0)
            writer.close()


if __name__ == "__main__":
    unittest.main()
