> 歷史紀錄；目前採用驗證見 [adoption](../../flow-evidence/adoption.md)。

# Adopt 驗證紀錄

## 候選與讀取順序

比較基準為 `53aea8bc420aa8d73d585dae273ff69ad191dea5`，候選為本次 worktree。既有未提交的顯示端變更保留，沒有修改或 stage。採用 feature 為 `checkout.inspect`；不是全專案採用。

編輯前已讀 root AGENTS.md、docs/agents/workflow.md、docs/agents/domain.md、scripts/checkout.py、browser/test_checkout.py 及既有 CI。開始時沒有 flows 或 manifest，因此先由原始碼建立基線，再啟用 root 同步規則。Codex 本 session 收到 root AGENTS.md 並實際讀取；新規則的下一次 session discovery、Claude 與其他工具的 discovery 尚未觀察。沒有建立 CLAUDE.md，也沒有改動 local instruction files。正式的隔離代理讀取順序驗收尚未執行。

codebase-memory 使用 Tier 2，index generation 為 `2026-10-23T03:29:59Z`。search、雙向 trace 與 snippet 已執行，checkout 與其測試 coverage 都是 no_recorded_issue / metadata_match；這是 best-effort，另已讀取完整來源。trace 顯示 release.build_release 也是消費端，列入範圍缺口。

## Runtime evidence: checkout.inspect

- Base: `53aea8bc420aa8d73d585dae273ff69ad191dea5`。
- Candidate: worktree；來源 AST 與 raw MD5 見 docs/flow-manifest.json，review fingerprint 綁定政策與流程。
- Environment: 本機 Python 3 與 Git；測試使用暫存的 bare origin、writer、clone。
- External dependency: 本機 Git fixture；另於 2026-10-23 執行真實 origin fetch。
- Preflight: scripts/checkout.py --fetch 成功；main ahead=0、behind=0、dirty=true、refs_source=fetched。
- Operation and inputs: `python3 -m unittest discover -s browser -p test_checkout.py -v`。
- Expected behavior: docs/agents/workflow.md 的核對規則與 browser/test_checkout.py 的斷言。
- Actual behavior: 4 tests passed，涵蓋 fetch divergence、遠端預設分支改變、dirty/detached、未知 default 與 fetch failure。
- Side effects and cleanup: fixture 由 TemporaryDirectory 清除；真實 fetch 更新 origin 追蹤參照，未切換分支。
- Evidence retention: 本紀錄與既有測試留在 repository；測試沒有保存私有資料。
- Failure classification: none for executed tests；CLI argparse/error JSON 與 timeout 尚無專屬行為測試。
- Limitations: 未執行整套 scripts/check.py --layout，未操作設備或 sender，沒有宣稱其通過。

## 安裝與門檻

完整 scripts、SKILL.md、references、assets 複製到 tools/flow-docs；本機 pre-commit 由既有空缺位置安裝，使用 --staged。新 clone 仍需自行組合安裝 hook，不能由 tracked 檔案保證已啟用。

Flow docs CI 使用唯讀權限、固定 action SHA、完整 Git history、環境變數傳入 base，保留原有 CI。安全檢視未發現 privileged trigger、動態 shell 插值、秘密或寫入 token。初次 branch push 的全零 base 會 fail closed。GitHub runner 執行與 fork 情境尚未執行。

2026-10-23 以 gh API 查詢 main/protection 回傳 Branch not protected (404)，repository rulesets 回傳空陣列。沒有設定或修改遠端保護，合併強制門檻尚未建立。

visual verification: pending。portable diagram 結構由 checker 驗證；未渲染圖片。

獨立 agent semantic review 見同目錄 checkout-review.json；結構檢查與 staged 候選驗證結果另於交付訊息回報，不以 hash refresh 代替審查。
