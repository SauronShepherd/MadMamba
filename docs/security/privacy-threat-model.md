# Privacy threat model and data-class inventory

Task: **R0-ADR-003**  
Requirements: **FR-CFG-008**, **SEC-012**

MadMamba treats application correctness, secrets, payload data, target-process control, output integrity, browser/viewer safety, plugin supply chain, and comparison validity as protected assets. The privacy boundary is local-first and fail-closed: classification and redaction happen before strings enter registries, metric keys, logs, errors, caches, reports, temporary artifacts, bundles, or exports.

The machine-readable source of truth is `privacy/data-class-inventory.json`. It classifies every leaf in the v1.5 core configuration example and the baseline report/bundle examples, including the currently implemented bundle/report summary. An unlisted field is not implicitly safe: the validator rejects it until the baseline is reviewed.

## Data handling classes

**Allowed** data is bounded structural, numeric, version, capability, and completeness metadata. **Sensitive** data is permitted only through the documented reduced representation: code identity, project-relative or keyed-HMAC path identity, fingerprints, run/process/interpreter identities, and allow-listed low-cardinality tags. **Prohibited** data is blocked by default: arguments/returns, object or serialized payloads, SQL/expressions/literals/raw paths, Py4J bodies, protobuf bodies, exception messages/locals/tracebacks/source, environment values, credentials/headers, worker log messages, and raw user/request/query IDs or UUIDs as dimensions.

Hashing is not redaction. Raw sensitive paths or identifiers must not be converted to plain unsalted hashes and called private. Where identity is needed, use project-relative identity or keyed HMAC with a run-local key; stable cross-run linkage requires explicit policy because it increases linkage risk.

## Threats and controls

The main privacy failures are accidental payload capture, secret-bearing strings entering cardinality registries before filtering, unsafe path/identifier persistence, imported protocol bodies becoming evidence, and later report/viewer export re-exposing data. Controls are classification before interning, deny-by-default field review, bounded safe metadata, explicit reduced sensitive representations, sanitizer boundaries, local-only defaults, and privacy-canary tests.

## Canary strategy

Every prohibited class has its own synthetic fixture ID in the inventory. A fixture is injected only in test data; the marker must be absent from **logs, reports, caches, temporary files, bundles, and viewer exports** after the privacy boundary. Fixture IDs describe the strategy without embedding real credentials or secret-like payload values in repository documentation.

## Scope and limitations

This R0 task establishes the privacy classification contract and executable inventory validator. It does not claim that the full R1 immutable configuration model exists yet; FR-CFG-008 is satisfied here only for the sensitivity/classification dimension. Defaults, ranges, dynamic/static status, and affected-capability metadata remain R1-CFG-001 work. Runtime parity and free-threaded execution are not applicable because this task changes policy metadata, documentation, and development validation only.
