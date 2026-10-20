# R36 與 TrimUI 安裝說明

兩台設備共用網頁與 MQTT 程式，但使用各自的安裝腳本。R36 是 Debian／Xorg；TrimUI 是 Buildroot，透過私有 Debian rootfs 執行 headless Chromium，再由原廠 SDL 顯示，不能直接共用套件安裝命令。平台依據見 [TrimUI 研究](trimui-smart-pro-s-research.md)。

兩支腳本都會自動安裝相依套件。R36 使用系統 apt；TrimUI 下載固定 SHA-256 的官方 Debian ARM64 基礎映像，在內部儲存建立私有 rootfs，再由其中的 apt 安裝 Chromium、sandbox、完整套件相依、字型、CA 憑證與 Python pip，並安裝固定版本及雜湊的 paho-mqtt 與 websocket-client。SSH／MQTT 互動流程已通過模擬測試。TrimUI 採用 headless Chromium＋原廠 SDL 的橋接，使用者已確認實體 LCD 可見，兩台掌機尺寸的版面測試通過；長時間待機仍待驗收。自動化驗證方式見 [外部設備 CI 驗證手冊](ci-validation.md)。

命令標示「唯讀」時只檢查設備；SSH 包裝仍會建立並清理暫存上傳目錄。「寫入」會安裝應用程式與選單。安裝前先退出監控與遊戲，回到掌機主選單。

## 從電腦選擇安裝腳本

在已有本專案的電腦終端機執行。R36 的完整流程與還原方式見 [使用指南](user-guide.md#安裝到掌機)。

```bash
# 寫入 R36：先嘗試預設 SSH 登入；必要時提示帳密及 sudo。
bash browser/install.sh --ssh 192.168.5.127

# 寫入 TrimUI：自動安裝相依套件，再進行 MQTT 設定與 Apps 安裝。
bash browser/install-trimui.sh --ssh 192.168.5.160
```

SSH 使用者預設為 R36 的 `ark` 與 TrimUI 的 `root`。共用的 [install-remote.sh](../browser/install-remote.sh) 先嘗試金鑰／設備允許的登入方式及對應原廠預設密碼；被拒絕後，終端機會提示使用者名稱和隱藏密碼。可用 `--user USER` 指定帳號，或透過 `HWMONITOR_SSH_PASSWORD` 環境變數提供密碼。密碼不放在命令列參數，也不印出；環境變數請由私有執行環境或隱藏輸入提供，避免把密碼寫進 shell 歷史。

主機金鑰第一次連線採 `accept-new`；已知金鑰不符、無法路由或連線逾時會停止，這些情況不會要求反覆更換密碼。非互動環境無法提示帳密，登入失敗時會回報錯誤並停止。

## MQTT 預設與輸入順序

兩支腳本都呼叫 [mqtt_setup.py](../browser/mqtt_setup.py)，依以下順序選擇設定：

1. 有 `--config FILE` 時讀取該檔案。
2. 沒有指定檔案時讀取掌機既有設定。
3. 沒有既有設定時讀取 `MQTT_HOST`、`MQTT_PORT`、`MQTT_TOPIC`、`MQTT_USERNAME`、`MQTT_PASSWORD`、`MQTT_TLS`。未指定的帳密為空，先嘗試匿名登入。
4. 缺少 broker 位址時，在終端機輸入位址、TLS 與埠號。
5. 登入或訂閱遭拒時，輸入帳號及隱藏密碼，然後重試。

這些 MQTT 環境變數在執行實際安裝的掌機端讀取，SSH 包裝不會轉送電腦端的 MQTT 環境變數。從電腦提供預設設定時使用 `--config`，包裝會以私有暫存檔上傳。

```bash
# 寫入 R36：使用電腦上的私有設定；登入失敗仍可在終端機修正。
bash browser/install.sh --ssh 192.168.5.127 --config /path/to/private-mqtt.json
```

`--config` 的格式見 [設定範例](../browser/mqtt-config.example.json)。目前沒有提供專屬 broker 的預設帳密，因此腳本不會猜測非原廠的帳密組合。若有固定 MQTT 預設值，將它放在私有設定檔，或在掌機的私有執行環境設定上述變數。

安裝流程會實際進行 MQTT 3.1.1 CONNECT 與指定主題的 SUBSCRIBE，兩者成功才儲存設定。這能確認登入與訂閱權限，不能證明電腦採集端正在發資料。網路、TLS 或 broker 位址錯誤會提示修改連線設定；非互動模式遇到錯誤直接停止。

兩個平台的 MQTT 設定都存成 mode 600。TrimUI 設定放在內部儲存 `/mnt/UDISK/hwmonitor/mqtt-config.json`，不依賴 SD 卡 FAT 檔案系統的 Unix 權限。設定與備份都包含密碼，不應上傳到儲存庫或公開日誌。

## 安裝前關閉 TrimUI 自動休眠

[trimui-awake.sh](../browser/trimui-awake.sh) 在下載套件前執行，將原廠 `dimtime` 設為 `0`，並建立 `/tmp/stay_awake`、`/tmp/stay_alive`。這些旗標讓目前執行中的 keymon 立即停止自動變暗、關屏及休眠；因此不需要先重開機，下載期間也可保持網路連線。依據是實機 `/usr/trimui/bin/keymon`，SHA-256 為 `67f734851dc5b3498f0741406d3ce3b0ccecbc79cf5d20480a785f78de2b8acb`：`dimtime` 的非正值分支位於 `0x4c74`，兩個防關屏檢查位於 `0x4960`、`0x4cc0`，防 suspend 判斷位於 `0x4a00`。此結論限於該韌體二進位。

安裝器在 `/mnt/SDCARD/System/starts/90-hwmonitor-awake.sh` 建立開機入口，於原廠啟動 keymon／MainUI 前重新套用設定。面板啟動器也會補做一次。這是持續生效的設定，安裝完成或退出面板時保留；自動休眠檢查已納入 `--check`。

原設定保存在 `/mnt/UDISK/hwmonitor/original-dimtime`，重複安裝不會以零覆蓋它。第二台原值為 300，已實測改為 0，旗標與啟動入口均存在。尚未以重新開機測試整個啟動順序，也未驗證手動電源鍵的各種操作。

如要恢復原廠自動休眠，先退出面板與其他 Apps，再在掌機執行以下寫入命令；下一次執行安裝器或面板仍會依本專案設定關閉它。

```bash
# 寫入 TrimUI：移除開機防休眠入口，還原保存的計時值。
set -e
original=$(cat /mnt/UDISK/hwmonitor/original-dimtime)
/usr/trimui/bin/systemval dimtime "$original"
rm -f /mnt/SDCARD/System/starts/90-hwmonitor-awake.sh /tmp/stay_awake /tmp/stay_alive
```

## 自動安裝相依套件

若只需準備環境，可使用 `--deps-only`，不會要求 MQTT 設定或替換選單入口。R36 的這個模式允許原面板繼續執行；完整更新仍須先退出監控。

```bash
# 寫入：安裝相依套件，不進行 MQTT 設定。
bash browser/install.sh --ssh 192.168.5.127 --deps-only
bash browser/install-trimui.sh --ssh 192.168.5.160 --deps-only
```

R36 安裝 Chromium、Chromium sandbox、Xorg、Xinit、Xauth、X11 工具、Python 3、paho-mqtt、CA 憑證、DejaVu 字型、procps、util-linux 及其 apt 相依，並準備私有 GBM。已安裝的套件會保留。這個分支已在第一台成功執行，備份為 `/home/ark/hwmonitor-backup.obITyqlp`；備份可能含帳密，保持私有。

TrimUI 的 [install-trimui-deps.sh](../browser/install-trimui-deps.sh) 使用 [Debian 官方 Docker 映像來源](https://github.com/debuerreotype/docker-debian-artifacts)，固定下載 commit `cf1f4a45447842b45e9952e0f018ae734a7341c7` 的 bookworm ARM64 slim 映像。其 [映像 manifest](https://raw.githubusercontent.com/debuerreotype/docker-debian-artifacts/cf1f4a45447842b45e9952e0f018ae734a7341c7/bookworm/slim/oci/blobs/image-manifest.json) 記載 SHA-256 `c75f989a229d12b2d2613a5997de9ff3546f664c22da9248720033a2410220f6`，安裝器下載後先驗證，通過才解壓。原廠缺少 CA 憑證，因此僅此固定雜湊的 bootstrap 下載略過 TLS 憑證檢查；apt 維持 Debian 簽章驗證，後續 pip 使用 CA 驗證與固定套件雜湊。

私有 rootfs 提供 Chromium 所需的 glibc，不替換 Buildroot 的 libc。Chromium 以 UID 65534 在 headless 模式渲染同一份網頁，保留套件 sandbox。[trimui_browser.py](../browser/trimui_browser.py) 接收 loopback CDP 的 JPEG 畫面串流，再交給設備原廠 SDL／GPU 顯示。接收端逐幀確認並只保留最新影像，避免方向鍵事件排在舊影像後面。CDP 埠由 Chromium 隨機選擇，僅綁定 loopback，是此顯示橋接的必要內部通道。

安裝包含 Chromium、chromium-sandbox、Mesa 函式庫、util-linux、字型、CA、pip 與其 apt 相依。paho-mqtt 固定為 2.1.0，websocket-client 固定為 1.8.0，兩者均驗證套件雜湊。原生 libdrm、SDL2／SDL2_image 沿用已在實機確認可用的原廠函式庫；安裝器會先確認能載入。最低檢查為內部儲存剩餘 1.5 GB，下載期間需保持 Wi-Fi 連線。

此路徑不使用 Xorg 或 Cog 輸出實體 LCD。Xorg 實驗雖可讀回正常 framebuffer，實體螢幕仍黑；原廠 SDL 的單色測試及網頁橋接則已由使用者確認可見。底層差異與原生 App／刷機研究見 [原生顯示研究](native-app-display-research.md)。目前不需要刷機。

[trimui-rootfs.sh](../browser/trimui-rootfs.sh) 為安裝與瀏覽器提供暫時的裝置、共享記憶體、proc、sys 和 udev 掛載，命令結束後清理。原廠 tar 不支援 `-z`，腳本使用 gzip 管線；解壓時保留封存權限，讓 apt 的低權限下載程序可以讀取檔案。這些相容性調整來自第二台實測。

進階使用者仍可用 `--runtime DIR` 提供自己的 runtime，略過自動建置。該目錄須有可執行的 `bin/chromium`，接受本機頁面 URL 並負責 SDL／瀏覽器生命週期，額外函式庫放在 `lib/`，純 Python paho 2.x 與 websocket-client 放在 `python/`。一般安裝不需要這個參數。

安裝器將程式與 runtime 放在 `/mnt/UDISK/hwmonitor/`，在 `/mnt/SDCARD/Apps/HardwareMonitor/` 建立入口，並在內部儲存建立應用程式、設定與選單的私有 `backup.*` 備份。相依套件環境保留在 runtime，避免每次備份重複儲存整個 rootfs。它不使用原廠系統的 apt、systemd、Xorg 或 R36 的遊戲手把路徑。`chromium --version` 通過只代表可載入程式及基礎相依，畫面仍須實際開啟驗證。

## TrimUI 按鍵操作

選單入口與實體按鍵位置見 [遊戲機操作圖解](device-controls.md)。

關屏／喚醒鍵以機身標示的 **X 鍵** 為準，對應事件碼 308；沿用目前按鍵設定。

[trimui_monitor.py](../browser/trimui_monitor.py) 依名稱尋找 `TRIMUI Player1`，避免依賴可能變動的 event 節點編號。

| 按鍵 | 操作 |
| --- | --- |
| 方向鍵／類比搖桿 | 選取、翻頁及切換資訊類別，導覽規則與共用網頁相同 |
| A | 開啟設備或資訊卡詳細頁，事件碼 305 |
| B | 逐層返回，事件碼 304 |
| L／R | 翻頁或切換上一台／下一台設備 |
| Start | 在總覽暫停／恢復輪播 |
| X | 關閉背光並透過 DRM DPMS 停用顯示，再按一次恢復低亮度畫面；MQTT 繼續接收 |
| Select + Start | 退出監控，回到原廠選單 |

A／B 映射依使用者的實體標籤回報修正；事件注入已確認 305 開啟、304 返回，修正後的完整實體按鍵驗收仍待執行。X 鍵使用原生 libdrm 的 connector DPMS，在關閉時先將背光設為零，再切換顯示為 Off；喚醒先切回 On，再恢復監控亮度。SDL 呈現與電源切換共用鎖，關屏時停止送出 pageflip。這不會讓 Linux 或 Wi-Fi 進入系統休眠，自動休眠仍由前述設定與旗標停用。喚醒失敗時可再按 X 重試，退出或啟動失敗時會嘗試恢復顯示與原背光。

此韌體已實測 DPMS Off 時顯示管線 active=0，喚醒後為 On／active=1；這是驅動狀態證據，實際耗電與各面板電源軌仍未量測。原廠電源鍵還可能影響無線網路，因此本功能使用 X，不接管電源鍵。介面研究見 [原生顯示研究](native-app-display-research.md#手動關屏與背景監控)。

## TrimUI 備份還原

備份只包含應用程式、MQTT 設定與選單，不包含 runtime 或防休眠設定。以下命令不能完整回復瀏覽器環境；還原舊版應用程式前，需另確認它與保留的 runtime 相容。

如需還原，先退出監控，使用安裝輸出的確切備份目錄。以下為尚未實機驗證的還原分支，會移除目前 Hardware Monitor，再還原備份；其他 Apps 不受此命令指定範圍影響。

```bash
# 寫入 TrimUI：在掌機終端機還原，先替換成安裝輸出的確切目錄。
backup='/mnt/UDISK/hwmonitor/backup.<安裝輸出代碼>'
set -e
test -f "$backup/files.tar.gz"
gzip -dc "$backup/files.tar.gz" | tar -tf - >/dev/null
rm -rf /mnt/UDISK/hwmonitor/app /mnt/SDCARD/Apps/HardwareMonitor
rm -f /mnt/UDISK/hwmonitor/mqtt-config.json
gzip -dc "$backup/files.tar.gz" | tar -C / -xf -
```

## 驗證與限制

```bash
# 唯讀：檢查已安裝檔案與依賴；不會測試 MQTT 連線。
bash browser/install.sh --ssh 192.168.5.127 --check
bash browser/install-trimui.sh --ssh 192.168.5.160 --check

# 開發電腦：模擬 SSH 預設登入／隱藏輸入，以及 MQTT 握手／訂閱、TrimUI 適配。
python3 browser/test_install.py
python3 browser/test_trimui_browser.py
python3 browser/test_trimui_power.py
```

使用者已確認原廠選單、原生 SDL 換色與 SDL 橋接監控頁都能在實體 LCD 顯示。正常執行日誌為 `/mnt/UDISK/hwmonitor/launch.log`；實作與測試結果適用於這台 Smart Pro S，其他韌體仍需重驗。

2026-10-20 在第二台使用 Chromium 155.0.8059.79、原生 SDL2 與 1280×720 viewport。開發電腦版面測試涵蓋 1024×768、1280×720 與 Xorg 實驗時的 1279×719，包含 0／2／4 GPU。較窄的手機版面尚未完成適配。

方向鍵測試從 evdev 事件寫入，量到正在輸出的 SDL framebuffer 選取底色改變，顯示橋接優化後的一輪五次約為 212 至 220 毫秒，原始數值與先前對照保存在 [SDL 驗證紀錄](evidence/trimui-sdl-2026-10-20.json)。這是數位顯示輸出延遲，不是相機量測的 LCD 光學延遲。修正包含最新影像槽、畫面串流背壓，以及避免 websocket-client 對大型影像執行重複的純 Python UTF-8 驗證；正常文字接收仍執行嚴格 UTF-8 解碼。[固定版本官方說明](https://github.com/websocket-client/websocket-client/blob/v1.8.0/docs/source/faq.rst)。

實機回歸測試如下。它們會寫入方向鍵事件或關閉監控，執行前需在測試掌機開啟 App；輸入延遲測試使用三台在線主機的 1280×720 總覽。

```bash
# 寫入實機：在 TrimUI 有本專案 browser 原始碼的目錄執行。
python3 measure_trimui_input.py
# 寫入實機：三輪 X 關屏／喚醒，第一輪保持關屏 12 秒；需有即時 MQTT 資料。
python3 test_trimui_screen.py
# 寫入實機並退出：31 是此設備進入監控前的背光原值。
python3 test_trimui_exit.py --expected-brightness 31
```

最後一輪退出耗時 1.85 秒。退出測試確認回到原廠選單、恢復背光 31、原生瀏覽器橋接結束，臨時掛載與鎖定目錄清空。防休眠設定保留。實測資料由 [SDL 驗證紀錄](evidence/trimui-sdl-2026-10-20.json) 保存；[Xorg 實驗紀錄](evidence/trimui-chromium-2026-10-20.json) 與 [Cog 黑屏紀錄](evidence/trimui-black-screen-2026-10-20.json) 保留為失敗案例。

X 鍵三輪關屏／喚醒測試通過，第一輪關屏保持 12 秒，超過主機資料的 10 秒過期門檻，MQTT 與三台主機持續在線。關屏時 DPMS Off、CRTC active=0、背光為零；喚醒恢復 On／active=1。從關屏狀態直接退出耗時 2.36 秒，恢復原廠選單、背光 31 並釋放瀏覽器、掛載與鎖。加入關屏協調後，方向鍵數位顯示延遲回歸測試五次約為 203 至 237 毫秒。完整數值見 [關屏驗證紀錄](evidence/trimui-screen-power-2026-10-20.json)。此三輪測試使用事件注入；使用者已確認此功能對應機身 X 鍵，完整實體按鍵操作矩陣仍待驗收。

長時間穩定性、耗電、重新開機後防休眠及全部實體按鍵操作，仍需驗證。
