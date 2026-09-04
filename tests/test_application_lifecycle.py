from __future__ import annotations

from madmamba import application_lifecycle, managed_application_runtime
from madmamba.cli import doctor_payload


def test_application_lifecycle_is_stable_and_lazy() -> None:
    first = application_lifecycle()
    second = application_lifecycle()

    assert first is second
    assert first.status().kernel_live is False


def test_doctor_observes_shared_managed_runtime() -> None:
    lifecycle = application_lifecycle()
    assert lifecycle.status().kernel_live is False

    with managed_application_runtime() as kernel:
        payload = doctor_payload()
        runtime = payload["runtimeLifecycle"]

        assert kernel.live is True
        assert runtime["kernelLive"] is True
        assert runtime["monitoringAttached"] is False
        assert runtime["monitoringDegraded"] is True

    assert lifecycle.status().kernel_live is False
