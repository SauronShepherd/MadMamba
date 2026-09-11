from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from madmamba.bundle_recovery import DiagnosticBundleRecovery


_INTERRUPTED_WRITER = r'''
import os
import sys
import time
from pathlib import Path

from madmamba.bundle import DiagnosticBundleWriter


class BlockingPartialStream:
    def __init__(self, wrapped, marker: Path) -> None:
        self._wrapped = wrapped
        self._marker = marker

    def write(self, data: bytes) -> int:
        prefix = data[: max(1, len(data) // 2)]
        written = self._wrapped.write(prefix)
        self._wrapped.flush()
        os.fsync(self._wrapped.fileno())
        self._marker.write_text(str(written), encoding="ascii")
        while True:
            time.sleep(60)

    def __getattr__(self, name: str):
        return getattr(self._wrapped, name)


root = Path(sys.argv[1])
marker = Path(sys.argv[2])
writer = DiagnosticBundleWriter(root)
writer.write("runtime.event", {"phase": "complete"})
writer._segment = BlockingPartialStream(writer._segment, marker)
writer.write("runtime.event", {"phase": "interrupted", "value": "x" * 4096})
'''


class DiagnosticBundleInterruptionTests(unittest.TestCase):
    def test_recovers_after_process_is_killed_during_record_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "bundle"
            marker = Path(directory) / "partial-write.ready"
            process = subprocess.Popen(
                [sys.executable, "-c", _INTERRUPTED_WRITER, str(root), str(marker)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.monotonic() + 10.0
                while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                if not marker.exists():
                    stdout, stderr = process.communicate(timeout=1)
                    self.fail(
                        "interruption fixture did not reach the partial-write boundary; "
                        f"stdout={stdout!r} stderr={stderr!r} returncode={process.returncode}"
                    )

                process.kill()
                process.wait(timeout=5)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)

            recovered = DiagnosticBundleRecovery(root).recover()

            self.assertEqual([record["sequence"] for record in recovered.records], [1])
            self.assertGreater(recovered.discarded_tail_bytes, 0)
            self.assertGreater(int(marker.read_text(encoding="ascii")), 0)


if __name__ == "__main__":
    unittest.main()
