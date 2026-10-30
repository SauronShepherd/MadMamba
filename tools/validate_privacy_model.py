#!/usr/bin/env python3
"""Validate MadMamba's R0 privacy threat-model field inventory."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

TASK_ID = "R0-ADR-003"
SCHEMA_VERSION = "1.0.0"
CATEGORIES = {"allowed", "sensitive", "prohibited"}
REQUIRED_CANARY_SINKS = {
    "logs", "reports", "caches", "temp-files", "bundles", "viewer-exports"
}
MAX_FILE_BYTES = 256 * 1024
MAX_CLASSES = 128
MAX_FIELDS = 512
MAX_TEXT = 1000
PATH_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:\[\])?(?:\.(?:[A-Za-z][A-Za-z0-9]*(?:\[\])?|\*))*$")
CLASS_ID_RE = re.compile(r"^(?:safe|sensitive|prohibited)\.[a-z0-9-]+$")

# Normative leaf fields from Technical Architecture v1.5 sections 30-31,
# plus the currently implemented bundle/report envelope. Paths use [] for list
# members and * only for bounded mapping keys explicitly described by the spec.
BASELINE_CONFIG_FIELDS = frozenset({
    "schemaVersion", "enabled", "preset",
    "run.id", "run.name", "run.role", "run.staticTags.*",
    "runtime.backend", "runtime.fallbackBackend", "runtime.toolIdPolicy",
    "runtime.coexistencePolicy", "runtime.subinterpreters", "runtime.freeThreaded",
    "runtime.jitPolicy", "runtime.panicFuse.maxErrorsPerComponent",
    "attach.enabled", "attach.safeRemoteExecOnly", "attach.ackTimeoutSeconds",
    "attach.temporaryDirectory",
    "selection.includeModules", "selection.excludeModules", "selection.includeFunctions",
    "selection.excludeFunctions", "selection.dynamicDiscovery.enabled",
    "selection.dynamicDiscovery.maxEventsPerSecond", "selection.dynamicDiscovery.maxNewCodes",
    "probes.methods.enabled", "probes.methods.activeWallDuration",
    "probes.methods.activeThreadCpuDuration", "probes.methods.suspendedInstanceTracking",
    "probes.methods.histogram", "probes.exceptions.enabled", "probes.exceptions.raised",
    "probes.exceptions.reraised", "probes.exceptions.handled", "probes.exceptions.unwind",
    "probes.exceptions.unhandled", "probes.exceptions.unraisable", "probes.exceptions.messages",
    "probes.exceptions.stackFingerprint", "probes.nativeCalls.enabled",
    "probes.nativeCalls.include", "probes.nativeCalls.maxEventsPerSecond",
    "adapters.plugins.enabled", "adapters.plugins.allow", "adapters.serialization.enabled",
    "adapters.arrow.enabled", "adapters.arrow.objects", "adapters.arrow.memoryPool",
    "adapters.arrow.conversions", "adapters.arrow.ipc", "adapters.arrow.cDataInterface",
    "adapters.arrow.device", "adapters.spark.enabled", "adapters.spark.mode",
    "adapters.spark.builtInProfilerPolicy", "adapters.spark.classic.semantic",
    "adapters.spark.classic.py4j", "adapters.spark.classic.wireBytes",
    "adapters.spark.connect.semantic", "adapters.spark.connect.grpc",
    "adapters.spark.connect.planShape", "adapters.spark.workers.enabled",
    "adapters.spark.workers.bootstrap", "adapters.spark.workers.taskContext",
    "adapters.spark.madlava.enabled", "adapters.spark.madlava.agentPath",
    "adapters.spark.madlava.onUnavailable", "evidence.importers.sparkRest",
    "evidence.importers.sparkEventLog", "evidence.importers.sparkMetrics",
    "evidence.importers.pysparkProfiles", "evidence.importers.tachyon", "evidence.importers.os",
    "metrics.maxMetricKeys", "metrics.maxTargets", "metrics.maxTypes",
    "metrics.maxStackFingerprints", "metrics.maxTagSets", "metrics.maxStringBytes",
    "metrics.shards", "metrics.overflowPolicy", "budget.mode", "budget.targetOverheadPercent",
    "budget.hardOverheadPercent", "budget.maxResidentBytes", "budget.evaluationIntervalSeconds",
    "budget.allowUpshift", "flightRecorder.enabled", "flightRecorder.maxEvents",
    "flightRecorder.maxAgeSeconds", "flightRecorder.triggers.unhandledException",
    "flightRecorder.triggers.latencyNs", "flightRecorder.triggers.sparkTaskFailure",
    "output.directory", "output.bundle", "output.snapshotIntervalSeconds", "output.queueCapacity",
    "output.queueOverflowPolicy", "output.rotateBytes", "output.maxFiles", "output.permissions",
    "output.fsync", "output.shutdownTimeoutSeconds", "privacy.mode", "privacy.captureArguments",
    "privacy.captureReturnValues", "privacy.capturePayloads", "privacy.captureExceptionMessages",
    "privacy.captureSqlText", "privacy.captureWorkerLogMessages", "privacy.pathIdentity",
    "privacy.stableCrossRunIdentity", "privacy.tagAllowList",
})

BASELINE_REPORT_FIELDS = frozenset({
    # v1.5 manifest example
    "bundle.bundleFormat", "bundle.bundleId", "bundle.schemaSet", "bundle.createdAt",
    "bundle.run.runId", "bundle.run.name", "bundle.privacy.mode", "bundle.privacy.stableLinkage",
    "bundle.components[].componentInstanceId", "bundle.components[].runtime", "bundle.components[].role",
    "bundle.components[].processInstanceId", "bundle.components[].interpreterInstanceId",
    "bundle.components[].records", "bundle.components[].checksum", "bundle.imports",
    "bundle.incomplete", "bundle.warnings",
    # v1.5 metric snapshot example
    "metric.schemaVersion", "metric.recordType", "metric.sequence", "metric.snapshotId",
    "metric.previousSnapshotId", "metric.componentInstanceId", "metric.processInstanceId",
    "metric.interpreterInstanceId", "metric.window.startMonotonicNs", "metric.window.endMonotonicNs",
    "metric.window.wallEnd", "metric.temporality", "metric.metrics[].descriptorId",
    "metric.metrics[].dimensions.targetId", "metric.metrics[].dimensions.tagSetId",
    "metric.metrics[].dimensions.outcome", "metric.metrics[].values.count",
    "metric.metrics[].values.sum", "metric.metrics[].values.max", "metric.metrics[].values.buckets",
    "metric.coverage.complete", "metric.coverage.droppedEvents", "metric.coverage.overflowKeys",
    # currently implemented report/bundle summary surface
    "report.state", "report.recovered", "report.records", "report.recordTypes.*",
    "report.discardedTailBytes", "currentManifest.bytes", "currentManifest.files[].bytes",
    "currentManifest.files[].path", "currentManifest.files[].records", "currentManifest.files[].sha256",
    "currentManifest.format", "currentManifest.manifestVersion", "currentManifest.records",
    "currentManifest.state", "record.payload.*", "record.recordType", "record.schemaVersion",
    "record.sequence",
})


class PrivacyModelError(ValueError):
    """Raised when the privacy inventory violates R0-ADR-003."""


def _load_bounded(path: Path) -> Any:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise PrivacyModelError(f"{path.name} exceeds {MAX_FILE_BYTES} bytes")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PrivacyModelError(f"{label} must be a non-empty string")
    if len(value) > MAX_TEXT:
        raise PrivacyModelError(f"{label} exceeds {MAX_TEXT} characters")
    return value


def validate_inventory(data: Any) -> None:
    if not isinstance(data, dict):
        raise PrivacyModelError("inventory root must be an object")
    expected_root = {"schemaVersion", "task", "requirements", "dataClasses", "fieldGroups"}
    if set(data) != expected_root:
        raise PrivacyModelError(f"inventory root fields must be exactly {sorted(expected_root)}")
    if data["schemaVersion"] != SCHEMA_VERSION:
        raise PrivacyModelError("unsupported schemaVersion")
    if data["task"] != TASK_ID:
        raise PrivacyModelError(f"task must be {TASK_ID}")
    requirements = data["requirements"]
    if requirements != ["FR-CFG-008", "SEC-012"]:
        raise PrivacyModelError("requirements must be exactly FR-CFG-008 and SEC-012")

    classes = data["dataClasses"]
    field_groups = data["fieldGroups"]
    if not isinstance(classes, list) or not classes or len(classes) > MAX_CLASSES:
        raise PrivacyModelError("dataClasses must be a bounded non-empty list")
    if not isinstance(field_groups, dict) or set(field_groups) != {"config", "report"}:
        raise PrivacyModelError("fieldGroups must contain exactly config and report")

    by_id: dict[str, dict[str, Any]] = {}
    prohibited_ids: set[str] = set()
    for index, item in enumerate(classes):
        label = f"dataClasses[{index}]"
        if not isinstance(item, dict):
            raise PrivacyModelError(f"{label} must be an object")
        required = {"id", "category", "description"}
        allowed = required | {"canaryStrategy"}
        if not required.issubset(item) or set(item) - allowed:
            raise PrivacyModelError(f"{label} has invalid fields")
        class_id = _text(item["id"], f"{label}.id")
        if not CLASS_ID_RE.fullmatch(class_id):
            raise PrivacyModelError(f"{label}.id is invalid")
        if class_id in by_id:
            raise PrivacyModelError(f"duplicate data class: {class_id}")
        category = _text(item["category"], f"{label}.category")
        if category not in CATEGORIES:
            raise PrivacyModelError(f"{label}.category is invalid")
        if not class_id.startswith(category + ".") and not (category == "allowed" and class_id.startswith("safe.")):
            raise PrivacyModelError(f"{class_id} prefix does not match category {category}")
        _text(item["description"], f"{label}.description")
        strategy = item.get("canaryStrategy")
        if category == "prohibited":
            prohibited_ids.add(class_id)
            if not isinstance(strategy, dict) or set(strategy) != {"fixtureId", "sinks", "assertion"}:
                raise PrivacyModelError(f"{class_id} requires a complete canaryStrategy")
            _text(strategy["fixtureId"], f"{class_id}.fixtureId")
            _text(strategy["assertion"], f"{class_id}.assertion")
            sinks = strategy["sinks"]
            if not isinstance(sinks, list) or set(sinks) != REQUIRED_CANARY_SINKS or len(sinks) != len(set(sinks)):
                raise PrivacyModelError(f"{class_id} canary sinks must cover every required sink")
        elif strategy is not None:
            raise PrivacyModelError(f"{class_id} may not define canaryStrategy")
        by_id[class_id] = item

    field_keys: set[tuple[str, str]] = set()
    mapped: dict[str, set[str]] = {"config": set(), "report": set()}
    field_count = 0
    for surface in ("config", "report"):
        groups = field_groups[surface]
        if not isinstance(groups, dict) or not groups:
            raise PrivacyModelError(f"fieldGroups.{surface} must be a non-empty object")
        for class_id, paths in groups.items():
            _text(class_id, f"fieldGroups.{surface}.class")
            if class_id not in by_id:
                raise PrivacyModelError(f"fieldGroups.{surface} references unknown data class: {class_id}")
            if not isinstance(paths, list) or not paths:
                raise PrivacyModelError(f"fieldGroups.{surface}.{class_id} must be a non-empty list")
            for path in paths:
                field_count += 1
                if field_count > MAX_FIELDS:
                    raise PrivacyModelError("field count exceeds bound")
                path = _text(path, f"fieldGroups.{surface}.{class_id}.path")
                if not PATH_RE.fullmatch(path):
                    raise PrivacyModelError(f"field path is invalid: {path}")
                key = (surface, path)
                if key in field_keys:
                    raise PrivacyModelError(f"duplicate field mapping: {surface}:{path}")
                field_keys.add(key)
                mapped[surface].add(path)

    expected = {"config": BASELINE_CONFIG_FIELDS, "report": BASELINE_REPORT_FIELDS}
    for surface in ("config", "report"):
        missing = sorted(expected[surface] - mapped[surface])
        extra = sorted(mapped[surface] - expected[surface])
        if missing:
            raise PrivacyModelError(f"unclassified {surface} fields: {', '.join(missing[:8])}")
        if extra:
            raise PrivacyModelError(f"unknown {surface} fields require baseline review: {', '.join(extra[:8])}")

    # Acceptance requires a canary strategy for every prohibited class, even if
    # a class currently has no emitted field because it is blocked before capture.
    if not prohibited_ids:
        raise PrivacyModelError("at least one prohibited data class is required")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", nargs="?", type=Path, default=Path("privacy/data-class-inventory.json"))
    args = parser.parse_args(argv)
    try:
        data = _load_bounded(args.inventory)
        validate_inventory(data)
    except (OSError, UnicodeError, json.JSONDecodeError, PrivacyModelError) as exc:
        print(f"privacy model validation failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"privacy model validation passed: {sum(len(paths) for groups in data['fieldGroups'].values() for paths in groups.values())} fields, "
        f"{len(data['dataClasses'])} classes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
