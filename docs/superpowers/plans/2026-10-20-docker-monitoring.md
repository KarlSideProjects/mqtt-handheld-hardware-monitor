# Docker monitoring implementation plan

> **For agentic workers:** Use executing-plans to implement these tasks in this session.

**Goal:** Browse a host's Docker containers and their status, CPU, RAM, network/disk rates and trends using the existing CT/VM controls.

**Architecture:** Add an optional `docker` v1 envelope beside `virtualization`, so both can coexist. A Linux collector reads only local Docker Engine GET endpoints in a background poller. Reuse the receiver inventory validation/history and the existing resource-list view, with provider-specific identity and metric semantics.

**Tech Stack:** Python standard library, existing MQTT sender, vanilla JavaScript, pytest and existing assert/Playwright checks.

**Spec:** User-approved scope in this conversation: host, Docker list, container details, status/CPU/RAM/network/disk/trends and existing controls.

## Global constraints

- Keep ordinary host and PVE messages compatible; no container control operations or new dependencies.
- Use full container IDs, never names as identity. Docker CPU uses 100% per core; RAM excludes inactive file cache.
- Enable Docker explicitly with `DOCKER_ENABLED=1`; local Unix socket only, configurable with `DOCKER_SOCKET`.
- Failed inventories preserve last successful data; no heartbeat-generated trend points; 30-second stale threshold and 262144-byte full-message limit.
- Socket access grants Docker daemon authority; do not automatically grant groups or mount the socket for existing installations.

## Review focus

- PVE and Docker coexist without overwriting each other's inventory or selection.
- Restart/counter reset/missing counters produce unknown rates, never spikes or invented zeroes.
- Partial API failures retain an atomic last-good inventory.
- Malformed identities, huge/nonfinite metrics and HTML names cannot escape validation/rendering.
- Both handheld viewports fit the two entry cards and container details.

## Task 1: Docker collector and sender

Files: add `hwmonitor_mqtt/clients/docker.py`, `hwmonitor_mqtt/collectors/docker.py`, `tests/test_docker_sender.py` in the sender worktree. Update `agents/agent_sender_async.py`, `.env.example`, and add opt-in `docker-compose.monitoring.yml`.

- [x] Write tests for real Unix HTTP requests, CPU/cache-adjusted RAM, monotonic I/O rates, missing counters, stopped/restarted/deleted containers, failures and capacity handling; run them and observe failures.
- [x] Implement `DockerApiClient(socket_path, timeout)` with `containers()` and `stats(container_id)` using bounded local GET requests. Implement `DockerCollector(client, node, ...)` with `poll_once`, `snapshot`, `capacity_error`, `start`, `stop`.
- [x] Add opt-in sender initialization and the independent `docker` envelope; bound the combined full payload, preserving both provider error envelopes.
- [x] Run Docker tests and the full sender suite; document enablement and socket authority.

## Task 2: Receiver and shared navigation

Files: update `browser/pve.py`, `browser/monitor.py`; add Docker fixture and `browser/test_docker.py`.

- [x] Write failing tests for coexistence, full-ID selection, A/B/L1/R1, pagination, reordering/deletion, stale/error recovery, invalid data and legacy PVE behavior.
- [x] Extend inventory validation with an explicit expected provider, Docker IDs and Docker CPU/RAM source. Keep shared history rules.
- [x] Add Docker entry selection and route provider state; retain existing PVE public state keys and controls.
- [x] Run receiver tests, existing PVE/navigation/event tests and installation checks.

## Task 3: Rendering and delivery verification

Files: update `browser/pve.js`, `browser/monitor.html`, UI/layout tests and README.

- [x] Add failing rendering/layout checks for Docker labels, CPU above 100%, cache-adjusted RAM, lifecycle badges, escaped names and both providers together.
- [x] Render Docker through the existing list/detail layout, add a separate host entry, and preserve accessible click/keyboard controls.
- [x] Run UI tests and layout checks at 1024x768 and 1280x720. Run the repository check command and inspect the diff.
- [x] Record verification and remaining live-daemon/device checks. Do not deploy, merge or claim physical-device verification.

## Verification record

- Display: `python3 scripts/check.py --layout` passed, including Docker/PVE receive/navigation, installation packaging, UI and both 1024x768 and 1280x720 layouts.
- Sender: baseline 151 passed, 1 skipped; final `make check`: 168 passed, 1 skipped (PowerShell runtime unavailable). Docker-specific tests include real Unix HTTP handling, Compose merge checks and two restart regression cases.
- Live local Docker Engine: 18 containers read through list, inspect and stats GETs, normalized and accepted by the handheld receiver. No container was modified and no real MQTT topic was published by this smoke check.
- Independent code review found a restart-between-polls issue. Added failing tests, fixed with StartedAt checks before/after stats, then re-review passed with 17 Docker tests.
- Not verified: physical handheld deployment/buttons, native PVE Docker group configuration and rebuilding an installed sender. PowerShell bootstrap regression is skipped when its runtime is unavailable.

Ruling: keep the receiver's existing PVE module filenames and public navigation state fields; add an explicit provider field to reuse tested history and navigation without duplicating them. Enable socket access explicitly because it grants Docker Daemon authority. Implemented in two isolated Orca worktrees; original workspace changes remain untouched.

## Deployment verification

Deployed the sender to DB795i and fully installed both handheld receivers. Existing MQTT configuration was retained. Both browsers acknowledged the new UI revision and stayed connected for the updater's 11-second observation. Real HTTP controls opened Docker list/details, switched containers and returned on both handhelds. Both received 18 Docker containers with fresh observations and zero invalid messages.

Deployment testing caught the missing `docker` HTTP action allowlist entry. A real HTTP regression test failed with 400 before the one-line fix and passed afterward; `scripts/check.py --layout` passed again.

The initial SSH launch on TrimUI left MainUI rendering alongside the monitor, causing recurring pageflip -16 errors and physical flicker reported by the user. Pausing MainUI stopped the errors and the user confirmed flicker stopped. Relaunched through the stock runtrimui command queue; the monitor's parent is the stock loop, MainUI is absent, and no pageflip errors were added during a 12-second observation. Updated the device operations guide with the verified handoff requirement.

PVE sender was not updated because SSH key authentication was rejected. Physical button-by-button and extended-duration verification remain unperformed. Device backups and the old sender image were retained privately for rollback.
