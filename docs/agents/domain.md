# Domain docs

本專案採 single-context 配置。領域詞彙由根目錄 GLOSSARY.md 管理，架構決策存放於 docs/adr/。

## Before exploring

探索程式碼前，讀取 GLOSSARY.md 及與工作範圍相關的 ADR。缺少檔案時直接繼續，不因為執行 setup 就建立空的 glossary 或 ADR。

若日後存在 GLOSSARY-MAP.md，依該檔案讀取相關 context 的 glossary，並補讀該 context 的 ADR。

## Vocabulary and decisions

issue、規格、程式碼及測試使用 glossary 定義的領域詞彙。概念已有定義時沿用該用語；真正的詞彙缺口留給 domain-modeling 處理。

工作方向與既有 ADR 衝突時，指出對應 ADR 與衝突內容，再討論是否需要新決策；保留既有已接受決策的歷史。
