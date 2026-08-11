@echo off
rem AI 教學影片知識平台 - 更新失敗看門狗
cd /d %~dp0
if not exist logs mkdir logs
python notify.py >> logs\watchdog.log 2>&1
