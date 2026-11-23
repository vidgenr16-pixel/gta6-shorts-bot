@echo off
title GTA 6 Shorts Bot
cd /d "%~dp0"
if not exist .env (
  echo .env is missing. Copy .env.example to .env and add your bot token.
  pause
  exit /b 1
)
if not exist "C:\gta6bot\.venv\Scripts\python.exe" (
  echo Setting up Python environment in C:\gta6bot ...
  python -m venv C:\gta6bot\.venv
  C:\gta6bot\.venv\Scripts\python -m pip install -r requirements.txt
)
echo Bot is running. Keep this window open. Close it to stop the bot.
C:\gta6bot\.venv\Scripts\python bot.py
pause
