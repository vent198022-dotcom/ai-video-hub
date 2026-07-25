# 一次性設定手冊

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
schtasks /Create /SC DAILY /ST 09:00 /TN "AIVideoHub" /TR "C:\Users\user\Desktop\AI用\claue 工作\AI 知識平台\ai-video-hub\run.bat"
```
- 電腦當天沒開機就不會跑；下次執行會用 publishedAfter 自動補齊漏掉的影片
- 查看排程：`schtasks /Query /TN "AIVideoHub"`
- 刪除排程：`schtasks /Delete /TN "AIVideoHub" /F`

## 6. 日常維運
- 執行紀錄：`logs\run.log`（管線日誌）、`logs\scheduler.log`（排程器輸出）
- 修改關鍵字/分類：編輯 `config.yaml`（改分類清單時注意：舊影片不會重新分類）
- YouTube 配額用量：Google Cloud Console → APIs & Services → Quotas
