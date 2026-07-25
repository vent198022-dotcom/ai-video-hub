@echo off
rem AI 教學影片知識平台 - 每日排程入口
cd /d %~dp0
if not exist logs mkdir logs
python main.py >> logs\scheduler.log 2>&1
