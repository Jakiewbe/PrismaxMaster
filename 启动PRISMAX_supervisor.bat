@echo off
chcp 65001 >nul
cd /d "%~dp0"
title PRISMAX Supervisor

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [PRISMAX] Requesting administrator privileges...
    powershell -NoProfile -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.8+ first.
    pause
    exit /b 1
)

echo [PRISMAX] Starting supervisor...
echo [PRISMAX] Policy: alert only, no browser refresh, no automatic restart.
python "%~dp0supervisor.py"
pause
