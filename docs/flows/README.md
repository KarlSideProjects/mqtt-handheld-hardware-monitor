# 流程文件索引

目前只採用 `checkout.inspect`，不宣稱全專案覆蓋。來源、節點映射與指紋由 [manifest](../flow-manifest.json) 管理；[流程圖](checkout.inspect.mmd) 描述 `scripts/checkout.py` 的現況。

## 文件責任

| 文件 | 責任與擁有者 |
| --- | --- |
| [工作流程](../agents/workflow.md) | 維護者管理版本核對與建置要求，預期行為以此為準 |
| [checkout 流程](checkout.inspect.mmd) | checkout 維護者管理實際分支、錯誤與來源導航 |
| [manifest](../flow-manifest.json) | 同一變更的作者管理來源覆蓋與獨立審查紀錄 |
| [CI 手冊](../ci-validation.md) | 維護者管理既有產品驗證入口 |
| [採用驗證紀錄](../flow-evidence/adoption.md) | 本次執行者記錄可觀測證據與未驗證項目 |

## 範圍與依賴

入口是 `python3 scripts/checkout.py` 與 `inspect_checkout(repo, fetch=False)`，來源導航為 `scripts/checkout.py#main` 與 `scripts/checkout.py#inspect_checkout`。來源採 Python AST 模式，包含巢狀 Git helper。依賴為 Python 標準函式庫、Git executable、指定 repository 與 origin。遠端預設分支及網路狀態是外部輸入，不能由本機指紋保證。

`browser/test_checkout.py` 是驗證政策輸入；既有測試使用暫存 Git repository 核對 fetch、分支切換、dirty、detached 與失敗。CLI 的 argparse 失敗發生於 JSON 錯誤處理之前。可選 symbolic-ref 失敗會得到 null；必要命令失敗與 fetch 失敗由 CLI 回報錯誤，不進行 checkout 或 merge。

`changed_paths` 是 porcelain NUL 分段計數；rename 可能包含兩段，不能視為精確的檔案數。此處記錄實作限制，不改寫既有需求。

## 覆蓋缺口

未採用的 first-party 邏輯包括 MQTT 接收與 HTTP API、dashboard 和 recovery、PVE/Docker 展示、裝置資訊、R36/TrimUI 啟動與輸入/電源、安裝/更新/復原、device/release/check 工具、文件產圖工具及其設定/fixtures。採集端屬另一 repository。

`release.py` 消費 `inspect_checkout`，目前沒有其 feature 或流程；修改 checkout 時仍須檢查此消費端，擴大 adopted scope 後才能聲稱建置流程受同步保護。checker 不推斷這個跨功能關係，也不阻擋範圍外程式變更。

## 檢查入口

根目錄 AGENTS.md 是同步規則的唯一來源。完整 checker 與參考資源位於 `tools/flow-docs/`。使用標準 Python，不需要安裝選用的 Tree-sitter 套件。

```bash
python3 tools/flow-docs/flow_checker.py snapshot --root .
python3 tools/flow-docs/flow_checker.py fingerprint --root . --base HEAD --feature checkout.inspect
python3 tools/flow-docs/flow_checker.py check --root . --base HEAD
```

snapshot 只更新已登記來源；行為或政策改變時，需要獨立 reviewer 的當前 fingerprint 證據。commit 前使用 `check --base HEAD --staged`，先將預期的來源、文件與審查證據一起 stage。新 clone 可將 `tools/flow-docs/assets/pre-commit` 與既有 hook 組合，安裝到 `git rev-parse --git-path hooks` 所指的 pre-commit，保留原有檢查。

CI 使用 PR base SHA 或 push before SHA，比較 checkout 的實際 candidate；空白或全零 base 會失敗，需要明確有效的比較基準。CI 仍保留原本產品檢查。遠端 required checks 與 branch protection 必須另外核對，存在 workflow 不代表已強制合併門檻。

## 契約與證據

checkout 的權威契約由 [工作流程](../agents/workflow.md) 的版本核對章節管理，因此不另建 contracts.md。[Runtime evidence](../flow-evidence/runtime/checkout.inspect/git-fixtures.md) 保存 Git fixture 測試與真實 fetch 的結果。獨立審查位於 `docs/flow-evidence/reviews/checkout.inspect/<fingerprint>.json`，確切路徑由 manifest 記錄。
