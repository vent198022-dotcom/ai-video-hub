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

## 5. 設定每日排程（系統管理員 PowerShell）
```powershell
schtasks /Create /SC DAILY /ST 09:00 /TN "AIVideoHub" /TR '"C:\Users\user\Desktop\AI用\claue 工作\AI 知識平台\ai-video-hub\run.bat"'
```
建立後立即驗證排程可正常執行：
```powershell
schtasks /Run /TN "AIVideoHub"
```
然後檢查 `logs\scheduler.log` 是否多出新的執行紀錄，代表排程可正常執行。

- 排程預設僅在該使用者登入時執行；電腦關機或未登入的日子不會跑，下次執行會自動補齊遺漏的影片。
- 查看排程：`schtasks /Query /TN "AIVideoHub"`
- 刪除排程：`schtasks /Delete /TN "AIVideoHub" /F`

## 6. 日常維運
- 執行紀錄：`logs\run.log`（管線日誌）、`logs\scheduler.log`（排程器輸出）
- 修改關鍵字/分類：編輯 `config.yaml`（改分類清單時注意：舊影片不會重新分類）
- YouTube 配額用量：Google Cloud Console → APIs & Services → Quotas

## 7. 手動提交影片或文章
在 `submit.txt` 裡貼上連結（一行一個），下次執行 `run.bat` 就會自動收錄、分類、上架。
- 貼 **YouTube 連結** → 收錄為影片（支援 watch?v=、youtu.be、shorts 等格式），且不受兩分鐘時長下限限制
- 貼 **一般網頁連結** → 收錄為文章，系統會自動抓取正文並由 AI 撰寫摘要
重複貼同一個連結不會重複收錄；抓不到正文的網頁會自動略過並記錄在 `logs\run.log`。

## 8. 難易度與國內外標示
每筆內容會由 AI 標上「入門／進階／專家」與「國內／國外」，網站上可依程度、國內外篩選。
新收的內容會自動標記；若要為既有內容補標，執行一次：
`python tag_metadata.py`
（只送標題、分類與現有摘要給 AI——不送影片字幕或文章正文，所以成本很低、也不會覆蓋既有摘要。
一次執行會分批補齊所有難易度或國內外尚未標記的內容，每批 100 筆；若中途中斷，已標記的會保留，下次執行接續剩下的。
補標後請再跑一次 `run.bat` 讓網站更新。）

## 9. 開源專案的安全性說明
收錄的開源專案會經過三層風險訊號檢查：
1. **授權條款**：沒有明確開源授權（例如顯示 NOASSERTION）的專案不予收錄
2. **AI 風險審視**：AI 閱讀 README，若判定為爬蟲／破解／要求交出金鑰等類型則不上架
3. **OpenSSF 安全評分**：有評分的專案會顯示在卡片上（0~10 分，越高越好）；查無評分代表該專案不在
   OpenSSF 資料集內，屬於「未知」而非「不安全」

**重要限制**：以上都是風險訊號檢查，**不等於原始碼安全稽核**。系統無法判斷專案內是否含有後門或惡意程式碼。
實際導入任何開源專案前，請自行評估並遵循公司的資安規範。
