# ADR-0003: Store diagnostics as a versioned manifest plus typed JSONL records
Status: Accepted
Date: 2026-09-02
Task: R0-ADR-002
Requirements: FR-RPT-001, FR-RPT-003, FR-RPT-005
Supersedes: None
Superseded-By: None

## Context

MadMamba needs recoverable local output that can represent multiple processes and interpreters, schema evolution, partial failure, imported evidence, and bounded streaming writes. One monolithic snapshot object would make crash-tail recovery, rotation, provenance, and incremental analysis difficult.

## Decision

The diagnostic bundle will be versioned by a manifest and schema-versioned typed records. Runtime components write newline-delimited JSON records so complete lines remain independently parseable. JSON encoding rejects NaN and infinity and uses declared integer and encoding limits. Rotation, checksums, sequence metadata, and recovery must distinguish complete records from partial or corrupt tails. Imported evidence remains source-identified rather than being rewritten as direct observation.

## Alternatives

A single JSON document was rejected because interrupted writes make the whole document difficult to recover and append. An opaque binary-only format was rejected as the stable core interchange because it raises implementation and migration cost before the schema is mature. A database as the primary bundle was rejected because it adds a runtime dependency and a larger hostile-input surface for a local diagnostic artifact.

## Consequences

Writers and readers can recover complete records after interruption, rotate bounded segments, and evolve record types independently. The format remains inspectable with standard tooling. Costs include explicit manifest/schema management, sequence and migration rules, and the need to validate every record family rather than relying on one broad snapshot schema.
