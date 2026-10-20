# TrimUI Smart Pro S 原生 App 與顯示層研究

目前採用原廠 SDL 顯示 headless Chromium 的網頁影像；最小換色 App 與監控頁均已確認可見。目前沒有證據顯示自製 App 必須先刷機。Xorg 可讀回完整 Chromium framebuffer，但使用者確認該路徑 LCD 仍全黑。headless Chromium＋原廠 SDL 的橋接已由使用者確認實體可見。

研究來源為 2026-10-20 透過 Firecrawl 讀取的官方 SDK、韌體及 SDL/Linux 文件，以及實機二進位。以下區分官方資料、反組譯觀察與實驗結果；沒有執行刷機。

## 官方支援與版本邊界

Smart Pro S 是 TG5050，官方 SDK 明載 Buildroot aarch64，包含 host/bin 工具鏈與 host/aarch64-buildroot-linux-gnu/sysroot。[TG5050 SDK release 20251208](https://github.com/trimui/toolchain_sdk_smartpro_s/releases/tag/20251208)。舊 Smart Pro 是 TG5040，官方另有 [TG5040 SDK](https://github.com/trimui/toolchain_sdk_smartpro)；舊裝置的圖形庫、編譯選項與 plane 編號不能直接套用。

官方 TG5050 firmware v1.0.1 說明列出 SDL2 非 1280x720 模式的意外旋轉修正，以及 Apps/ports HOME 儲存修正。[韌體 v1.0.1](https://github.com/trimui/firmware_smartpro_s/releases/tag/v1.0.1)。因此原生測試先用 1280x720，再依實機韌體版本處理其他尺寸。這不表示所有黑屏都由旋轉造成。

官方 SD package 已有 ports 啟動腳本及 CPU 設定腳本。[TG5050 SD package](https://github.com/trimui/assets_smartpro_s)。官方提供自製程式使用的 SDK，且本機已有 Apps 啟動方式，本次未找到「執行自製 App 必須先刷機」的官方要求。這支持先在 stock 系統使用相容二進位與獨立 Apps 目錄；韌體升級/SD recovery 是另一項操作，不能當作目前黑屏的必要修正。

SDK 公開 git tree 僅 README，開發內容放在 release 壓縮包。此研究未下載整個約 1.11 GB SDK，不能宣稱已驗證內部 SDL 範例或廠商 SDL 原始碼。官方沒有公開可直接引用的 TG5050 OSD/plane/colorkey 設定手冊。

## OSD 遮擋假說與排除邊界

實機觀察：Xorg 位於 vch0 plane 93、normalized-zpos=0，原廠 trimui_osdd 位於 uch2 plane 119、normalized-zpos=1；後者是全螢幕 XR24，alpha 顯示 255、premult。Linux DRM 的 zpos 定義是較大值位於較上層，沒有像素 alpha 的格式會以像素 alpha=1 合成。[Plane composition properties](https://docs.kernel.org/gpu/drm-kms.html#plane-composition-properties)。XR24 是 XRGB8888，X 不是 ARGB 的 alpha。

早期據此提出「全螢幕黑色 OSD 遮住下層 dashboard」的假說；後續停用 OSD 仍黑屏，故它不能單獨解釋此現象。應先讀回 OSD FB 像素與 property 範圍：標準 DRM alpha 是 0..65535，廠商顯示 255 可能有自己的範圍，不能未查就假定其值。colorkey 是驅動專屬狀態，此次未找到 TG5050 官方說明，也不能直接假設黑像素一定會透明。

實機原廠 MainUI SHA256 為 `2771c6a08901323693d22402e641d19542d3f878dbab56822f86270921d5f7e2`。readelf 證實它動態依賴原生 `libSDL2-2.0.so.0`、SDL_ttf/image/mixer；字串還包含 `touch /tmp/trimui_osd/osdd_quit`、`touch /tmp/trimui_osd/osdd_rotate`、`/tmp/trimui_osd/osdd_show_up` 與 `/dev/disp`。這提供原廠控制介面的線索，但字串本身不能定義所有操作語意。

實機 `/usr/trimui/osd/trimui_osdd` 的 SHA256 為 `995f0c5d855a4c2cd7c25c0b60476bf218e79c8264b82f41a2ac58116f0e4adc`。pyelftools 與 Capstone 反組譯證實：

- 主迴圈 `0x2fc0..0x2fd0` 對 `/tmp/hide_osdd` 執行 access，存在時跳至 `0x31c0`。
- hide 路徑呼叫 `0x8360` 與 `0x127d0(0,0)`，然後以 unlink 移除旗標。show 路徑來自 `/tmp/show_osdd`，呼叫 `0x127d0(1,250)`。
- `0x127d0` 將控制序列第五個 word 設為 0；show 分支將它設為 255。worker `0x12664` 讀序列並交給 `0x8c50`。
- `0x8c50` 的隱藏路徑選擇全域備用 framebuffer，再經 `0x8970` 呼叫 drmModeSetPlane。這條路徑沒有把 framebuffer ID 直接設為 0，不能宣稱 hide 必然停用整個 plane。
- 原廠程式內部依模式使用 plane 113 (`0x71`)、119 (`0x77`) 或 93 (`0x5d`)。這些值來自此特定實機二進位，不是可移植的通用 ID。
- `echo -1 > /sys/class/de_plane/de_plane/attr/rmpos` 出現在 `0x30a4..0x30ac` 的退出 cleanup 路徑，並非 hide 路徑。不要把它解讀成已證實安全的 hide 指令。

`touch /tmp/hide_osdd` 曾列為候選實驗，但旗標處理成功並不能證明畫面可見。後續使用原廠 `osdd_quit` 停用 OSD 的實驗結果見下文；正式安裝器沒有加入這類 OSD 操作。

## 原生 SDL 與其他繪圖路徑

先使用設備原生 SDL2 庫，列出 `SDL_GetNumVideoDrivers` / `SDL_GetVideoDriver`，再跑 1280x720 單色測試。可以透過現有 Python ctypes 呼叫，不需要先編譯 App 或下載整個 SDK。候選 API 是 SDL_Init(SDL_INIT_VIDEO)、SDL_CreateWindow、SDL_GetWindowSurface、SDL_FillRect、SDL_UpdateWindowSurface；若該 backend 不支援 window surface，再測 SDL_CreateRenderer/RenderClear/RenderPresent。測試必須輸出 SDL_GetError，記錄實際 driver/renderer。

SDL 官方允許使用 SDL_VIDEODRIVER 選 backend，但可用值取決平台與編譯選項。官方表格把 fbcon 列為 SDL1，不是 SDL2；不能直接指定 SDL2=fbcon。kmsdrm 是 SDL2 的一條路徑，原廠客製 SDL 可能有其他 backend，應以實際枚舉為準。[SDL driver FAQ](https://wiki.libsdl.org/SDL2/FAQUsingSDL)。SDL_KMSDRM_DEVICE_INDEX 自 SDL 2.24.0 才提供，選擇 cardNN，不能用它選任意 plane。[Device index hint](https://wiki.libsdl.org/SDL2/SDL_HINT_KMSDRM_DEVICE_INDEX)。

fbdev 或 pic2fb 可用作單張測試圖，但應先確認 `/dev/fb*` 實際連到哪個 plane。只把圖寫進可讀 framebuffer，不保證其所在 plane 在最終合成上可見。此次沒有找到 TG5050 官方 pic2fb 程式或其支援說明；社群同名二進位不能當成原廠驗證工具。

Direct DRM/libdrm 測試可選 connector、CRTC 與 plane，並記錄 plane 的格式、zpos 和 alpha。這能測顯示控制器合成，但需避免與 Xorg 或 OSD 同時搶 DRM master/plane，並保留原狀態以供恢復。後續已確認停用 OSD 不足以修正 Xorg 黑屏；目前沒有完成直接 DRM 路徑的修復驗證。

若原生 SDL 可見，可把它作為原生儀表板載體，但重做 UI 會失去現有共用 HTML 的單一實作。另一種橋接是原生 SDL 顯示網頁 raster frame，仍需要持續渲染與輸入同步，並不等同完整網頁瀏覽器。兩者都應在單色探測完成後再評估。

## 本次設備試驗與下一步

原生 Python ctypes 已成功載入系統 SDL2，枚舉到 KMSDRM、offscreen、dummy 與 evdev。使用 KMSDRM、1280×720 全螢幕和 accelerated renderer 的單色測試完成紅／綠／藍切換，程式未回報 SDL 錯誤。使用者已確認實體 LCD 顯示紅／綠／藍換色。對照原廠 MainUI 反組譯後，測試採 SDL_Init(0x221)、SHOWN 視窗旗標 4、accelerated＋vsync renderer 旗標 6，以及 SDL_RENDER_SCALE_QUALITY=1。

另一輪試驗使用原廠 `osdd_quit` 旗標暫停 OSD，再啟動 Chromium。DRM 與廠商 blender 狀態均確認只剩 Xorg plane，使用者仍回報全黑。因此 OSD 遮擋不能單獨解釋此現象，尚不應把 OSD 停用寫入正式安裝器。退出監控後，原廠啟動流程已重新啟動 OSD 和 MainUI。

使用者已確認原廠選單正常顯示，因此螢幕與原廠顯示路徑可用，目前沒有必要以刷機作為第一步。原生 SDL 單色及網頁橋接均已確認可見。因此已實作原廠 SDL 顯示 headless Chromium 網頁影像的方案，保留共用 HTML；影像更新與按鍵延遲的修正結果見安裝說明。原生 SDL 重做 UI 仍是未採用的替代方案。

韌體升級僅在核對當前版本、官方修正內容與恢復方式後另行評估。Smart Pro S 的 TG5050 韌體、SDK 和 SD package 必須互相對應，不能使用舊 Smart Pro 的 TG5040 映像。


## 共用網頁的已實測橋接

[trimui_browser.py](../browser/trimui_browser.py) 讓 headless Chromium 提供 JPEG 串流，由原廠 SDL_image 載入 texture，再經 SDL_RenderCopy／RenderPresent 顯示。實體可見性已由使用者確認；安裝與延遲結果由 [安裝驗證](installation.md#驗證與限制) 管理。這個方案保留共用 HTML、MQTT 與原生按鍵服務，不需要第二套儀表板 UI 或刷機。

[CDP Page.startScreencast](https://chromedevtools.github.io/devtools-protocol/tot/Page/#method-startScreencast) 產生影像事件，每幀須確認；裝置支援時使用單幀背壓與最新影像模式。SDL 在主執行緒依序載入 texture、清除、複製、呈現並釋放 texture，API 依據為 [IMG_LoadTexture_RW](https://wiki.libsdl.org/SDL2_image/IMG_LoadTexture_RW) 與 [SDL_RenderPresent](https://wiki.libsdl.org/SDL2/SDL_RenderPresent)。這些官方介面證明可用的開發方式，並非對任意韌體的效能保證。
