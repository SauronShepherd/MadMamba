# ADR-0001: Use one runtime kernel per interpreter
Status: Accepted
Date: 2026-09-02
Task: R0-ADR-002
Requirements: FR-LIF-010, FR-INT-008
Supersedes: None
Superseded-By: None

## Context

MadMamba must report interpreter-local truth. Multiple CPython interpreters can own independent imports, hooks, and lifetimes. A mutable process singleton would blur ownership of monitoring state, cleanup, configuration, and evidence identity. Process-scoped coordination is still needed for process identity, output ownership, at-fork handling, and interpreter registration.

## Decision

MadMamba will create one independent runtime kernel for each instrumented interpreter. Each kernel owns its lifecycle, configuration generation, monitoring lease, callbacks, target registry, adapters, reentrancy state, contexts, metric shards, flight recorder, capability registry, snapshot participation, and interpreter identity. A lightweight process coordinator may coordinate process-scoped resources, but it must not substitute for interpreter-local ownership. Execution in an interpreter that was not bootstrapped is reported as a coverage gap instead of being attributed to another kernel.

## Alternatives

A single process singleton was rejected because interpreter-local hooks, imports, and mutable state cannot be represented safely as one shared runtime. A shared kernel partitioned by interpreter was rejected for the stable reference implementation because it increases cross-interpreter synchronization and lifetime hazards. Observing only the main interpreter was rejected because it would hide known coverage gaps.

## Consequences

Interpreter identity, hook ownership, cleanup, and coverage become explicit and testable. The design does not rely on GIL serialization and can evolve toward free-threaded execution. Costs include per-interpreter retained state, explicit process coordination, subinterpreter bootstrap work, and stricter lifecycle testing. Cross-interpreter correlation must use explicit evidence identifiers rather than Python object identity.
