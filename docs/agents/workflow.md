# 工作流程

## 版本核對

探索功能現況前執行 `python3 scripts/checkout.py --fetch`。工具只更新 origin 追蹤參照，回報 HEAD、分支、遠端預設分支、ahead／behind 與未提交狀態，不切換分支或合併。`refs_source=local_cache` 只代表本機快取，fetch 失敗或 default_ref 不明時不可宣稱已核對最新主線。

checkout 落後時，先讀取預設分支的相關檔案與已合併 PR，再判定功能是否存在。保留使用者未提交的內容；需要隔離時沿用 Orca 工作區工具。

## 可追溯建置

使用 `scripts/release.py --repo <採集端工作區> --image <映像標籤> --output <新的私有目錄> -- make check`。來源必須已提交且工作樹乾淨；工具執行檢查、確認版本未變動，將該 commit 的 archive 直接交給 Docker 建置。

成功的私有目錄包含 source.tar、checks.log、build.log、image.id 與 manifest.json。manifest 對齊 source_commit、檢查紀錄與不可變 image ID；失敗不產生成功 manifest，不會重啟或部署容器。保留 source.tar 後可在工作區移除時重建來源；執行時環境以 image ID 識別，不保證未鎖定的外部套件日後仍建出相同映像。

部署使用已驗證的 image ID，保留舊映像與私有設定。部署結果另記錄目標、版本、驗證及回復位置；不要將帳密、完整環境變數或原始 inspect 輸出加入 Git。

## 工具輸出

本 session 已讀過的技能沿用其內容；需要補充時只讀相關章節或引用檔案。記錄已載入的技能名稱及必要約束，避免為同一規則重讀整份文件。

Orca 的 JSON 回應保留完整資料供程式處理，對話只輸出當次需要的 id、path、status 或失敗 reason。工具定義只探索當次要呼叫的方法；批次讀檔時控制範圍，避免輸出截斷後再讀一遍。

## 驗證

顯示端沿用 `python3 scripts/check.py --layout`，採集端沿用 `make check`。新增行為的測試放入既有檢查入口；HTTP 操作經實際 handler 測試，不能以直接 state.action() 或前端模擬伺服器代替傳輸契約驗證。

實機操作依 [設備更新與診斷](device-operations.md)。已穩定運作的設備不因本機工具測試而重新啟動。
