# Adopt 驗證紀錄

| 實際路徑 | 用途 | 狀態 | 驗證證據 |
| --- | --- | --- | --- |
| `AGENTS.md` | 同步規則唯一來源 | reused | 本 session 的指令與檔案讀取 |
| `docs/flows/README.md` | 範圍、責任、來源導航與缺口 | reused | 已核對來源與連結 |
| `docs/flows/checkout.inspect.mmd` | checkout feature 流程 | created | 沿用既有流程內容，配合 feature ID 命名 |
| `docs/flow-manifest.json` | AST、節點映射、政策與 review | reused | snapshot、fingerprint、check |
| `docs/flows/contracts.md` | 共用契約 | not-applicable | 權威契約已在 `docs/agents/workflow.md` 的版本核對章節 |
| `docs/flow-evidence/adoption.md` | 各 gate 的結果 | created | 本文件 |
| `docs/flow-evidence/reviews/checkout.inspect/031fdaec772ecd2bada6c00b98713e0b94eea1f803a95a839ef4def20b723950.json` | 獨立審查 | created | 獨立代理 `/root/adopt_semantic_review` 回傳 pass、findings=[] |
| `docs/flow-evidence/runtime/checkout.inspect/git-fixtures.md` | 外部 Git 行為證據 | created | 同目錄 `git-fixtures/tests.log`、`git-fixtures/fetch.json` |
| `tools/flow-docs/flow_checker.py` | CLI checker | reused | 與技能 scripts 原檔逐一比對相同 |
| `tools/flow-docs/flow_parsers.py` | 語法 adapter | reused | 與技能 scripts 原檔逐一比對相同 |
| `tools/flow-docs/requirements-ast.txt` | 選用依賴釘選 | reused | 與技能 scripts 原檔逐一比對相同 |
| `tools/flow-docs/SKILL.md`、`tools/flow-docs/references/`、`tools/flow-docs/assets/pre-commit` | 完整操作與 hook 資源 | reused | 已核對安裝資源 |
| `.git/hooks/pre-commit` | 本機 staged gate | reused | executable，使用 `check --base HEAD --staged`；未設定 core.hooksPath |
| `.github/workflows/flow-docs.yml` | PR/push candidate check | reused | 原始碼檢視，GitHub runner 未執行 |
| `README.md` | 根目錄導航 | reused | 已有 flow index 連結 |

## 範圍與候選

比較基準為 `53aea8bc420aa8d73d585dae273ff69ad191dea5`，候選為目前 worktree。只採用 `checkout.inspect`，來源為 `scripts/checkout.py`，採 native Python AST。這是部分採用，其他 first-party 邏輯與依賴缺口見 [索引](../flows/README.md)。

公開入口為 CLI `main` 與 `inspect_checkout(repo, fetch=False)`。模組輸入包含 Python 標準函式庫、Git executable、repo、fetch flag、origin refs 與工作樹狀態；沒有產品設定檔或 frontend 邊界。`browser/test_checkout.py` 為政策輸入。`scripts/release.py#build_release` 是範圍外消費端，尚無受保護 feature。

本次沒有路徑覆寫。既有 `docs/evidence/flow-docs/` 保留為歷史證據；當前結果使用技能規定的 `docs/flow-evidence/`。本次保留產品未提交變更，也不改動使用者 index。

## 規則發現與讀取順序

Root gate 已由本 session 指令載入，並於編輯前讀取 `AGENTS.md`、`docs/agents/workflow.md`、`docs/agents/domain.md`、`docs/flows/README.md`、`docs/flow-manifest.json`、`docs/flows/checkout.mmd` 與來源、測試。對話在首次編輯前宣告 `Affected Feature IDs: checkout.inspect`。流程內容沿用至新檔名；契約仍由工作流程文件管理。

未發現 repository 根目錄 CLAUDE 入口，不建立相容檔。祖先掃描只找到 `/home/karl/.claude/CLAUDE.md`；未改動該個人指令檔。Claude、其他工具與新 session 的實際 discovery 尚未觀察；隔離代理的 tiny refactor、deletion、missing baseline、new capability、delegation 與 expanded scope 讀取順序驗收未執行。

結構探索使用 codebase-memory Tier 2，generation `2026-10-23T08:33:47Z`。checkout、release、test_checkout 的 coverage 為 no_recorded_issue / metadata_match；此結果只屬 best-effort。另已直接讀取來源與測試。Graph 將巢狀 git helper 誤連至 checker.Tree.git，因此依實際原始碼確認 checkout 的 Git subprocess 行為。

## Gate 結果

| Gate | 狀態 | 證據與限制 |
| --- | --- | --- |
| Installation | passed | 完整 scripts 與技能參考資源已逐檔比對 installed skill；本機 hook 可執行 |
| Root rule and discovery | passed / unverified | 本 Codex session 已載入；其他 session 與工具 unverified |
| Read-before-edit | passed / incomplete | 本次對話有讀取與編輯順序；完整隔離代理驗收 incomplete |
| Coverage | partial | checkout 的來源與節點映射；全專案範圍未採用 |
| Structural checker | passed | `check --base HEAD` 與隔離 index 的 `check --base HEAD --staged` 均通過；本機 pre-commit 同樣通過 |
| Agent semantic review | passed | `/root/adopt_semantic_review`，當前 fingerprint 與 raw JSON 見 manifest；結構化紀錄不證明 reviewer 身分 |
| Behavior and external inputs | passed within scenario | [Runtime evidence](runtime/checkout.inspect/git-fixtures.md)，4 tests passed；未驗證案例列於該文件 |
| Visual inspection | pending | portable diagram 尚未渲染，沒有衍生圖片 |
| CI execution | unverified | 現有產品 CI 保留；Flow docs workflow 使用真實 PR base/push before，全零 base fail closed |
| Human and merge requirements | incomplete | 2026-10-23 gh API：main/protection 回傳 Branch not protected (404)，rulesets 為空；未變更遠端設定 |

## 驗證紀錄

隔離 temporary Git repositories 的 [checker acceptance log](checker-acceptance.log) 記錄正向與拒絕案例，涵蓋 stale hashes、缺漏來源與符號、cosmetic refresh、共享依賴、module context、review 狀態、staged 差異、缺失 base、圖語法、unsafe paths 與 loop。fixture 使用 synthetic review JSON，僅測試 checker 結構驗證，不作為產品語意審查。

逐檔比對發現 vendored SKILL.md 與 references 為舊版，已同步 installed skill 的內容；checker、parser 與 requirements 原本相同。`git diff --exit-code HEAD -- scripts/checkout.py browser/test_checkout.py .github/workflows/ci.yml` 通過，確認本次採用來源、測試與既有產品 CI 均未改動。

比較 base 為上列完整 SHA。`python3 tools/flow-docs/flow_checker.py check --base HEAD` 回報 worktree passed，affected features 為 `checkout.inspect`。使用 `GIT_INDEX_FILE` 建立從 HEAD 加入採用文件的隔離 candidate，`check --base HEAD --staged` 與 `.git/hooks/pre-commit` 都回報 index passed；使用者 index 未變更。當前語意審查 fingerprint 為 `031fdaec772ecd2bada6c00b98713e0b94eea1f803a95a839ef4def20b723950`，獨立代理回傳 pass 與空 findings。

未執行全產品 `scripts/check.py --layout`、設備、sender、GitHub runner、圖形渲染與完整隔離代理讀取情境。遠端保護未建立，不能宣稱全專案覆蓋或端到端合併強制門檻完成。
