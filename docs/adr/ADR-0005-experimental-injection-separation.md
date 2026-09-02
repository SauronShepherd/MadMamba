# ADR-0005: Isolate source and bytecode injection from the stable core
Status: Accepted
Date: 2026-09-02
Task: R0-ADR-002
Requirements: NFR-SEM-001
Supersedes: None
Superseded-By: None

## Context

Source AST transformation and sourceless bytecode rewriting can provide narrow observability that runtime hooks cannot, but they carry materially higher compatibility, exception-table, semantic-parity, and supply-chain risk. The v1.5 release scope excludes source and .pyc transformation from stable 0.1 and defines a separately published experimental track.

## Decision

Stable MadMamba will not perform source AST transformation or .pyc rewriting. Injection capabilities, if implemented, live in the separately named madmamba-experimental package or experimental tree, remain disabled by default, use explicit feature flags and schemas where needed, and do not become stable merely because code exists. Stable adapters may use documented runtime hooks, wrappers, post-import discovery, and delegated evidence sources instead.

## Alternatives

Shipping transformation inside the stable package behind a hidden switch was rejected because installation alone would blur the trust boundary. Rewriting .pyc files as a fallback was rejected because CPython-minor fragility and exception-table corruption risk are incompatible with the stable semantic-preservation contract. Abandoning experimental research entirely was rejected because some future diagnostics may justify explicit opt-in transformation after separate certification.

## Consequences

The stable package keeps a narrower semantic and supply-chain risk profile, while experimental work can evolve under separate gates. Some exact expression or call-site diagnostics will remain unavailable in stable releases. Experimental features require independent schemas, parity testing, compatibility claims, and promotion evidence before any future stable adoption.
