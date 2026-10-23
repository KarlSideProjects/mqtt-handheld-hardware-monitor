### Runtime evidence: checkout.inspect / git-fixtures

- Base: `53aea8bc420aa8d73d585dae273ff69ad191dea5`。
- Candidate: 本次 worktree；`scripts/checkout.py` 的 MD5 為 `f67164580c8033ae68b75207ca57bf46`，AST 與政策綁定見 manifest。
- Environment: Python 3.14.4、Git 2.53.0，本機 Linux。
- External dependency: 暫存 bare origin、writer、clone；真實 origin 觀測日期為 2026-10-23。
- Preflight: `python3 scripts/checkout.py --fetch` 成功，HEAD 等於 base，ahead=0、behind=0、dirty=true、refs_source=fetched。
- Operation and inputs: `python3 -m unittest discover -s browser -p test_checkout.py -v`；fixtures 由 `browser/test_checkout.py` 建立。
- Expected behavior: `docs/agents/workflow.md` 的版本核對契約與測試中的斷言。
- Actual behavior: 4 tests passed，涵蓋 fetch divergence、遠端預設分支變更、dirty/detached、未知 default 與 fetch failure。
- Side effects and cleanup: fixtures 由 TemporaryDirectory 清除；真實 fetch 更新 origin refs，沒有 checkout 或 merge。
- Evidence: [tests.log](git-fixtures/tests.log)、[fetch.json](git-fixtures/fetch.json)。
- Evidence retention: 上列檔案存放於 repository 文件目錄，暫存 fixture 清除後仍保留。
- Failure classification: none for executed scenarios。
- Limitations: CLI argparse、error JSON、timeout 未有專屬行為測試；未執行產品全套檢查、設備或 sender 驗證。
