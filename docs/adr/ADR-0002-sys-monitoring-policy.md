# ADR-0002: Prefer sys.monitoring with non-destructive coexistence
Status: Accepted
Date: 2026-09-02
Task: R0-ADR-002
Requirements: FR-MON-001, FR-MON-010, FR-MON-011
Supersedes: None
Superseded-By: None

## Context

The stable runtime needs deterministic method lifecycle evidence without replacing debuggers, coverage tools, profilers, or tracing hooks. CPython exposes a bounded set of sys.monitoring tool IDs and event scopes whose semantics differ by interpreter version. Callback failures and free-threaded execution also make implicit GIL serialization unacceptable.

## Decision

Stable MadMamba will prefer sys.monitoring. It will lease only an available tool ID, never evict or free another tool's ID, register callbacks before enabling events, prefer per-code local events where supported, and report conflicts or unsupported event scope as capability degradation. Existing tracing, profiling, debugger, JIT, and trampoline state is detected rather than overwritten by default. Shared state used by callbacks must have an explicit synchronization or immutability contract.

## Alternatives

Replacing sys.setprofile or sys.settrace globally was rejected as the stable default because it is more invasive and can destroy ownership semantics. Clearing an occupied monitoring ID was rejected as non-cooperative. Bytecode/source rewriting was rejected for stable monitoring because it increases semantic and version fragility. A setprofile fallback remains possible only as an explicit degraded capability.

## Consequences

The monitoring backend has explicit coexistence and ownership semantics and can fail open when no safe ID or event plan is available. Version-specific event tests and free-threaded stress become mandatory for implementation claims. Some evidence will be unavailable or broader in scope on older interpreters, and those gaps must remain visible rather than being hidden by unsafe fallback behavior.
