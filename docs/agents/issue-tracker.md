# Issue tracker: GitHub

本專案規格與票券存放於 KarlSideProjects/mqtt-handheld-hardware-monitor 的 GitHub Issues。使用 gh CLI；在命令加上 --repo 或 API 的完整 repository 路徑，避免跨採集端倉庫時操作錯誤專案。

## Conventions

- 建立 issue：使用 gh issue create，提供 title、body-file 及所需標籤。多行本文先寫入檔案，保留實際換行。
- 讀取 issue：使用 gh issue view，讀取 number、title、body、labels、comments。
- 列出 issue：使用 gh issue list，按工作範圍、state 與 triage label 篩選。
- 留言及標籤：使用 gh issue comment、gh issue edit。多行留言使用 body-file。
- 關閉 issue：使用 gh issue close 並記錄原因；沿用呼叫技能對關閉父 issue 的限制。
- 發布規格或票券表示建立 GitHub issue；讀取相關票券表示讀取完整本文及留言。

## Parent and blocking relationships

有來源 issue 時，票券使用 GitHub 原生 sub-issue 關係連至來源。依賴使用原生 issue dependencies。先建立 blocker，再建立依賴它的票券；新增關係時使用 issue database id，不能把顯示的 issue number 或 node_id 當 database id。

本機 gh 2.46 不支援新版 sub-issue 旗標，因此使用 gh api：

- 讀取 database id：GET repos/KarlSideProjects/mqtt-handheld-hardware-monitor/issues/{number}，取 id。
- 加入 sub-issue：POST repos/KarlSideProjects/mqtt-handheld-hardware-monitor/issues/{parent}/sub_issues，參數 sub_issue_id 為子票 database id。
- 加入 blocker：POST repos/KarlSideProjects/mqtt-handheld-hardware-monitor/issues/{child}/dependencies/blocked_by，參數 issue_id 為 blocker database id。

只有原生關係不可用時才退回本文：子票頂端記錄 Part of #parent，以 Blocked by 列出 blocker。權限或 API 錯誤必須明確回報，不宣稱已建立原生關係。

有未關閉 blocker 的票券不在可執行 frontier。全部 blockers 關閉後才可開始；ready-for-agent 表示規格就緒，不表示依賴已解除。

## Pull requests as a triage surface

PRs as a request surface: no.

GitHub 的 issue 與 PR 共用編號。來源不明時先辨識類型，再使用相應 gh issue 或 gh pr 命令。

## Wayfinding operations

wayfinder 使用一個標記 wayfinder:map 的 issue 作為 map；工作票以 sub-issue 連至 map，並按功能使用 wayfinder:research、wayfinder:prototype、wayfinder:grilling 或 wayfinder:task。

工作 frontier 是 map 內沒有未關閉 blocker、也尚未指派的 open 票券。認領時指派給執行者；回報研究結果、關閉工作及維護 map 時，遵循當次技能的明確授權與更新規則。
