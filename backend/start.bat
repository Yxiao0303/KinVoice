@echo off
chcp 65001 >nul
title KinVoice 后端

cd /d "%~dp0"

echo ================================================
echo   KinVoice 后端一键启动
echo ================================================
echo.

python start.py

pause
