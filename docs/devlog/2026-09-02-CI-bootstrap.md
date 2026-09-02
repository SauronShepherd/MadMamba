# 2026-09-02 — GitHub Actions CI Bootstrap

## Selected engineering task

**GitHub Actions CI bootstrap and repair.** This infrastructure task is required by Technical Architecture v1.5 §44 (cross-release CI and certification matrix) but is not assigned a standalone roadmap task ID in the v1.5 R0/R1 tables. No synthetic specification task ID is invented.

## Specification mapping

- Technical Architecture v1.5 §44.1: CPython 3.12/3.13/3.14, free-threaded builds where available, and Python 3.15 preview axes.
- Technical Architecture v1.5 §44.2: Linux, macOS, and Windows platform axes.
- Technical Architecture v1.5 §44.4: every-PR and merge/main test scheduling.
- Technical Architecture v1.5 §37.3: stage gates require applicable cumulative tests and no mandatory skipped gates.
- Technical Architecture v1.5 §46: remote CI results must be bound to the commit/environment/artifact evidence used for certification.

## Repository state before change

- `main` head: `f6d369aa8b9f6186c9969c987e038a8413375c06`.
- No `.github/workflows` directory existed.
- No workflow runs or commit status checks existed for the current head.
- `main` is currently unprotected, so this change does not claim branch-protection enforcement.

## Implementation summary

- Added `.github/workflows/ci.yml` with `push` to `main`, `pull_request` to `main`, and manual dispatch triggers.
- Added a 12-lane matrix:
  - Linux: CPython 3.12, 3.13, 3.14, 3.13t, 3.14t, and 3.15-dev.
  - macOS: CPython 3.12, 3.13, and 3.14.
  - Windows: CPython 3.12, 3.13, and 3.14.
- Every lane runs the current R0 traceability validator, ADR linter, complete unittest suite, Python bytecode compilation, and JSON parsing checks.
- Added a 10-minute per-job timeout and `fail-fast: false` so one compatibility failure does not hide evidence from other lanes.
- Restricted workflow token permissions to `contents: read`.
- Pinned GitHub-owned actions to exact commit SHAs resolved from their current v7 tags:
  - `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1`.
  - `actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97`.
- No third-party actions, secrets, package installs, or external test dependencies were added.

## Local pre-push verification

A local static validator parsed the workflow with PyYAML and asserted:

- workflow name and all three triggers;
- read-only repository permissions;
- exactly 12 expected OS/Python lanes;
- exact lane membership;
- both action references are pinned to 40-character hexadecimal commit SHAs;
- no workflow-level write permission is requested.

Result: **PASS**.

The existing repository source was not modified by this infrastructure task. The authoritative cumulative execution of existing validators/tests is therefore the post-push GitHub Actions matrix run created by this commit.

## Security and privacy

- Workflow token is read-only.
- GitHub-owned actions are commit-pinned rather than floating major tags.
- No secrets are referenced.
- No arbitrary downloaded scripts, package installation, network test fixtures, telemetry, or artifact upload is introduced.
- Existing privacy-canary tests remain part of every matrix lane.

## Performance / boundedness

- CI jobs have a hard 10-minute timeout.
- The matrix is explicitly bounded to 12 lanes.
- This infrastructure-only task has no application runtime benchmark threshold; no runtime performance certification is claimed.

## Known limitations

- Package, viewer, semantic-parity, attach, Spark, Arrow, and adapter-specific jobs are not fabricated before those components exist. They must be added when their roadmap tasks become implementable and their corresponding gates become applicable.
- Scheduled nightly/weekly suites are not enabled yet because their target runtime/adapters/performance campaigns do not exist in the current R0 repository.
- Branch protection is currently disabled and is not silently changed by this task.

## Commit / branch / CI

- Target branch: `main`.
- Commit: the commit containing this report; exact SHA is reported after publication because a Git commit cannot embed its own final hash.
- Post-push CI: must be inspected immediately after publication. This report does not pre-claim a green remote result.

## Next recommended roadmap task

**R0-ADR-003 — Privacy threat model and data-class inventory.**
