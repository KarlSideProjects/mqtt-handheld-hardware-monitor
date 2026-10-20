# PVE、CT 與 VM 監控研究及模組化規劃

狀態：提案，尚未實作。讀者：採集端、安裝器及掌機顯示端維護者。

## 1. 建議方案與責任分工

建議在 `hwmonitor-mqtt` 的採集端加入獨立 PVE 模組，沿用 MQTT broker 傳送資料；掌機增加「PVE 主機 → CT／VM 清單 → 個別資源」的瀏覽。第一版採集器安裝在 PVE 主機，沿用 Linux 實體硬體監控，再透過 PVE API 補上虛擬資源。CT 是 LXC 容器，VM 是 QEMU 虛擬機。

| 元件 | 規劃變更 | 安裝及權限 |
| --- | --- | --- |
| 採集端安裝器 | 辨識目標 OS、PVE 與執行環境，派送至獨立平台模組 | 安裝服務時才使用必要的管理權限 |
| 一般 Linux 模組 | 採集本機硬體；維持既有 Linux 行為 | 不要求 PVE API 設定 |
| Windows 模組 | 沿用 Windows 採集與排程安裝 | 不載入 Linux 或 PVE 工具 |
| PVE 模組 | 組合 Linux 硬體資料與 CT／VM API 資料 | 專用唯讀 PVE API token |
| MQTT broker | 沿用傳輸；檢查既有 ACL 是否允許主機 topic | 不持有 PVE token，不執行平台辨識 |
| 掌機服務及網頁 | 保留階層、狀態與資料來源，加入客機清單及導覽 | 不直接連 PVE API |
| CT／VM 內部 | 基礎資源監控不需安裝程式 | 需要檔案系統、程序或 GPU 細節時另議 |

本提案涵蓋辨識、安裝、採集與顯示的模組邊界。不包含開關機、建立／刪除 VM、遷移控制，也不預設安裝 QEMU Guest Agent。所有新欄位與行為均為提案，不能視為現有功能。

## 2. 已核對的現況

程式依據為掌機倉庫 commit `247bc0b058be3faf7c418de96dfd2353f8d460b6`，以及本機採集端 checkout `/home/karl/Workspace/Tools/hwmonitor-mqtt` 的 commit `445a2342940108c85fb246a1ec84272e95930f4d`。本機採集端 remote 是 `jhihweijhan/hwmonitor-mqtt`，掌機 README 連結的是 `KarlSideProjects/hwmonitor-mqtt`；實作前須確認交付的採集端倉庫，不能假定兩者版本相同。

| 已核對事實 | 原始碼依據 | 對規劃的影響 |
| --- | --- | --- |
| 預設訂閱 `sys/agents/+/metrics` | [mqtt_start](../browser/monitor.py)，341-381 行 | 沿用現有 topic，將客機資料放在父主機訊息內 |
| 正規化只取 CPU、GPU、RAM、I/O 等既有欄位 | [normalize](../browser/monitor.py)，33-60 行 | 單純多傳 PVE 欄位，顯示端仍不會保留它 |
| 主機以 `host` 字串作索引 | [Monitor.receive](../browser/monitor.py)，188-224 行 | 新增獨立資源 ID，避免客機同名或與主機相撞 |
| 主機逾時為 10 秒；最多 128 台主機，單則訊息上限 262144 bytes | [Monitor.receive／tick](../browser/monitor.py)，188-243 行 | 客機不能直接塞進頂層主機列表；必須控制訊息大小與新鮮度 |
| 歷史保留最近 60 次接收；介面以固定資訊卡顯示 | [monitor.py](../browser/monitor.py)，210-218 行；[monitor.html](../browser/monitor.html)，163-218 行 | 重送快取不可重複寫入客機歷史；虛擬資源需依能力顯示 |
| TrimUI 使用同一份 Monitor、HTTP handler 及網頁 | [trimui_monitor.py](../browser/trimui_monitor.py)，143-150 行 | PVE 顯示做一次，設備按鍵及顯示驅動維持獨立 |
| Linux sender 已有完整硬體 payload、MQTT publish 與可調發布週期 | 採集端 `hwmonitor_mqtt/agents/agent_sender_async.py`，39-46、743-763、884-910、946-949 行 | 保留實體溫度與 GPU；PVE 採集不能阻塞既有發布 |
| Windows 已有獨立 sender 與排程安裝腳本 | 採集端 `hwmonitor_mqtt/agents/agent_sender_windows.py`、`scripts/windows/install_windows_sender_task.ps1` | 保留入口相容性，將選擇與實際安裝分離 |
| Compose agent 綁定 host PID/network、GPU 路徑及 privileged 設定 | 採集端 `docker-compose.yml`；`Dockerfile` 使用 Python slim image | 不能把既有 Compose 配置當作所有 OS／系統的通用安裝模板 |
| HTTP 靜態資源路由及兩台掌機的安裝檔案清單為明確列舉 | [handler](../browser/monitor.py)，476 行起；[R36 安裝器](../browser/install.sh)，119 行起；[TrimUI 安裝器](../browser/install-trimui.sh)，66、90 行 | 新功能模組必須同步加入服務路由、檔案安裝及安裝檢查 |

結構探索使用 codebase-memory，並檢查上述程式及測試路徑的索引覆蓋；回報為 metadata_match、無已記錄缺口。另直接讀取關鍵來源核對。這是限定範圍的研究，不是全倉庫稽核。

## 3. OS、系統與安裝角色的模組邊界

使用者要求安裝器先辨識系統，再選擇處理方式。建議辨識結果分開保存 OS、系統類型與執行環境，例如 `os=linux`、`system=pve`、`runtime=host`。PVE 保留 Linux 屬性，派送時採 PVE 專屬處理。

另外區分安裝角色：`agent` 是被監控端，`display` 是掌機顯示端。R36／TrimUI 的顯示安裝器繼續由本倉庫管理；Linux／Windows／PVE 的採集安裝器由採集端倉庫管理。PVE 裡的 Linux VM 仍走一般 Linux 模組，Windows VM 仍走 Windows 模組。

| 辨識順序 | 判定證據與提案行為 | 不確定時 |
| --- | --- | --- |
| 安裝目標及角色 | 遠端安裝檢查遠端主機；不能以執行安裝工具的電腦代替 | 顯示目標及辨識依據，停止依賴該資訊的寫入 |
| OS | Windows 使用系統 API；Linux 讀 OS 資訊及 `/etc/os-release` | 回報 unsupported，不嘗試 Linux 套件指令 |
| PVE 節點 | Linux 下，確認 `pve-manager` 已安裝且 `pveversion` 成功；`/etc/pve` 作佐證 | 出現 PVE 跡象但驗證失敗時回報偵測錯誤，不默默退回一般 Linux |
| 一般 Linux | 無 PVE 節點證據後，依 distro、版本、套件管理器及服務管理器選安裝方式 | 未支援的發行版可輸出手動步驟，不套用 Debian 安裝命令 |
| 容器內執行 | 分開記錄容器 OS 與宿主機辨識；宿主安裝器將檢查結果傳入配置 | 既有容器缺少宿主資訊時要求明確 target 設定，並以 API 驗證 |

`pveversion` 的用途可追溯到 [Proxmox 官方腳本](https://github.com/proxmox/pve-manager/blob/master/bin/pveversion)。上述多項證據組合是本提案的偵測策略，仍須以實際部署驗證。Debian 名稱、PVE kernel、QEMU 虛擬硬體或單一檔案存在，都不能獨立決定選用 PVE 模組。

> **Why & What - 明確派送與模組組合**
>
> **What:** 偵測器只回傳辨識結果；安裝器按結果選模組；PVE 採集模組組合 Linux 基礎採集與 PVE API adapter。
>
> **Why:** OS 判定、套件安裝、PVE API 與 MQTT 各有不同失敗方式；分離後可以單獨測試，並避免 Windows 載入 Linux 依賴。
>
> **Alternatives considered:** 單一大腳本便於最初交付，但平台條件會散落在採集及安裝流程；動態 plugin framework 可供第三方擴充，現階段沒有這個需求。
>
> **Fallback:** 使用固定模組表及少量明確函式，不建立 plugin 掃描、動態載入或通用工作流引擎。

規劃中的採集端檔案邊界如下，名稱為建議，尚未建立：

| 檔案／目錄 | 單一責任 | 允許依賴 |
| --- | --- | --- |
| `hwmonitor_mqtt/platforms/detect.py` | 辨識 OS、系統與執行環境；不安裝、不連 MQTT | 系統查詢及標準函式庫 |
| `hwmonitor_mqtt/collectors/linux.py` | Linux 本機硬體採集 | 既有 Linux 工具 |
| `hwmonitor_mqtt/collectors/windows.py` | Windows 本機硬體採集 | 既有 Windows 工具 |
| `hwmonitor_mqtt/collectors/pve.py` | 清單、PVE 欄位對應、累積量差分及快取 | PVE API adapter；不安裝套件、不 publish |
| `hwmonitor_mqtt/clients/pve.py` | HTTPS、token、TLS、timeout 與 API 回應驗證 | 標準 `urllib`／`ssl` 即可先做 |
| `hwmonitor_mqtt/transport/mqtt.py` | 連線、序列化、發布及重連 | paho-mqtt；不知道 PVE API 細節 |
| `scripts/install-linux.sh` | Linux 相依套件及服務安裝 | 該平台支援的套件與服務工具 |
| `scripts/install-pve.sh` | PVE 檢查、Linux 共用安裝、唯讀 API 配置驗證 | Linux 安裝共用部分及 PVE adapter 檢查入口 |
| `scripts/windows/install_windows_sender_task.ps1` | Windows 相依套件與排程安裝 | 既有 PowerShell 流程 |

既有兩支 sender 保留為啟動入口，負責選模組、排程與發布。先抽出實際要共用的部分，保留既有錯誤處理及測試，不一次重寫所有硬體採集。安裝器與採集器不得互相 import；匯入模組不得觸發安裝、背景服務或網路連線。

PVE 偵測成功只決定模組，不代表已取得 API 權限。缺少 token 時，PVE 設定狀態應為「待設定」，本機硬體仍可採集；不能顯示「沒有 CT／VM」。相依套件依能力安裝，不因為是 Linux 就強制掛載 NVIDIA 路徑，也不為唯讀 API 採集新增 privileged 要求。

顯示端也按功能分離：建議新增 `browser/pve.py` 處理客機資料驗證、快取新鮮度及客機狀態；新增 `browser/pve.js` 處理客機清單及詳細頁。`monitor.py` 保留 MQTT 接收、通用按鍵及頁面派送，`monitor.html` 保留主畫面與共用格式化函式。PVE 模組只接受資料及明確傳入的共用函式，不存取 MQTT 連線或設備驅動；通用主畫面也不解析原始 PVE API。這些檔案是功能邊界，不要求為每個指標各建一個模組。

## 4. PVE API 能取得的資料與限制

官方資料於 2026-10-20 透過 Firecrawl 讀取，研究涵蓋目前公開 API schema 及原始碼；實際 PVE 版本尚未知。PVE API 使用 HTTPS 8006，支援獨立權限的 API token。[官方 API 說明](https://pve.proxmox.com/wiki/Proxmox_VE_API)

| API，以下省略 `/api2/json` | 規劃用途 | 使用注意事項 |
| --- | --- | --- |
| `GET /cluster/resources?type=vm` | 一次取得可見 VM／CT 的 node、vmid、type、狀態及資源統計 | 回應受權限過濾；PVE 模組只取指定 node 的客機 |
| `GET /nodes/{node}/status` | 遠端採集方案的主機概況或診斷 | 首版主機硬體仍沿用 Linux 採集 |
| `GET /nodes/{node}/qemu?full=1`、`GET /nodes/{node}/lxc` | 清單統計的診斷或版本相容替代 | QEMU `full=1` 才要求完整狀態，可能增加節點工作量 |
| `GET /nodes/{node}/qemu/{vmid}/status/current`、LXC 對應路徑 | 特定資源診斷、比對缺少欄位 | 首版不為每台 guest 每輪發一個請求 |

端點及欄位依據：[官方 API viewer](https://pve.proxmox.com/pve-docs/api-viewer/)、[官方 API schema](https://pve.proxmox.com/pve-docs/api-viewer/apidoc.js)。API viewer 需 JavaScript；研究另讀 schema 核對，不能只依網頁空殼判定欄位。

| 指標 | 可取得範圍 | 顯示及換算規則 |
| --- | --- | --- |
| CPU | 客機 CPU 使用比例與 vCPU 數 | 目前來源已依客機 CPU 數正規化，使用率乘 100；不得再除以 vCPU 數 |
| RAM | PVE 回報的 `mem`、`maxmem` | 可算比例，但標示「PVE 記憶體統計」，不稱為客機應用程式實際用量 |
| 網路 | `netin`、`netout` 累積 bytes | 相鄰有效觀測差分後除以實際間隔，才是 B/s |
| 磁碟 I/O | `diskread`、`diskwrite` 累積 bytes | 與網路相同；第一筆、重開機、遷移或 counter 回退時顯示未知 |
| 虛擬磁碟配置 | 部分 `disk`／`maxdisk` 欄位 | 必須按 QEMU／LXC 語意區分，不能推導 VM 檔案系統剩餘空間 |
| GPU、VRAM、溫度、程序 | 這批 API 不足以提供客機內完整細節 | 顯示不支援；需要時才設計客機端擴充 |

CPU 與記憶體語意見 [QemuServer.pm](https://github.com/proxmox/qemu-server/blob/master/src/PVE/QemuServer.pm) 及 [LXC.pm](https://github.com/proxmox/pve-container/blob/master/src/PVE/LXC.pm)。QEMU 記憶體可能來自 host cgroup，也可能在可用時採 balloon 統計；QEMU balloon driver 與 QEMU Guest Agent 是不同元件。基礎監控不以安裝 Guest Agent 為前提。

VM 檔案系統細節可另評估 QEMU Guest Agent；相關 API 的權限需逐端點檢查，不能假定唯讀 PVEAuditor 足夠。[QEMU Guest Agent 官方說明](https://pve.proxmox.com/wiki/Qemu-guest-agent)、[API schema](https://pve.proxmox.com/pve-docs/api-viewer/apidoc.js)

PVE 的 `pvestatd` 目前以約 10 秒週期更新狀態，cluster resources 讀取快取統計。建議 PVE 模組以該週期起步，這是工程選擇，不是 API 每秒請求上限；更快 polling 不保證更多有效樣本。[pvestatd 原始碼](https://github.com/proxmox/pve-manager/blob/master/PVE/Service/pvestatd.pm)、[API2Tools 原始碼](https://github.com/proxmox/pve-manager/blob/master/PVE/API2Tools.pm)

## 5. 採集位置、權限與資料新鮮度

> **Why & What - 主機端模組先行**
>
> **What:** PVE 安裝模組在目標 PVE 主機啟動單一 sender；Linux collector 提供實體數據，PVE collector 透過 HTTPS 讀客機統計。
>
> **Why:** 現有硬體及溫度可沿用，父主機 payload 只有一個發布者，避免兩個 sender 互相覆寫。代價是每台 PVE 主機都要部署及更新採集端。
>
> **Alternatives considered:** 集中式遠端 collector 可免裝主機端程式，也較易統一 token；但需處理既有主機資料合併，且 API 無法取代全部實體感測器。`pvesh` 免 API token，但通常須在節點以 root 執行。
>
> **Fallback:** 若使用者要求 PVE 不安裝程式，沿用獨立 PVE adapter 改成遠端 collector；先確認父主機唯一發布者與實體感測資料取捨。

API 使用專用使用者及啟用權限分離的 token。`PVEAuditor` 是唯讀起點，依 `/nodes`、`/vms` 或目標範圍配置 ACL；權限分離時，使用者與 token 都必須具備需要的權限，其有效權限為交集。安裝檢查必須驗證目標 node 及預期客機可見性，HTTP 200 不代表清單完整。[官方權限與 token 文件](https://pve.proxmox.com/pve-docs/pveum-plain.html)

PVE token、CA 檔與 MQTT 帳密由私有配置持有，不進 payload、Git、瀏覽器或一般 log。TLS 應驗證 CA 與主機名稱；自簽環境匯入可信 CA，不將略過驗證當預設。預先建立唯讀 token 即可，不要求提供 root 登入密碼。

Linux 主機數據維持既有發布節奏，PVE API 輪詢由獨立工作處理，設有限 timeout 且不重疊執行；MQTT 發布只讀最新快取。這樣既有主機逾時規則仍可使用，API 暫時失敗也不阻塞硬體監控。

客機統計另帶成功觀測時間，提案以 30 秒作過期門檻。重送快取不能刷新該時間或重複增加趨勢點；PVE API 失敗時保留最後清單並標示過期。端點未回報底層快取的精確樣本時間時，畫面只能保證 API 觀測時間，不能宣稱是全新硬體樣本。

## 6. MQTT 擴充與掌機介面

建議沿用完整 host payload，只新增可選的 `virtualization` 區塊，不把每台 CT／VM 發成頂層電腦。保留既有 CPU、RAM、GPU 欄位，讓一般主機繼續使用現有資料路徑。PVE 主機本身也不以 Linux 名稱或 hostname 字串猜類型，而由明確能力資訊決定介面。

以下是擬議資料語意，正式欄位 schema 及 fixture 在實作時集中定義；本節不宣稱既有 sender 已支援：

| 資料 | 必要內容 | 語意及錯誤處理 |
| --- | --- | --- |
| `virtualization` | 版本、provider=pve、cluster ID、node、成功觀測時間、查詢狀態、guests | 一般主機省略；不以 null 或空清單代表查詢失敗 |
| `guests` | 成功完整查詢後的全量陣列 | 成功空陣列才代表範圍內沒有客機；失敗保留舊清單及時間 |
| 客機識別 | cluster ID、type=qemu/lxc、vmid、node、name、status、uptime | 穩定 ID 為 cluster ID + type + vmid；node 是目前位置，name 只是顯示名稱 |
| 客機指標 | CPU、vCPU、PVE RAM 使用量／上限、網路及磁碟速率 | 沿用可共用的數值及單位欄位；未知為 null，明確量到零才填 0 |
| 能力及來源 | 可用指標與記憶體統計來源 | 缺 per-core 資料不顯示「0 核心」；GPU 直通不能據此推定負載 |

cluster ID 為配置中的穩定識別值，不以可能重複的 cluster 名稱當唯一 ID。每個父主機只發布該 node 的客機，避免每台 PVE 節點都重複列出整個 cluster。遷移後穩定 ID 不變，重新建立差分基線；第一版不保證跨節點趨勢連續保存。

接收端驗證版本、型別、ID 唯一性、有限數值、陣列及訊息大小，沿用既有信任邊界。全量 payload 必須符合 ch. 2 的上限；超限不能靜默截斷或假裝清單完整。採集端應回報容量錯誤，保留基礎 host 發布及最後有效客機觀測。實際環境若超限，再設計獨立 inventory topic，第一版不先建分片協定。

畫面與按鍵規劃為：

1. 總覽仍顯示一般主機與 PVE 主機；PVE 標示客機數與 API 資料狀態。
2. A 進入 PVE 主機詳細頁，保留實體 CPU／RAM／溫度，提供 CT／VM 入口。
3. A 開客機清單，方向鍵選取與分頁，列出 type、VMID、名稱、狀態、CPU 及 RAM。
4. A 開客機詳細頁，顯示可取得的資源與趨勢；不支援的資訊不顯示成零。
5. B 逐層返回；L1／R1 在清單所屬 PVE 主機的客機間切換，不能跳到無關主機。

實作只增加必要的客機清單及選取狀態，沿用現有資訊卡與格式化函式。一般主機的固定資訊卡保持原操作。停止的 CT／VM 留在清單並標示 stopped；API 不可用標為 unknown/stale，不能當成 stopped。成功清單移除客機時，查看中的頁面退回該 PVE 清單；主機失聯則沿用總覽退回行為。

## 7. 實作順序、影響檔案與驗收

下列是可依序交付的工作，不代表已開始改程式。先完成辨識及採集模組，再串 MQTT 與顯示；安裝器不得在資料格式尚未確認前宣稱 PVE 功能可用。

| 工作 | 修改位置 | 可檢查產出及驗收 |
| --- | --- | --- |
| 系統辨識與派送 | 採集端新增 `platforms/detect.py`、偵測測試；既有 sender 入口 | Windows、一般 Linux、PVE、PVE 內 Linux VM、容器與不支援 OS 的 fixtures；PVE 特徵不完整時明確報錯 |
| 模組分離 | 採集端 `collectors/`、`clients/pve.py`、`transport/mqtt.py` 及既有 sender | import 無副作用；停用 PVE 不 import PVE adapter；Windows 不 import Linux 工具；既有採集測試通過 |
| PVE 採集 | PVE collector 與 API response fixtures | 有 CT／VM、stopped、空清單、401/403、timeout、缺欄位、重開機與 counter 回退；CPU 換算及 B/s 差分可由固定樣本驗證 |
| 平台安裝 | Linux／PVE 安裝模組、Windows 既有腳本、Compose 配置、私有設定範例 | dry-run 顯示選中的模組與證據；重裝保留配置；PVE 檢查 API 權限及 CA；一般 Linux 不要求 NVIDIA/PVE；容器不誤認宿主 OS |
| 訊息及接收 | 完整 payload builder、新增 `browser/pve.py` 與測試、[monitor.py](../browser/monitor.py) 的 normalize/receive/tick/snapshot/action | 舊 payload 相容、父子不混淆、ID 不因改名而改變、失敗不清空清單、過期不冒充新樣本、超限不截斷 |
| 客機 UI | 新增 `browser/pve.js` 與測試、[monitor.html](../browser/monitor.html)、[test_monitor.py](../browser/test_monitor.py)、[test_monitor_events.py](../browser/test_monitor_events.py)、[test_monitor_ui.cjs](../browser/test_monitor_ui.cjs)、[test_monitor_layout.cjs](../browser/test_monitor_layout.cjs) | 分頁、A/B 導覽、同名客機、清單刪除、父主機斷線、跳脫名稱、防裁切；R36 1024×768 與 TrimUI 1280×720 |
| 顯示模組交付 | [monitor.py](../browser/monitor.py) 靜態資源路由、[install.sh](../browser/install.sh)、[install-trimui.sh](../browser/install-trimui.sh) 及安裝測試 | 兩台掌機皆安裝 Python／JS 模組；`--check` 能發現缺檔；JavaScript 路由使用明確允許清單 |
| 文件及實機 | 採集端安裝文件及設定文件；本倉庫 README、安裝及操作文件 | 一台 PVE、至少一個 CT 與一個 VM，對照 PVE UI 的時間與統計口徑；實按兩台掌機，記錄可見結果 |

採集端新增測試後以 `uv run pytest -q` 驗證。顯示端以 `python3 browser/test_monitor.py`、`python3 browser/test_monitor_events.py`、`node browser/test_monitor_ui.cjs` 及有 Playwright 的 `node browser/test_monitor_layout.cjs` 驗證。安裝腳本另做 shell 語法檢查與 dry-run；實際安裝要在測試目標確認，不以 mock 測試代替。

模組拆分的成本是採集端會同時調整入口、共用 MQTT 與平台安裝流程；必須保留舊入口和設定的相容性。PVE adapter 採直接 HTTPS 可省去新相依套件，但仍須維護錯誤處理、版本相容與官方欄位對應。

## 8. 實作前需要確認的部署資訊

| 未知資訊 | 確認者 | 影響 |
| --- | --- | --- |
| 實際使用的採集端倉庫及版本 | 專案維護者 | 模組拆分及 PR 應交付到哪個專案 |
| PVE 版本、單節點或 cluster、每節點客機量 | PVE 管理者 | API fixtures、可見範圍、訊息容量與測試組合 |
| 現有 sender 是原生服務或 Docker、誰發布 PVE host | 部署維護者 | OS 偵測的位置、服務安裝與避免重複發布 |
| 是否允許 PVE 主機安裝採集器 | PVE 管理者 | 主方案或遠端 collector 替代方案 |
| 是否需要客機檔案系統、程序或 GPU 細節 | 功能負責人 | 是否另外設計 guest 模組及權限 |

本研究未連入實際 PVE、未讀取 token、未安裝程式，也未修改 broker。官方 master 原始碼及公開 API schema 會變動，開發時須以目標 PVE 版本重核欄位；基本資源監控不能被描述為客機內完整硬體監控。
