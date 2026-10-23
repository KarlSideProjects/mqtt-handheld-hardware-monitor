<!-- codebase-memory-mcp:start -->
For structural codebase exploration, use the installed `codebase-memory` skill.
<!-- codebase-memory-mcp:end -->

## Sender

MQTT 採集端（Windows/Linux/PVE sender）在 `KarlSideProjects/hwmonitor-mqtt`，本機 clone 位於 `~/Workspace/Tools/hwmonitor-mqtt`，有自己的 `AGENTS.md`。

## Web Research

網頁研究優先使用全域 Firecrawl MCP 工具。

## Agent skills

### Issue tracker

規格與票券發布至 KarlSideProjects/mqtt-handheld-hardware-monitor 的 GitHub Issues；執行 tracker 操作前讀取 `docs/agents/issue-tracker.md`。

### Triage labels

使用五個預設 triage 角色；套用標籤前讀取 `docs/agents/triage-labels.md`。

### Domain docs

採 single-context 配置；探索領域概念或決策前讀取 `docs/agents/domain.md`。

### Device operations

部署、更新或診斷 R36／TrimUI 前，讀取 `docs/agents/device-operations.md`，使用其中的設備工具與驗證條件。

### Session workflow

開始探索現況或準備建置前，讀取 `docs/agents/workflow.md`，核對 checkout、版本與部署來源。

## [MANDATORY] Flow Documentation Sync Gate
1. Pre-Edit Read: before adding, modifying, refactoring, moving or deleting
   code or behavior-bearing inputs, read docs/flows/README.md,
   docs/flow-manifest.json and all affected feature/shared flows and contracts.
   Before the first edit, report: Affected Feature IDs: <resolved IDs>.
   Missing/stale flows require a source-verified baseline first;
   unreadable required documents block dependent edits.
2. Post-Edit Sync: run flow-docs-sync Maintain, update affected flows,
   mappings and source fingerprints in the same change, then run:
   python3 tools/flow-docs/flow_checker.py check --base HEAD
   Use the project's actual comparison base; HEAD is the local default.
   Obtain independent agent review where required; preserve repository human
   approval requirements. Hash refreshes alone are not semantic review.
3. Delegation/resume: each executing agent reads its own affected documents.
   Recheck the read set after scope/input changes or a handoff.
   Missing required checks or unresolved coverage prevent completion claims.

目前採用範圍與缺口見 docs/flows/README.md；未映射的功能先建立來源驗證基線。
