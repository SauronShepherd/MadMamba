from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from madmamba import cli
from madmamba.bundle_reader import DiagnosticBundleIntegrityError


class ReportCliTests(unittest.TestCase):
    def test_report_json_reuses_bounded_bundle_summary(self) -> None:
        payload = {
            "state": "FINAL",
            "recovered": False,
            "records": 3,
            "recordTypes": {"event": 2, "lifecycle": 1},
            "discardedTailBytes": 0,
        }
        output = io.StringIO()
        with patch.object(cli, "inspect_bundle", return_value=payload) as inspect, redirect_stdout(output):
            self.assertEqual(cli.main(["report", "bundle", "--json"]), 0)

        inspect.assert_called_once_with("bundle", recover_open=False)
        self.assertEqual(json.loads(output.getvalue()), payload)

    def test_report_human_output_stays_aggregate(self) -> None:
        payload = {
            "state": "OPEN",
            "recovered": True,
            "records": 2,
            "recordTypes": {"event": 2},
            "discardedTailBytes": 17,
        }
        output = io.StringIO()
        with patch.object(cli, "inspect_bundle", return_value=payload) as inspect, redirect_stdout(output):
            self.assertEqual(cli.main(["report", "bundle", "--recover-open"]), 0)

        inspect.assert_called_once_with("bundle", recover_open=True)
        rendered = output.getvalue()
        self.assertIn("state: OPEN", rendered)
        self.assertIn("records: 2", rendered)
        self.assertIn("event: 2", rendered)
        self.assertIn("recovered: yes", rendered)
        self.assertIn("discarded tail bytes: 17", rendered)

    def test_report_integrity_failure_preserves_exit_contract(self) -> None:
        error = DiagnosticBundleIntegrityError("checksum mismatch")
        stderr = io.StringIO()
        with patch.object(cli, "inspect_bundle", side_effect=error), redirect_stderr(stderr):
            self.assertEqual(cli.main(["report", "bundle", "--json"]), 2)

        self.assertIn("bundle integrity error", stderr.getvalue())
        self.assertIn("checksum mismatch", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
