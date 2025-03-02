@echo off
chcp 65001 > nul
title XUnity大模型翻译v3 - 打包程序

echo ==================================================================
echo                    XUnity大模型翻译v3 - 打包程序
echo ==================================================================
echo.
echo 此脚本将帮助您将程序打包为可执行文件(.exe)
echo.

:: 检查Python是否安装
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到Python! 请先安装Python 3.8或更高版本。
    echo 您可以从 https://www.python.org/downloads/ 下载Python
    pause
    exit /b 1
)

echo [√] 已找到Python
echo.

:: 检查必要的文件
if not exist XUnity-LLMTranslateGUI.py (
    echo [错误] 未找到主程序文件 XUnity-LLMTranslateGUI.py
    echo 请确保您在正确的目录中运行此脚本
    pause
    exit /b 1
)

echo [√] 已找到主程序文件
echo.

echo === 安装必要的依赖 ===
echo.
pip install -r requirements.txt || (
    echo [错误] 安装依赖失败!
    pause
    exit /b 1
)

echo.
echo === 开始打包程序 ===
echo.
python build_exe.py
if %errorlevel% neq 0 (
    echo [错误] 打包程序失败!
    pause
    exit /b 1
)

echo.
echo 如果打包成功，可执行文件将位于 dist 目录中
echo.
pause 