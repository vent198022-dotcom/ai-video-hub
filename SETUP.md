# 一次性設定手冊

## 0. 環境準備（新電腦或重灌後才需要）
1. 安裝 Python 3.11 以上：https://www.python.org/downloads/ ，安裝時勾選「Add python.exe to PATH」
2. 安裝 Git：https://git-scm.com/download/win （預設選項即可）
3. 在專案目錄執行：`pip install -r requirements.txt`

## 1. 申請金鑰
- **YouTube Data API v3**：到 Google Cloud Console → 建立專案 → 啟用「YouTube Data API v3」→ 建立 API 金鑰
- **Gemini API**：到 Google AI Studio（aistudio.google.com）→ Get API key

## 2. 設定 .env
複製 `.env.example` 為 `.env`，填入兩把金鑰。`.env` 不會進版控。

## 3. 建立 GitHub repo 並啟用 Pages
```bash
# 在 GitHub 網站建立私人層級以外的 repo（Pages 免費版需 public），例如 ai-video-hub
git remote add origin https://github.com/<帳號>/ai-video-hub.git
git push -u origin main
```
第一次 `git push` 會跳出瀏覽器要求登入 GitHub（Git Credential Manager），登入一次後排程的自動推送會沿用憑證，不會再問。

然後到 repo → Settings → Pages → Source 選 `Deploy from a branch`，
Branch 選 `main`、資料夾選 `/docs`，儲存。
網站網址：`https://<帳號>.github.io/ai-video-hub/`

## 4. 手動試跑一次
```bash
python main.py
```
確認 `logs\run.log` 顯示四個階段完成、GitHub Pages 網站有內容。

## 5. 設定每日排程（PowerShell）
本專案路徑含空格與中文，**必須用 PowerShell 的排程 API 建立**，不要用 `schtasks /Create`
（原因見本節末的「踩過的坑」）：

**務必透過 `run_hidden.vbs` 啟動，不要直接指向 `run.bat`**（原因見本節末第二個坑）：

```powershell
$vbs = "C:\Users\user\Desktop\AI用\claue 工作\AI 知識平台\ai-video-hub\run_hidden.vbs"
Register-ScheduledTask -TaskName "AIVideoHub" -Force `
  -Action (New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$vbs`"") `
  -Trigger (New-ScheduledTaskTrigger -Daily -At 16:00) `
  -Settings (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
      -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 `
      -RestartInterval (New-TimeSpan -Minutes 15) `
      -ExecutionTimeLimit (New-TimeSpan -Hours 2)) `
  -Description "AI 教學影片知識平台每日更新"
```

`-Settings` 那幾項也是必要的，預設值對筆電很不友善（見本節末第三個坑）。

**時間建議設 16:00**：Gemini 免費配額在太平洋時間午夜重置，換算為台灣時間夏令 15:00、
冬令 16:00。設 16:00 可讓兩個季節都落在重置之後，不必隨換季調整。

建立後**必須驗證儲存正確**——只看到「建立成功」不代表能執行：
```powershell
$x = [xml](schtasks /Query /TN "AIVideoHub" /XML)
$x.Task.Actions.Exec.Command      # 必須是 wscript.exe
$x.Task.Actions.Exec.Arguments    # 必須是完整的 run_hidden.vbs 路徑（含引號）
```

再實際觸發一次，確認真的跑得動：
```powershell
Start-ScheduledTask -TaskName "AIVideoHub"
```
等約一分鐘後檢查 `logs\scheduler.log` 與 `logs\run.log` 是否增長。

- 排程預設僅在該使用者登入時執行；電腦關機或未登入的日子不會跑，
  漏掉的影片會在下次執行時由 `publishedAfter` 增量補齊。
- 查看狀態：`Get-ScheduledTaskInfo -TaskName "AIVideoHub"`
  （`LastTaskResult` 為 `0` 代表成功、`267009` 代表正在執行中）
- 刪除排程：`Unregister-ScheduledTask -TaskName "AIVideoHub" -Confirm:$false`

### 踩過的坑：為什麼不用 schtasks /Create
`schtasks /Create /TR "<含空格的路徑>"` 會把路徑在**第一個空格處切開**，前半當成程式、
後半當成引數，於是執行時回報 `-2147024894`（找不到檔案）。實測結果：

| 寫法 | 儲存結果 |
|------|---------|
| `/TR "C:\...\AI用\claue 工作\...\run.bat"` | Command=`C:\...\AI用\claue`、Arguments=`工作\...\run.bat` ❌ |
| `/TR '"C:\...\run.bat"'`（單引號包雙引號） | 同上，PowerShell 5.1 會把內層引號吃掉 ❌ |
| `Register-ScheduledTask -Execute $bat` | Command=完整路徑、Arguments 為空 ✅ |

關鍵是**建立成功不等於能執行**——`schtasks /Create` 兩種寫法都回報 SUCCESS，
只有實際觸發或檢查儲存的 XML 才會發現路徑被切壞。

### 踩過的坑之二：為什麼要透過 run_hidden.vbs
排程若直接指向 `run.bat`，每天會彈出一個主控台視窗並停留十幾二十分鐘。
視窗一旦被關掉（看到擋在螢幕上的黑視窗，任誰都會想關），Python 收到
`CTRL_CLOSE_EVENT` 而中止，工作排程器回報 `3221225786`（`0xC000013A`），
當天的更新就沒完成——而且**不會有任何錯誤提示**。

實測：改用 `run_hidden.vbs`（視窗樣式 0）之前，多數日子在 5 分鐘內被中止；
改用之後完整跑完 21 分鐘、`LastTaskResult=0`。

### 踩過的坑之三：筆電的預設排程設定會讓它幾乎不會跑
`Register-ScheduledTask` 的預設值中有三項對筆電特別不友善，疊加起來等於
「只有在插著電、開著機、且不中途拔電的日子才會更新」：

| 預設設定 | 後果 | 對策參數 |
|---------|------|---------|
| `DisallowStartIfOnBatteries` | 沒插電就不啟動 | `-AllowStartIfOnBatteries` |
| `StopIfGoingOnBatteries` | 執行中拔電就中止 | `-DontStopIfGoingOnBatteries` |
| `StartWhenAvailable=False` | 關機那天永久跳過，不補跑 | `-StartWhenAvailable` |

## 6. 設定更新失敗告警（建議）
系統若連續多天沒成功更新，會主動寄 Email 通知，不必自己盯著網站。

**準備 Gmail 應用程式密碼**（不是登入密碼，可隨時單獨撤銷）：
1. 到 https://myaccount.google.com/security 確認「兩步驟驗證」已開啟
2. 到 https://myaccount.google.com/apppasswords 建立一組，名稱自取
3. 把 Gmail 地址與 16 碼密碼填進 `.env` 的 `ALERT_SMTP_USER` / `ALERT_SMTP_PASS`

**建立看門狗排程**（每天 20:00 檢查一次，只跑幾秒）：
```powershell
$vbs = "C:\Users\user\Desktop\AI用\claue 工作\AI 知識平台\ai-video-hub\run_hidden.vbs"
Register-ScheduledTask -TaskName "AIVideoHubWatchdog" -Force `
  -Action (New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$vbs`" notify.bat") `
  -Trigger (New-ScheduledTaskTrigger -Daily -At 20:00) `
  -Settings (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
      -DontStopIfGoingOnBatteries -StartWhenAvailable `
      -ExecutionTimeLimit (New-TimeSpan -Minutes 10)) `
  -Description "AI 知識平台更新失敗告警"
```

門檻可在 `config.yaml` 的 `watchdog.threshold_hours` 調整，預設 48 小時。

**為什麼要獨立排程**：主管線若執行到一半被中止，寫在管線裡的通知也不會被執行——
壞掉的系統無法通報自己壞掉。看門狗獨立執行且只跑幾秒，才能可靠地抓到各種故障。

**限制**：若電腦整天關機，本機看門狗同樣不會執行，因此無法涵蓋「連續多天完全沒開機」
的情況。要涵蓋那種情境需要外部的雲端監控服務。

## 7. 日常維運
- 執行紀錄：`logs\run.log`（管線日誌）、`logs\scheduler.log`（排程器輸出）
- 修改關鍵字/分類：編輯 `config.yaml`（改分類清單時注意：舊影片不會重新分類）
- YouTube 配額用量：Google Cloud Console → APIs & Services → Quotas

## 8. 手動提交影片、文章或開源專案
在 `submit.txt` 裡貼上連結（一行一個），下次執行 `run.bat` 就會自動收錄、分類、上架。
- 貼 **YouTube 連結** → 收錄為影片（支援 watch?v=、youtu.be、shorts 等格式），且不受兩分鐘時長下限限制
- 貼 **GitHub 專案網址** → 收錄為開源專案，自動帶入星數、授權與安全評分
  （支援結尾 `/`、`.git`、`/tree/main`、`/blob/...` 等形式）
- 貼 **其他網頁連結** → 收錄為文章，系統會自動抓取正文並由 AI 撰寫摘要

重複貼同一個連結不會重複收錄；抓不到正文的網頁會自動略過並記錄在 `logs\run.log`。

**手動指定的開源專案不套用授權檢查**（你指定就代表已自行判斷），但仍會經過 AI 風險審視——
若被判定為爬蟲／破解／要求交出金鑰等類型，不會上架，原因會記錄在 `logs\run.log`。

## 9. 手動下架內容
在 `remove.txt` 裡貼上要下架的連結（一行一個，影片／文章／專案皆可），
下次執行 `run.bat` 就會從網站移除，而且不會被重新收錄。

這份清單代表「目前要下架什麼」：**把某一行刪掉再跑一次，該筆內容就會自動回到網站上**。
下架不會刪除資料，只是把它標記為人工下架，所以隨時可以還原。

網址完全無法辨識時（例如整行亂碼、既非影片也非文章也非專案格式）才會記錄在
`logs\run.log`；若格式正確但資料庫裡查無對應項目（例如網址打錯字、ID 不存在），
則會被靜默略過，不會特別記錄，也不影響其他項目下架。

**注意**：復原是以整份清單為準——清空或刪除整個 `remove.txt`（而不是只刪掉其中
一行），等同一次把所有先前下架的項目全部復原，請小心操作。

## 10. 難易度與國內外標示
每筆內容會由 AI 標上「入門／進階／專家」與「國內／國外」，網站上可依程度、國內外篩選。
新收的內容會自動標記；若要為既有內容補標，執行一次：
`python tag_metadata.py`
（只送標題、分類與現有摘要給 AI——不送影片字幕或文章正文，所以成本很低、也不會覆蓋既有摘要。
一次執行會分批補齊所有難易度或國內外尚未標記的內容，每批 100 筆；若中途中斷，已標記的會保留，下次執行接續剩下的。
補標後請再跑一次 `run.bat` 讓網站更新。）

## 11. 開源專案的安全性說明
收錄的開源專案會經過三層風險訊號檢查：
1. **授權條款**：沒有明確開源授權（例如顯示 NOASSERTION）的專案不予收錄
2. **AI 風險審視**：AI 閱讀 README，若判定為爬蟲／破解／要求交出金鑰等類型則不上架
3. **OpenSSF 安全評分**：有評分的專案會顯示在卡片上（0~10 分，越高越好）；查無評分代表該專案不在
   OpenSSF 資料集內，屬於「未知」而非「不安全」

**重要限制**：以上都是風險訊號檢查，**不等於原始碼安全稽核**。系統無法判斷專案內是否含有後門或惡意程式碼。
實際導入任何開源專案前，請自行評估並遵循公司的資安規範。
