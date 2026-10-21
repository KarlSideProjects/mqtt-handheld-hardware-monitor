# MQTT Handheld Hardware Monitor

把 Linux 掌機變成桌上的硬體監控螢幕，一台掌機查看多台電腦的 CPU、GPU、記憶體、溫度與趨勢。

**掌機顯示端（本專案）** 接收並顯示資料；**[電腦採集端 hwmonitor-mqtt](https://github.com/KarlSideProjects/hwmonitor-mqtt)** 安裝在 Windows／Linux／PVE，負責採集及傳送。兩邊需連到同一個 MQTT broker，並使用相符的主題設定。

電腦採集端 → MQTT broker → 掌機顯示端

## 安裝入口

| 要安裝在哪裡 | 安裝 script | 說明 |
| --- | --- | --- |
| R36 MAX 2 | [install.sh](browser/install.sh) | dArkOS4Clone／Debian 13 ARM64，已實機驗證 |
| TrimUI Smart Pro S | [install-trimui.sh](browser/install-trimui.sh) | 原廠 Buildroot ARM64，實驗支援，長時間穩定性待驗收 |
| Windows／Linux／PVE 電腦 | [採集端安裝入口](https://github.com/KarlSideProjects/hwmonitor-mqtt#安裝入口) | 先準備會傳送資料的電腦 |

**[掌機安裝步驟與命令](docs/installation.md#快速安裝)** · [給 AI 的安裝 prompt](docs/installation.md#給-ai-的安裝-prompt)

安裝需準備掌機網路與 SSH、MQTT broker；本專案不包含刷機映像。腳本會安裝相依套件並保留既有 MQTT 設定，帳密與備份請保持私有。

![電腦透過 MQTT 將硬體資料傳給掌機](docs/images/monitoring-overview.png)

## 操作與詳細文件

從 R36 的 **Ports → Hardware Monitor**，或 TrimUI 的 **應用 Apps → Hardware Monitor** 開啟。**A** 進入、**B** 返回。

- [選單與按鍵圖解](docs/device-controls.md)：關屏、喚醒及退出。
- [使用指南](docs/user-guide.md)：實機畫面、詳細功能、維護與還原。
- [完整安裝說明](docs/installation.md)：SSH、MQTT、相依套件與驗證限制。
- [CI 手冊](docs/ci-validation.md)：開發驗證。

程式碼採 [GPL v3](LICENSE)。
