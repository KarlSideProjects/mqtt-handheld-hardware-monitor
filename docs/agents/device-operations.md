# 設備更新與診斷

本文件供操作掌機的維護者與 agent 使用。畫面更新以 `scripts/device.py` 為入口；它只替換網頁、PVE 顯示模組與圖片，保留正在執行的採集／顯示後端、MQTT 設定與目前選取的主機或客機。後端 Python 檔案與工作副本不同時，工具會在寫入前以 `backend_requires_install` 停止，請先使用既有安裝器完整安裝並開啟監控。

## 設備與路徑

以下 IP 是目前實驗環境的連線範例，命令必須明確指定 `--host`；請以實際設備為準。

| 設備 | 範例 IP | SSH 使用者 | 應用程式目錄 | 瀏覽器 |
| --- | --- | --- | --- | --- |
| R36 MAX 2 | `192.168.5.127` | `ark` | `/home/ark/device-browser` | X11 `:0` 上的 Chromium |
| TrimUI Smart Pro S | `192.168.5.160` | `root` | `/mnt/UDISK/hwmonitor/app` | runtime 內的 Chromium／SDL |

兩台的監控 HTTP 服務均為設備本機 `127.0.0.1:8766`。PVE 採集主機與 MQTT broker 屬於採集端設定，不能從掌機 IP 推導。診斷不讀取或輸出這些帳密。

## 完整安裝後重新啟動

完整安裝器完成後，以設備工具重啟，不需要自行拼接 SSH 啟動命令：

```bash
python3 scripts/device.py restart --device r36 --host 192.168.5.127
python3 scripts/device.py restart --device trimui --host 192.168.5.160
```

重啟會先核對平台、啟動器及程序身分。R36 停止既有監控與 emulationstation，再使用既有 Ports 啟動器；失敗時嘗試恢復選單。TrimUI 停止既有監控後，使用原廠 `/tmp/cmd_to_run.sh` 排程交給 `/usr/trimui/bin/runtrimui.sh` 執行。未知排程或程序身分不符時停止，不覆寫其他應用程式的排程。

TrimUI 的 MainUI 在 SIGTERM 後仍存活時，工具只對再次核對身分的程序使用 SIGKILL；原廠迴圈支援退出碼 137。訊號透過 pidfd 綁定程序，避免 PID 重用。不要在 MainUI 執行時用 nohup 直接啟動監控，也不要終止原廠 runtrimui 迴圈。

完成條件：只剩一個監控與顯示程序；TrimUI 沒有同時執行的 MainUI，且監控由原廠迴圈持有；MQTT 就緒後持續觀察 12 秒，沒有新增 `Could not queue pageflip`。HTTP 與 MQTT 正常但新增 pageflip 錯誤，也會回報失敗並嘗試關閉新啟動的監控。

此重啟命令已通過受控程序／檔案系統邊界測試，尚未在實體掌機執行。原廠排程交接與停止 MainUI 消除閃爍的流程已於 2026-10-20 實機驗證，使用者確認閃爍停止。

## 認證與前置條件

在有本儲存庫工作副本及 Python 3 的開發電腦執行下列命令。先用一般 SSH 核對目標的主機金鑰並登錄至 `known_hosts`。工具採 `StrictHostKeyChecking=yes`；使用現有 SSH agent，或透過 `--identity /path/to/key` 指定金鑰，`--user` 可覆寫表中的使用者。

需要密碼認證時，在本機互動式終端讀入環境變數，密碼不會放進命令參數或儲存庫：

```bash
read -rs -p 'SSH password: ' HWMONITOR_SSH_PASSWORD; echo
export HWMONITOR_SSH_PASSWORD
```

完成後執行 `unset HWMONITOR_SSH_PASSWORD`。不要將 MQTT 密碼或 PVE token 當成設備 SSH 密碼。

掌機必須已開啟 Hardware Monitor 且處於喚醒狀態。更新驗證要求 MQTT 已連線並至少有一臺主機持續傳送資料；不符合條件時不會回報更新成功。

## 精簡診斷

```bash
python3 scripts/device.py diagnose --device r36 --host 192.168.5.127
python3 scripts/device.py diagnose --device trimui --host 192.168.5.160
```

輸出為 JSON，只包含設備、載入版本、網頁檔案雜湊、連線、主機數、目前瀏覽位置、PVE／Docker 資料狀態及顯示程序摘要。Docker 摘要只包含查詢狀態、容器數、新鮮度、年齡及允許的錯誤碼，不列容器明細。SSH 認證失敗、主機金鑰失敗、連線失敗及遠端 Python 失敗使用不同錯誤碼，不回傳原始 stderr。

不包含完整 `/status`、趨勢歷史、MQTT 設定、SSH 密碼或 PVE 密鑰。兩台可讀取帶有版本標記的當前頁面；尚未透過此工具載入的頁面顯示 `loaded_revision: null`。`last_verified_update` 是最後一次載入確認與時間，且必須仍符合目前檔案雜湊；該歷史紀錄不等於即時畫面檢查。

## 更新正在執行的畫面

```bash
python3 scripts/device.py update --device r36 --host 192.168.5.127
python3 scripts/device.py update --device trimui --host 192.168.5.160
```

工具檢查設備與後端相容性，取得更新鎖，建立私有備份，再逐檔原子替換畫面資產。R36 透過既有 X11 重新載入 Chromium，TrimUI 使用既有 CDP 連線；不建立第二個瀏覽器或 SDL 顯示程序。

成功條件是重新繪製的頁面將本次版本與隨機識別碼回傳至暫時的設備 loopback 確認端點，且 MQTT 連線和在線主機維持至少 11 秒。端點不對外監聽，更新結束即關閉。監控端在 10 秒後會移除停止傳送的主機，因此持續超過此期限才算有新的輸入。輸出的 `loaded: true` 與 `mqtt_observation_seconds: 11` 通過後，程序退出碼才是零。

## 失敗與回復

載入版本逾時、MQTT 中斷或檔案寫入失敗時，工具嘗試還原備份並重新載入舊頁面。JSON 的 `recovery` 分別回報 `files_restored` 與 `page_revision_restored`；任一未確認時都不應視為完整回復。舊頁面沒有版本標記時，無法確認其頁面版本，該欄維持 false。

備份位置由成功或失敗輸出的 `backup` 提供，目錄僅設備登入使用者可讀。SSH 中斷或設備斷電可能阻止自動回復；重新連線後先執行 diagnose，必要時在設備上將備份中的 `monitor.html`、`pve.js` 與 `assets/hardware-buddy.svg` 複製回應用程式目錄，再退出並重新開啟 Hardware Monitor。保留 `mqtt-config.json`，不要覆蓋它。

`backend_requires_install` 時的完整安裝與回復步驟見 [設備安裝說明](../installation.md)。畫面與連線驗證不代表實體 LCD、實體按鍵或長時間穩定性已驗收。

## 本機與實機測試

在開發電腦執行 `npm ci`、`npx playwright install chromium`，再執行 `python3 scripts/check.py --layout`。固定的本機測試清單排除關屏、喚醒及退出測試；不使用 `test_*.py` 萬用字元執行整個目錄。

實機測試入口是 `scripts/check_device.py`，必須在具有本儲存庫副本的對應掌機上執行。它先檢查設備、監控連線、輸入與顯示前置條件，再啟動有期限的測試。例如 `python3 scripts/check_device.py --device r36 --test awake` 或 `python3 scripts/check_device.py --device trimui --test screen`。退出測試會關閉監控，需同時指定 `--allow-destructive-exit` 與 `--expected-brightness`；不納入一般 CI。
