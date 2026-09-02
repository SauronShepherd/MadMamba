# Architecture decision map

This document connects the R0-ADR-002 decision baseline to the v1.5 architecture and functional requirements.

| ADR | Architectural scope | Requirement anchors | Release claim |
|---|---|---|---|
| ADR-0001 | One runtime kernel per interpreter; process coordination stays narrow | FR-LIF-010, FR-INT-008 | 0.1 per-interpreter runtime identity and coverage |
| ADR-0002 | Preferred sys.monitoring backend, tool-ID ownership, coexistence and no-GIL assumptions | FR-MON-001, FR-MON-010, FR-MON-011 | 0.1 stable monitoring backend |
| ADR-0003 | Manifest plus typed, schema-versioned JSONL component records and crash-tail recovery | FR-RPT-001, FR-RPT-003, FR-RPT-005 | 0.1 diagnostic bundle |
| ADR-0004 | Offline viewer, hostile-input bounds, text rendering, no default network/runtime extensions | FR-RPT-006, FR-RPT-008, FR-RPT-009, SEC-019 | 0.1 local viewer |
| ADR-0005 | Source/.pyc transformation excluded from stable core and isolated to experimental track | NFR-SEM-001 plus v1.5 release-scope boundary | Experimental only; no stable 0.1 claim |

The source-transformation separation is a normative architecture/release-scope decision in v1.5. The functional specification does not assign that separation a dedicated FR identifier, so ADR-0005 links the semantic-preservation requirement and explicitly cites the release-scope boundary rather than inventing an ID.
