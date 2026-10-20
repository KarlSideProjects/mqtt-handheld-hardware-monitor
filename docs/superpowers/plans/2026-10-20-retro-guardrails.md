# Retrospective guardrails implementation plan

> **For agentic workers:** Implement inline using executing-plans; use test-driven-development and a final independent review.

**Goal:** Implement the six accepted retrospective improvements without disrupting the stable deployed devices.

**Architecture:** Extend the existing device CLI and local CI tests. Add small Git checkout and immutable source-build commands; keep agent instructions as navigation to their workflow guide.

**Tech Stack:** Python standard library, existing Git/Docker/SSH commands, unittest and existing CI.

**Spec:** All six recommendations in the accepted retrospective in this session.

## Global constraints

- Preserve existing MQTT/PVE configuration, UI update recovery, SSH host-key validation and secret-free output.
- Do not restart live devices during implementation; lifecycle tests use a controlled process/filesystem boundary.
- Local commits are allowed; do not push or merge.
- Use existing `python3 scripts/check.py --layout` and sender `make check`; add no dependency.

## Review focus

- A failed or conflicting launch cannot kill an unrelated process or overwrite a stock queue.
- Renderer errors after launch fail verification even when HTTP and MQTT are healthy.
- SSH errors must not echo arbitrary stderr, credentials or command bodies.
- Detached/stale checkout and failed fetch must report uncertainty explicitly.
- A dirty/changed revision or failed check cannot produce a successful build manifest.

## Tasks

- [x] Extend diagnostics and SSH errors: Docker fields and provider; allowlisted authentication/host-key/network/remote-Python error codes. Add failing tests, implement and verify existing tests.
- [x] Add `device.py restart`: safe existing-monitor stop, stock TrimUI queue handoff, existing R36 Ports launcher, bounded single-renderer/MQTT/pageflip validation. Test process identity, queue collisions, ordering and failure recovery before implementation.
- [x] Add real HTTP entry matrix for PVE/Docker/metric/detail/back and negative requests to existing transport tests; keep renderer-only tests lightweight.
- [x] Add `checkout.py`: optional fetch, actual default remote branch, branch/head/ahead/behind/dirty summary, no automatic checkout or merge. Test against temporary real repositories.
- [x] Add `release.py`: clean fixed Git revision, run supplied check command, archive committed source, build image with revision label, record immutable image ID and check/source hashes privately. Test failure paths with real Git and controlled external Docker boundary.
- [x] Wire tests into existing CI runner; add concise agent workflow pointer and tool-output guidance; update device operations documentation.
- [x] Run full checks, request independent review, fix findings, commit guardrails and create a source/check/image manifest without changing running containers.

## Verification record

- `python3 scripts/check.py --layout`: passed, including real HTTP navigation, checkout/release failure paths, 13 restart tests and both display layouts.
- Independent review: fixed asynchronous renderer cleanup and missing-log false success; reviewer confirmed fixes and 13 restart tests.
- Sender `make check`: 168 passed, 1 skipped (PowerShell unavailable).
- Built sender commit `0eaa7e485cdf2013d3b5c8a28e60b06e6e7f3ea2` from its Git archive. Private manifest: `/home/karl/.local/state/hwmonitor/docker-release-20261020-retro/manifest.json`.
- Image ID: `sha256:1c8f5d2368bf7b52d62c64b77492b59ee99eaab12d50f68ed280b2751d24b6ba`; manifest records source/check/archive hashes. This image has not been deployed.
- Live diagnostics were read-only. The new restart command has controlled-boundary tests; it has not been run on live hardware. No push or merge.
