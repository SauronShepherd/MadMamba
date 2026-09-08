from __future__ import annotations

from madmamba import DiagnosticBundleReader, DiagnosticBundleWriter, InterpreterRuntimeLifecycle


def test_managed_runtime_emits_bounded_lifecycle_records(tmp_path) -> None:
    lifecycle = InterpreterRuntimeLifecycle()
    bundle = tmp_path / "bundle"

    with DiagnosticBundleWriter(bundle) as writer:
        with lifecycle.managed(interpreter_key=73, diagnostic_writer=writer) as kernel:
            assert kernel.interpreter_key == 73
            assert lifecycle.status(73).kernel_live is True

    records = DiagnosticBundleReader(bundle).read_records()

    assert [record["recordType"] for record in records] == [
        "runtime.started",
        "runtime.stopped",
    ]
    assert [record["sequence"] for record in records] == [1, 2]
    for record in records:
        assert set(record["payload"]) == {
            "interpreterKey",
            "kernelLive",
            "monitoringAttached",
            "monitoringDegraded",
            "monitoringEvents",
            "monitoringToolId",
        }
        assert record["payload"]["interpreterKey"] == 73
        assert record["payload"]["kernelLive"] is True
        assert "locals" not in record["payload"]
        assert "arguments" not in record["payload"]

    assert lifecycle.status(73).kernel_live is False


def test_managed_runtime_without_writer_preserves_existing_behavior() -> None:
    lifecycle = InterpreterRuntimeLifecycle()

    with lifecycle.managed(interpreter_key=91) as kernel:
        assert kernel.interpreter_key == 91
        assert lifecycle.status(91).kernel_live is True

    assert lifecycle.status(91).kernel_live is False
