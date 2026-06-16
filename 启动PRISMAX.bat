@echo off
chcp 65001 >nul
title PRISMAX 一键启动器

:: ========================================
:: 检查管理员权限
:: ========================================
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [提示] 正在请求管理员权限...
    powershell -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

:: ========================================
:: 设置工作目录（关键！）
:: ========================================
cd /d "%~dp0"
echo [路径] 工作目录: %CD%

:: 设置环境变量，确保子进程也使用正确路径
set "PRISMAX_DIR=%~dp0"
echo.
echo ╔════════════════════════════════════════════════════════╗
echo ║           PRISMAX 跨端联动系统 一键启动器              ║
echo ╠════════════════════════════════════════════════════════╣
echo ║  [1] Bridge 中转站                                     ║
echo ║  [2] Python 主控脚本                                   ║
echo ╚════════════════════════════════════════════════════════╝
echo.

:: ========================================
:: 检查 Python
:: ========================================
echo [检查] 正在检测 Python 环境...
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo [成功] Python 版本: %PYVER%
echo.

:: ========================================
:: 检查必要文件
:: ========================================
echo [检查] 正在检测必要文件...
if not exist "Bridge_v2.py" (
    echo [错误] 未找到 Bridge_v2.py
    pause
    exit /b 1
)
if not exist "prismax_bot_v2.5_crossplatform.py" (
    echo [错误] 未找到 prismax_bot_v2.5_crossplatform.py
    pause
    exit /b 1
)
echo [成功] 所有必要文件已就绪
echo.

:: ========================================
:: 检查依赖库
:: ========================================
echo [检查] 正在检测 Python 依赖库...
python -c "import requests" >nul 2>&1
if %errorLevel% neq 0 (
    echo [安装] 正在安装 requests...
    pip install requests -q
)
python -c "import pydirectinput" >nul 2>&1
if %errorLevel% neq 0 (
    echo [安装] 正在安装 pydirectinput...
    pip install pydirectinput -q
)
python -c "import pyautogui" >nul 2>&1
if %errorLevel% neq 0 (
    echo [安装] 正在安装 pyautogui...
    pip install pyautogui -q
)
python -c "import keyboard" >nul 2>&1
if %errorLevel% neq 0 (
    echo [安装] 正在安装 keyboard...
    pip install keyboard -q
)
echo [成功] 依赖库检查完成
echo.

:: ========================================
:: 创建日志目录
:: ========================================
if not exist "logs" mkdir logs

:: ========================================
:: 启动 Bridge（新窗口）
:: ========================================
echo [启动] 正在启动 Bridge 中转站...
start "PRISMAX Bridge" cmd /k "cd /d ""%~dp0"" && title PRISMAX Bridge && python Bridge_v2.py"

:: ========================================
:: 等待并验证 Bridge 启动
:: ========================================
echo [等待] Bridge 初始化中...
set BRIDGE_OK=0
set RETRY=0

:CHECK_BRIDGE
timeout /t 1 /nobreak >nul
set /a RETRY+=1

:: 使用 Python 检查 Bridge 健康状态
python -c "import requests; r=requests.get('http://127.0.0.1:5000/health',timeout=2); exit(0 if r.status_code==200 else 1)" >nul 2>&1
if %errorLevel% equ 0 (
    set BRIDGE_OK=1
    echo [成功] Bridge 启动成功！(用时 %RETRY% 秒)
    goto BRIDGE_READY
)

echo [等待] 检测 Bridge... %RETRY%/15
if %RETRY% lss 15 goto CHECK_BRIDGE

if %BRIDGE_OK% equ 0 (
    echo [错误] Bridge 启动超时，请检查 Bridge 窗口是否有错误
    echo [提示] 按任意键继续尝试启动主脚本，或关闭窗口取消
    pause
)

:BRIDGE_READY
echo.

:: ========================================
:: 启动主控脚本（当前窗口）
:: ========================================
echo [启动] 正在启动主控脚本...
echo [路径] 当前目录: %CD%
echo.
echo ════════════════════════════════════════════════════════
echo   系统已启动！
echo   - Bridge 运行在独立窗口
echo   - 主控脚本运行在当前窗口
echo   - 按 F9 启动/暂停操作
echo   - 按 ESC 紧急停止
echo ════════════════════════════════════════════════════════
echo.

:: 确保在正确目录下运行
cd /d "%PRISMAX_DIR%"
python "%PRISMAX_DIR%prismax_bot_v2.5_crossplatform.py"

:: ========================================
:: 退出时清理
:: ========================================
echo.
echo [提示] 主控脚本已退出
echo [提示] 请手动关闭 Bridge 窗口
pause

