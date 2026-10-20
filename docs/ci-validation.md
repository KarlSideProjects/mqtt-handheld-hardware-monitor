# 外部設備 CI 驗證手冊

建議用同網段的 Linux 自架 runner，結合 pytest／OpenSSH、Playwright、掌機上的瀏覽器自動化，以及固定相機，驗證 R36 與 TrimUI 的監控面板。模擬器負責軟體相容性，實機負責 GPU、按鍵、休眠與 LCD 驗收。任何單一工具都不能保證生產環境完全沒有問題。

這份手冊供維護者建立 CI，安裝操作另見 [雙設備安裝說明](installation.md)。**CI 建置流程是尚未部署的草案**；文中會標示已實測項目。工具能力依 2026-10-20 查閱的官方文件整理，版本更換後需要重新確認。

## 1. 目前狀態與判定方式

Cog 路徑的黑屏是必須攔截的失敗案例。[實測紀錄](evidence/trimui-black-screen-2026-10-20.json) 顯示 MQTT 已連線、有三台在線主機、背光非零，但啟用中的 DRM plane 只有原廠 OSD，沒有 Cog 的 framebuffer。頁面載入成功與後端正常，都不足以證明畫面輸出成功。

此紀錄中的 framebuffer 擁有者欄位來自該台韌體的 debugfs。它是該 Cog 測試的必要診斷條件，不能直接當成所有 DRM 裝置的通用測試，也不能證明實體 LCD 可見。

2026-10-20 的 GitHub 唯讀查詢中，這個儲存庫沒有已登錄的 Actions workflow，儲存庫及所屬組織的 runner 清單均為空。查詢範圍是 `repos/KarlSideProjects/r36max2-hwmonitor/actions/{workflows,runners}` 及 `orgs/KarlSideProjects/actions/runners`，不包含帳號其他儲存庫。本文沒有建立 runner 或啟用工作流程。Chromium／SDL 實機測試由人工觸發執行，使用者已確認橋接頁面可見，結果見 [安裝驗證](installation.md#驗證與限制)，尚未串接 CI。

建議 CI 分別回報以下狀態，發布時要求對應機型全部通過：

| 狀態 | 通過條件 | 缺少證據時 |
| --- | --- | --- |
| 軟體通過 | 程式、安裝邏輯、多尺寸頁面與資料互動測試通過 | 失敗或未驗證 |
| 實機渲染通過 | 裝置實際引擎、內容更新、應用程式顯示輸出均通過 | 不能由 HTTP 成功推導 |
| 實體面板通過 | 相機或人工目視確認當次標記、方向、內容更新及按鍵結果 | 標示未驗證，阻擋該機型發布 |

人工目視可以暫代相機，但必須記錄設備、版本、測試項目及驗收人。尚未接上硬體的工作不能透過跳過測試取得發布成功狀態。

## 2. 工具選擇與模擬器的範圍

以下為建議組合。「採用」代表建議導入，不代表已安裝或已跑過完整流程。

| 工具 | 驗證內容 | 驗證邊界 | 採用建議 |
| --- | --- | --- | --- |
| pytest + OpenSSH | 安裝、退出碼、程序、HTTP／MQTT、清理與重連 | 無法證明畫面可見 | 實機測試基礎 |
| Playwright Chromium／WebKit | DOM、CSS、互動、多尺寸版面與截圖差異 | bundled WebKit 不是掌機的 Cog／WPE | 每個 PR 執行 |
| Playwright CDP | 兩台掌機實際 Chromium 的 DOM、互動及引擎截圖 | 不涵蓋背光及 LCD 光學結果 | 實機測試採用 |
| WPEWebDriver + Selenium | 候選 Cog／WPE 引擎的網頁與截圖 | 目前安裝器使用 Chromium | 日後重試 WPE 時評估 |
| DRM state、libdrm、FFmpeg kmsgrab | 顯示模式、plane、framebuffer 與可擷取的輸出 | 緩衝區不一定能讀回；單一 plane 不等於合成畫面 | 實機診斷與輸出驗證 |
| 固定相機 + V4L2／FFmpeg + OpenCV | LCD 畫面、方向、當次標記及內容變化 | 需要固定位置與光線校正 | 自動化面板驗收 |
| QEMU ARM64 virt | ARM64 userspace、套件及部分安裝路徑 | 無法重現本機的 Allwinner／Mali／面板 | 軟體相容性選配 |
| VKMS + Mesa | 虛擬 DRM／KMS 與軟體渲染 | 無法證明廠商 GPU 或實體 LCD 正常 | 圖形整合選配 |
| labgrid | pytest 整合、資源協調、SSH、串列與電源控制 | 畫面判讀仍需測試程式 | 加入電源或串列救援時採用 |
| LAVA | 設備排程、部署、開機與測試管理 | 仍需描述掌機及撰寫畫面測試 | 大型設備庫再評估 |

OpenSSH 已足夠處理目前兩台設備；若需要主機狀態斷言，可加入 [pytest-testinfra 的 SSH backend](https://testinfra.readthedocs.io/en/latest/backends.html)。[Playwright 視覺比對](https://playwright.dev/docs/test-snapshots)需要固定 OS、字型、瀏覽器及執行環境，避免環境差異造成誤報。其[瀏覽器版本](https://playwright.dev/docs/browsers)由 Playwright 配套提供，因此 WebKit 測試成功仍須補測裝置引擎。

[QEMU virt](https://www.qemu.org/docs/master/system/arm/virt.html) 是通用虛擬平台，不對應一台真實掌機。由此可判斷，它適合驗證 ARM64 軟體，但不能作為 TrimUI GPU 相容性的依據。[VKMS](https://docs.kernel.org/gpu/vkms.html) 是軟體 KMS 驅動，可搭配 IGT 測試通用顯示行為；實際可用選項取決於 runner 的核心版本。

目前建議先完成 pytest、Playwright、實機引擎與相機的閉環。兩台固定系統使用完整 [LAVA](https://lava.readthedocs.io/en/latest/introduction/glossary.html) 會增加服務與設備設定維護；需要共用設備、自動斷電或串列救援時，再導入 [labgrid](https://labgrid.readthedocs.io/en/latest/overview.html)。這是依本專案規模作出的工程選擇。

## 3. 自架 runner 的配置草案

runner 放在可連到兩台掌機的獨立 Linux 主機，掌機本身只執行待測程式。建議標籤為 `self-hosted`、`linux`、`handheld-lab`，實際 CPU 架構依 runner 主機登錄。[GitHub 支援透過標籤選擇 runner](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/use-in-a-workflow)。

公開 PR 的程式與版面測試在 GitHub-hosted runner 執行。接觸掌機 SSH 及內網的硬體在迴路測試（HIL），建議放在私人控制儲存庫，由維護者選定可信任版本觸發。GitHub 提醒公開儲存庫的 fork 程式可攻擊自架 runner；私人控制工作也必須限制可提交及執行程式的人員。[GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use)。

以下步驟尚未實際部署：

1. 維護者準備獨立 Linux runner 主機、掌機供電及固定相機。
2. 維護者在私人控制儲存庫的 Settings → Actions → Runners → New self-hosted runner 取得當次註冊指令，依主機 OS／架構安裝。
3. 維護者配置專用 SSH 金鑰、已核對的主機金鑰與私有測試 MQTT 設定，避免在工作日誌輸出帳密。
4. 維護者確認 runner 可以連線設備並讀取相機，再固定 Python、Node、Playwright、Selenium、字型和瀏覽器版本。
5. 工作流程依設備使用獨立 concurrency group，設定 `cancel-in-progress: false`，避免更新中途取消。[GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)。
6. 測試程式取得 runner 本機的設備鎖，再開始部署。跨儲存庫或人工操作不受同一儲存庫的 concurrency 保護，需要共用資源鎖或 labgrid 協調。

安裝器在互動終端機會嘗試預設登入，再提示帳密；CI 沒有互動輸入，必須預先提供私有設定，認證失敗就停止。不要在公開 PR 工作提供設備或 broker 憑證。

每次工作記錄程式版本、安裝產物雜湊、設備韌體、核心、顯示模式與瀏覽器版本。TrimUI 安裝的具體套件及版本由 [安裝說明](installation.md#自動安裝相依套件) 管理；CI 應讀取實際版本，不只依賴 runner 的套件快取。

## 4. 軟體與版面驗證

下列命令在開發電腦執行，不部署設備。基本測試已執行通過；它們驗證各自涵蓋的程式行為，不能取代實機驗收。

```bash
# 開發電腦：基本程式與安裝模擬測試。
python3 browser/test_install.py
python3 browser/test_trimui_browser.py
python3 browser/test_trimui_power.py
python3 browser/test_monitor.py
python3 browser/test_monitor_events.py
python3 browser/test_menu.py
python3 browser/test_device_info.py
node browser/test_monitor_ui.cjs
```

現有 [版面測試](../browser/test_monitor_layout.cjs) 需要安裝 Playwright 及其 Chromium，命令如下。本次已通過兩台目標尺寸及 TrimUI 實際 viewport 的版面測試；腳本目前檢查溢出並輸出預覽，尚未建立完整視覺基準比對。

```bash
# 開發電腦：需先備妥 Playwright 與配套 Chromium。
node browser/test_monitor_layout.cjs
MONITOR_VIEWPORT='{"width":1280,"height":720}' node browser/test_monitor_layout.cjs
MONITOR_VIEWPORT='{"width":1279,"height":719}' node browser/test_monitor_layout.cjs
```

下列矩陣包含已執行項目與待擴充情境；目前完成的是兩台掌機尺寸、1279 × 719 及零／兩／四張 GPU 的版面檢查，其餘 CI 整合仍待實作。尺寸依 [README 實機畫面](../README.md#實機畫面) 及 [TrimUI 實測顯示模式](trimui-smart-pro-s-research.md#2-實機與官方依據)；瀏覽器實際 viewport 仍需在裝置量測。

| 測試情境 | 輸入 | 必須檢查 |
| --- | --- | --- |
| R36 版面 | 1024 × 768 | 字體、圖表、底部操作列無裁切 |
| TrimUI 版面 | 1280 × 720 | 重排、方向與操作列位置 |
| 窄視窗 | 建議 390 × 844，屬新增測試目標 | 同一頁面的響應式行為 |
| 主機及 GPU 數量變化 | 無主機、多頁主機、零／多張 GPU | 空狀態、分頁、卡片與詳細頁 |
| MQTT 狀態變化 | 固定資料、缺欄位、過期、斷線與重連 | 顯示正確狀態及更新結果 |

CI 使用獨立測試 broker 或固定 fixtures，隔離真實監控流量。固定時間、資料及動畫後，再加入 Playwright 的 `toHaveScreenshot()` 比對，保留 expected、actual、diff 和 trace。視覺基準必須經人工核對，不能直接接受失敗時產生的圖片。

## 5. 實機瀏覽器與顯示輸出驗證草案

兩台設備使用 Chromium，但作業系統、顯示驅動及輸入裝置仍需分開驗證。TrimUI 實測引擎、viewport、版面及退出結果由 [安裝驗證](installation.md#驗證與限制) 管理。

測試時可在專用 Chromium session 開啟 loopback CDP，再用 SSH tunnel 讓 runner 經由 [Playwright connectOverCDP](https://playwright.dev/docs/api/class-browsertype#browser-type-connect-over-cdp) 連線。此介面只支援 Chromium，功能完整度低於 Playwright 原生連線。TrimUI 可透過 CDP 檢查 DOM 與七種資訊頁；一般啟動的 SDL 橋接亦需使用 loopback CDP，詳見安裝說明。

CI 整合仍是草案，建議依序執行：

1. fixture 取得設備鎖，準備隔離的測試資料；若需要替換目前 session，先正常退出並確認選單恢復。
2. TrimUI 啟動一個完整的 Chromium／SDL 測試 App，再連接該橋接已建立的 loopback CDP；R36 啟動專用的 Chromium CDP session。每台設備同時只保留一個顯示 session，避免搶用 SDL／DRM。
3. runner 建立 SSH tunnel，再用 CDP 連線該 session。
4. 測試確認當次標記、多頁互動、資料更新與頁面溢出，保存引擎截圖。
5. fixture 關閉 session，檢查原生 SDL、瀏覽器程序、掛載、背光及原廠選單。
6. fixture 還原一般啟動方式，確認測試 tunnel 已關閉；正常 SDL 橋接保留必要的 loopback CDP。

若日後重試 Cog，可參考 [Cog WebDriver 官方方法](https://igalia.github.io/cog/webdriver.html)，在裝置配置版本配對的 WPEWebDriver，由 Selenium 建立 automation session。官方範例使用 Wayland，不能當成此設備 DRM 路徑已通過的證據。

引擎截圖之後，還要檢查 DRM connector、CRTC、plane 與 framebuffer。擷取工具可評估 [FFmpeg kmsgrab](https://ffmpeg.org/ffmpeg-devices.html#kmsgrab)，但它需要 DRM master 或 CAP_SYS_ADMIN，緩衝區也必須支援相應讀回方式。不能直接擷取第一個 plane，否則可能只得到原廠 OSD。

若驅動支援 [DRM writeback](https://docs.kernel.org/gpu/drm-kms.html#writeback-connectors)，可評估取得合成輸出；功能是否可用必須實測。沒有可用的讀回路徑時，改由相機提供畫面證據，並保留 DRM 診斷。讀回圖片仍未涵蓋實體 LCD、背光與排線。

## 6. LCD、按鍵與待機驗證草案

固定相機是確認 LCD 實際發出正確圖像的自動化路徑。Linux 可用 [V4L2 capture](https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/dev-capture.html) 或 [FFmpeg V4L2](https://ffmpeg.org/ffmpeg-devices.html#video4linux2_002c-v4l2) 擷取 USB 相機。相機型號、裝置節點、解析度及校正資料尚未選定。

1. 維護者固定相機及掌機位置，校正螢幕四角，鎖定曝光與白平衡。
2. 測試頁顯示本次工作的唯一標記及固定測試資料，讓 OpenCV 可辨認正確設備、方向與版本。
3. runner 保存相機原圖及校正後的螢幕區域，再比對標記、關鍵內容及預期版面。
4. 測試更新資料並要求第二張圖片出現新內容，排除停格或舊畫面。
5. 測試經由 evdev／uinput 等注入對應事件，驗證選取、詳細頁、返回、換主機、暫停及退出，再比對畫面。

[measure_trimui_input.py](../browser/measure_trimui_input.py) 可量測方向鍵到 active SDL framebuffer 選取底色改變，這是數位顯示管線的回歸測試。DMA-BUF 讀回適用於此韌體，不能推廣為所有設備均支援。

事件注入只驗證事件到功能的路徑。實體按鍵的接點及手感仍需人工或按壓治具；合成事件不能當成實體按鍵驗證。只有非黑色像素也不足以通過，因為選單、OSD 或錯誤畫面都可能有亮度。

待機測試要超過設備原本的自動休眠計時，並持續確認資料及畫面更新。TrimUI 原設定及防休眠機制見 [安裝前關閉自動休眠](installation.md#安裝前關閉-trimui-自動休眠)；僅檢查旗標存在不算長時間測試。重新開機後仍須重測，確認開機入口真正生效。

[test_trimui_screen.py](../browser/test_trimui_screen.py) 在實機注入 X，檢查背光、DPMS、CRTC active、喚醒與關屏時 MQTT 持續更新。這是驅動及事件路徑測試，實體熄滅／恢復與省電幅度仍須目視、相機或供電量測；不能只因 API 回報 Off 就宣稱面板所有電源已關閉。

功能測試還要涵蓋 MQTT 斷線重連、退出回原廠選單、背光恢復、再次啟動及重複安裝。兩台設備的按鍵與手動關屏機制不同，必須分開驗收。

## 7. 失敗證據與設備恢復

每項測試都要有完成期限。逾時先保存證據，再執行 fixture 的清理；恢復失敗時，工作必須回報設備不可用。尚未配置可控電源或串列救援，因此 SSH 失聯時不能保證全自動復原。

建議每次工作保存：

- 測試 JUnit XML、Playwright trace 與差異圖片。
- 實機引擎截圖、DRM 輸出圖片、相機原圖與校正後圖片。
- 程式與設備版本、部署產物雜湊、當次測試標記及時間。
- 應用日誌、程序狀態、DRM state、背光、掛載與必要的核心日誌。
- MQTT 連線／資料更新結果、退出清理及選單恢復結果。

工作失敗也要上傳診斷，使用 [GitHub workflow artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) 保存。上傳採明確檔案清單，排除 MQTT 設定、SSH 金鑰、環境變數及含密碼的安裝備份。

一般清理先正常停止測試 session／App，釋放輸入與 DRM，再檢查臨時掛載、背光和選單。需要還原部署時，使用 [安裝說明中的備份還原](installation.md#trimui-備份還原)；該 TrimUI 還原分支仍標示未實測。runner 註冊的撤銷方式是在 GitHub 移除對應 runner，並停止主機上的 runner 服務。

驗收完成時，報告必須列出兩台設備各自的三層狀態、失敗證據及恢復結果。Cog 黑屏保留為失敗案例。Xorg 實驗雖可讀回 framebuffer，實體 LCD 仍黑屏；原廠 SDL 橋接則已由使用者確認可見。CI 必須辨識實際使用的輸出路徑，不能沿用另一條路徑的結果。
