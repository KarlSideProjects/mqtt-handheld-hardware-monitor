# TrimUI Smart Pro S 共用網頁監控面板研究

| 項目 | 內容 |
| --- | --- |
| 狀態 | 原廠 SDL 網頁橋接已確認實體可見；驗收結果見安裝說明 |
| 對象 | 維護掌機監控面板的開發者與設備持有人 |
| 範圍 | 沿用本專案 MQTT 監控，以響應式網頁支援第二台掌機 |
| 初始調查來源 | 2026-10-20，透過 SSH 唯讀檢查 `192.168.5.160`；後續安裝驗證見安裝說明 |
| 初始程式基準 | 本專案 commit `3c3e7070cc5d8cf86a7aedce9c8de75cf23bcd51`；檔案連結包含後續移植實作 |

## 1. 結論

目前保留同一份 [monitor.html](../browser/monitor.html)，依可用寬度與高度調整版面。兩台掌機各執行本機 MQTT／HTTP 服務，再由各自的網頁引擎顯示。R36 沿用 Chromium，TrimUI 使用私有 Debian rootfs 的 headless Chromium，再由原廠 SDL 顯示。安裝、實際啟動與仍待確認的顯示項目統一記錄於 [安裝說明](installation.md)。

第二台已具備 Python、SDL2 與 DRM 顯示介面。直接在記憶體載入現有 Python 模組後，CPU、記憶體與電池採樣成功。主要移植工作是網頁引擎、響應式版面、按鍵與螢幕電源控制。R36 的 Debian 安裝流程不能直接用於這台 Buildroot 系統。另有實驗性的 TrimUI 安裝器與按鍵／感測適配，使用前提及尚未驗證項目見 [雙設備安裝說明](installation.md)。

目標是保留遊戲選單、MQTT 資料格式及現有監控功能，從 TrimUI Apps 開啟同一套網頁。本次實作未進行刷機、修改 broker 或修改電腦採集端；手機與一般瀏覽器也可共用前端，但遠端存取服務另有設計工作，見第 4 節。

## 2. 實機與官方依據

以下數據是當次設備狀態，並非所有韌體版本的保證。官方產品識別見 [Smart Pro S 頁面](https://trimui.com/pages/trimui-smart-pro-s)；該頁規格主要放在圖片內，因此此處採用實機讀值。

| 檢查面向 | 實測結果 | 來源 |
| --- | --- | --- |
| 系統 | Buildroot 2022.05、Linux 5.15.147、aarch64、glibc 2.33 | `/etc/os-release`、`uname -a`、`ldd --version` |
| SoC 相容字串 | `allwinner,a523 arm,sun55iw3p1` | `/proc/device-tree/compatible` |
| CPU | possible `0-7`，當時 online `0-1,4` | `/sys/devices/system/cpu/{possible,online}` |
| 記憶體 | MemTotal 986008 kB，約 963 MiB；首次檢查 MemAvailable 約 390 MiB | `/proc/meminfo` |
| Python | 3.10.4，`ssl`、`http` 可匯入；`paho` 不存在 | `python3 --version` 與 `importlib.util.find_spec` |
| 顯示 | DRM DSI 模式列出 `1280x720`、`720x1280`；fb0 模式為 `1280x720`；DRM rotate 為 `1` | `/sys/class/drm/card0-DSI-1/{modes,rotate}`、`/sys/class/graphics/fb0/modes` |
| 顯示緩衝 | fb0 virtual_size 為 `1280,1440`，32 bpp | `/sys/class/graphics/fb0/{virtual_size,bits_per_pixel}`；不能當成網頁 viewport |
| 圖形函式庫 | 有 SDL2、EGL、GLESv2、GBM、libdrm | `/usr/lib` 檔案檢查，尚未建立 EGL context |
| SDL 視訊後端 | `KMSDRM`、`offscreen`、`dummy`、`evdev` | Python ctypes 呼叫 `SDL_GetNumVideoDrivers`、`SDL_GetVideoDriver`，未初始化顯示 |
| 既有網頁環境 | 標準程式路徑與 Apps 檢查未找到 Chromium、WebKit、Xorg 或 Weston | `command -v` 及限定目錄檔名搜尋，非全檔案系統排除證明 |
| Apps 入口 | `config.json` 的 `launch` 指向 `launch.sh` | `/mnt/SDCARD/Apps/BootRetroArch`、`WiliWili` 等現有入口 |
| 輸入 | `TRIMUI Player1` 為 `/dev/input/event4`、`js0` | `/proc/bus/input/devices`；節點編號可能變動 |
| 本機感測器 | CPU thermal 名稱為 `cpul_thermal_zone`、`cpub_thermal_zone`；電池為 axp2202 | `/sys/class/thermal/thermal_zone*/type`、`/sys/class/power_supply` |

官方 [Smart Pro S SDK 發行頁](https://github.com/trimui/toolchain_sdk_smartpro_s/releases/tag/20251208) 提供 Buildroot aarch64 工具鏈及 sysroot，可作為編譯目標依據。[Smart Pro S 韌體 v1.0.1](https://github.com/trimui/firmware_smartpro_s/releases/tag/v1.0.1) 提及 SDL2 的 1280×720 旋轉修正。Smart Pro 與 Smart Pro S 有不同的官方資源，後續應以 Smart Pro S SDK 為準。

現有 [LocalStatus](../browser/monitor.py) 在設備上連續採樣兩次，讀到 CPU 約 16.4%、記憶體約 60.4%、電池 88%。初始版本溫度為 null，當時程式僅匹配 `soc-thermal`；目前 TrimUI 適配已傳入對應 thermal 類型。模組由 SSH 標準輸入在記憶體載入，沒有執行主入口、MQTT 連線、輸入接管或背光設定。這證明採樣程式可部分沿用，尚未證明完整面板能執行。

原生 App、其他繪圖方式與刷機需求見 [原生顯示研究](native-app-display-research.md)。

## 3. 網頁引擎選擇

目前採用私有 Debian rootfs 的 headless Chromium／原廠 SDL 橋接，實測結果由 [安裝說明](installation.md#驗證與限制) 管理。這能沿用 R36 的網頁引擎與共用 HTML，代價是需維護較大的私有執行環境；耗電與長時間資源用量尚未量測。

Cog／WPE 是直接使用 DRM 的候選方案，但本機試驗出現 EGL display／context 初始化錯誤，沒有產生應用程式 framebuffer，見 [失敗證據](evidence/trimui-black-screen-2026-10-20.json)。原廠 Mali 驅動與 WPE 的平台介面相容性仍是候選根因，未做底層修復確認，不能只憑換引擎成功就認定唯一根因。

[Cog DRM 文件](https://igalia.github.io/cog/platform-drm.html) 列出 GLES、GBM、DRM 與 backend 相依；原廠 App 或 SDL2 可以顯示，並不足以證明這些介面彼此相容。SDL 原生重畫會增加第二套 UI；遠端渲染則需要額外主機，因此目前保留同一份網頁，以 headless Chromium 渲染，再交由原廠 SDL 顯示。

## 4. 共用範圍與適配工作

> **Why & What - 共用前端與本機資料服務**
>
> **What:** 兩台掌機共用 HTML、資料正規化與 MQTT 處理，各自保留最少量的設備適配。
>
> **Why:** 現有服務已支援一般 MQTT broker，不需要 broker 提供 WebSocket。設備適配可容納兩種 OS、按鍵與顯示電源差異。
>
> **Alternatives considered:** 集中一台網頁服務方便統一部署與讓手機存取，但會新增常駐主機依賴，且本機電池、按鍵與螢幕控制仍需要掌機端服務。
>
> **驗證邊界：** 開發電腦的 HTML 測試與掌機的資料服務測試，都不能取代實體 LCD 驗收。

現有 [monitor.py](../browser/monitor.py) 已提供 `/status`、SSE `/events` 與 `/control`，並由 Python 接收 MQTT。[monitor.html](../browser/monitor.html) 透過同源請求顯示資料。這些介面適合繼續沿用；前端不需持有 broker 帳密。

| 檔案 | 目前實作與驗證邊界 |
| --- | --- |
| [monitor.html](../browser/monitor.html) | 共用頁面與動態設備標籤；加入短高度版面，兩台掌機尺寸測試通過，手機窄版仍待適配 |
| [monitor.py](../browser/monitor.py) | 共用 MQTT、資料正規化與 HTTP；輸入及 thermal 類型可由設備適配指定 |
| [trimui_monitor.py](../browser/trimui_monitor.py) | 依名稱尋找手把，適配本機感測器、A／B、背光與 DRM DPMS；完整實體按鍵矩陣仍待驗收 |
| [trimui_browser.py](../browser/trimui_browser.py) | headless Chromium 串流交由原廠 SDL 顯示；已確認實體畫面可見 |
| [install-trimui.sh](../browser/install-trimui.sh) 與 `browser/trimui-*.sh` | Apps 入口、私有 rootfs、停用自動休眠與退出清理；套件及還原邊界見安裝說明 |
| [test_monitor_layout.cjs](../browser/test_monitor_layout.cjs) | 以 MONITOR_VIEWPORT 測試寬高，涵蓋零／兩／四張 GPU；完整視覺基準仍待建立 |

TrimUI 使用原生 libdrm DPMS 與背光介面手動關屏，R36 透過 X11 DPMS；兩者的呼叫方式與驗收需分開處理。窄螢幕單欄與垂直捲動仍是後續提案，不屬於本次掌機版面的驗證結果。

若需要手機連入同一服務，還須修改目前僅綁定 `127.0.0.1:8766` 的設定，以及 `/control` 固定 localhost 的 Host／Origin 驗證。每個瀏覽器目前也會共用同一份選取、分頁與暫停狀態；獨立操作需要拆分瀏覽狀態。這些工作不影響兩台掌機各自執行本機服務的方案。

## 5. 驗證結果與後續工作

網頁引擎概念驗證、Apps 整合及掌機尺寸版面已完成。當前實體顯示、方向鍵延遲、A／B 事件映射與退出清理結果，統一記錄於 [安裝驗證](installation.md#驗證與限制)，避免將早期唯讀調查誤當成安裝後狀態。

後續需驗收完整實體按鍵矩陣、長時間資料更新與 MQTT 斷線恢復，並量測耗電、啟動時間和記憶體用量。建議連續執行兩小時觀察記憶體與重連；這是尚未執行的驗收提案。重新開機後的防休眠行為也需實測。

## 6. 未驗證事項

實體 LCD 已確認可見，不能再以早期 Xorg 黑屏代表目前 SDL 橋接結果。GPU 加速效益、耗電、長時間閒置、重新開機後防休眠及完整實體按鍵操作仍待驗證；手機窄螢幕尚未適配。

自架 runner、相機驗收與發布門檻見 [外部設備 CI 手冊](ci-validation.md)。目前只有人工觸發的開發與實機測試，尚未部署 CI 工作流程。
