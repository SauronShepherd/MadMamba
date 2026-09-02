# ADR-0004: Make the viewer local-first and offline by default
Status: Accepted
Date: 2026-09-02
Task: R0-ADR-002
Requirements: FR-RPT-006, FR-RPT-008, FR-RPT-009, SEC-019
Supersedes: None
Superseded-By: None

## Context

Diagnostic bundles can contain sensitive operational metadata even after redaction. A viewer that depends on remote assets, telemetry, arbitrary extensions, or network APIs would expand the privacy boundary and make air-gapped incident analysis unreliable. Hostile or malformed bundles must also be treated as untrusted input.

## Decision

The default viewer will operate locally with no network requests and no external assets required for core use. Static export remains self-contained. Bundle parsing and rendering are bounded by input size, nesting, decompression, record, and rendering limits. User-controlled strings are rendered as text rather than injected HTML. The default query/runtime surface must not load remote modules, executable extensions, arbitrary SQL engines, or user-defined code.

## Alternatives

A hosted SaaS viewer was rejected as the default because it would require uploading evidence and network availability. CDN-hosted assets were rejected because they violate offline guarantees and introduce supply-chain/network dependencies. An unrestricted embedded query engine was rejected because it materially enlarges the hostile-input and code-execution surface.

## Consequences

Bundles remain analyzable in restricted and air-gapped environments, and privacy policy can be evaluated without trusting a remote service. The viewer must carry its own assets and enforce strict parser/rendering limits. Optional remote export may exist only as a separately governed capability and cannot be required for normal viewing.
