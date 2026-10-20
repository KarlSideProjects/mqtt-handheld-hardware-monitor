# Monitoring environment implementation plan

> **For agentic workers:** Use subagent-driven-development or executing-plans to implement each task with tests and independent review.

**Goal:** Make installation, checks and handheld updates reproducible and verify the running result.

**Architecture:** Keep sender checks in the sender repository and handheld checks and operations in this repository. Reuse the existing test scripts, SSH transport conventions and browser runtime; store credentials outside Git. Hardware checks run only when explicitly requested and after device preflight.

**Tech stack:** Python standard library, systemd, MQTT, shell, Playwright and GitHub Actions.

**Spec:** The five retrospective improvements accepted by the user: actual installation smoke test, CI, complete device update, separated test environments and concise device operations/diagnostics.

## Global constraints

- Preserve existing private configuration, user edits and active navigation.
- Public CI uses GitHub-hosted runners, read-only permissions, pinned actions and no device credentials.
- Local checks never run physical input, backlight or sleep tests.
- A successful update requires backup, atomic replacement, browser reload, expected loaded revision and continuing MQTT observations.
- Diagnostics whitelist metadata; never print passwords, tokens, raw environment or full metric histories.

## Review focus

- A restrictive umask must not prevent the service identity from importing installed packages.
- Failed or stale browser reload must fail the update, even if files have the correct hash.
- Wrong devices, offline monitors and missing prerequisites fail before changing device state.
- Update failure restores application files and reloads the prior application when possible, reporting recovery separately.
- Public PR code cannot reach credentials or an internal network runner.

## Task 1: Sender installation and CI

**Ownership:** Sender worktree `/home/karl/orca/workspaces/hwmonitor-mqtt/retro-sender-checks`.

**Files:** `.github/workflows/ci.yml`, development dependencies/check entry point, `tests/integration/` or `scripts/` smoke test, README verification instructions.

- [ ] Add a real native-install smoke check under `umask 077`: actual venv/pip, unprivileged systemd service and a private local broker observation. Use temporary fixture configuration, no live PVE account or production secrets.
- [ ] Keep the existing mocked regression tests and add meaningful failure coverage for the smoke harness.
- [ ] Add a reproducible check command, declare its dependencies and run existing tests on supported Python versions including 3.13.
- [ ] Add SHA-pinned, read-only Actions jobs for checks and a bounded systemd/MQTT integration smoke check.
- [ ] Run checks and obtain independent review before publication.

## Task 2: Display test entry points and CI

**Ownership:** Display test/config files; parent owns README, AGENTS and device operations.

**Files:** `scripts/check*`, pinned Node package manifest/lock, `.github/workflows/ci.yml`, hardware test preflight, runner tests.

- [ ] Write a regression proving the local entry point excludes live-device scripts.
- [ ] Provide explicit local and device test commands, with clear device preflight and bounded execution.
- [ ] Declare and lock Playwright dependencies; run existing JavaScript tests and both 1024x768 and 1280x720 layouts without `/tmp` dependencies.
- [ ] Add read-only, SHA-pinned Actions checks with no hardware runner or device secrets.
- [ ] Run checks and obtain independent review.

## Task 3: Complete handheld update, diagnostics and navigation

**Ownership:** Parent; `browser/device_ops.py`, related tests, browser loaded-revision handshake, README, `docs/agents/device-operations.md` and minimal AGENTS navigation.

**Interfaces:** `python3 scripts/device.py diagnose|update --device r36|trimui --host IP`; optional explicit SSH user/identity and private authentication inherited from SSH environment.

- [ ] Test concise diagnostic output and secret/history exclusion.
- [ ] Test update preflight, backup and atomic replacement, reload acknowledgement, MQTT freshness and rollback failure reporting using controlled transports.
- [ ] Implement runtime revision reporting for the page, with R36 and TrimUI reload adapters that reuse their current X11/CDP runtimes.
- [ ] Keep device operations separate from platform-neutral release validation and reuse existing modules where possible.
- [ ] Document addresses as environment examples, application paths, port 8766, authentication, commands, backup and rollback. Add one conditional AGENTS pointer without incorporating unrelated untracked instructions.
- [ ] Run local tests; run diagnose and idempotent update on both authorized devices; verify loaded revision and continuing observations without changing selected host/guest.
- [ ] Independently review the full changes, publish PRs, observe CI, merge using the existing authorization and verify the final installed revisions.
