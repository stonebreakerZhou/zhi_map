@echo off
REM ==============================================
REM MindFlow 打包脚本（Windows）
REM
REM 用法：
REM   1. 激活 conda 环境：conda activate zhi_map_env
REM   2. 在项目根目录双击本文件
REM
REM 产物：
REM   dist\MindFlow\MindFlow.exe
REM   dist\MindFlow\（依赖资源）
REM ==============================================

echo ============================================
echo   MindFlow 打包脚本 v1.0
echo ============================================
echo.

REM 检查 conda 环境
where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [错误] 找不到 pyinstaller，请先激活 conda 环境：
    echo        conda activate zhi_map_env
    pause
    exit /b 1
)

echo [1/4] 清理旧的打包产物...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/4] 准备 assets 目录...
if not exist assets mkdir assets
REM TODO: 把 icon.ico 放到 assets/ 下

echo [3/4] 执行 PyInstaller 打包...
pyinstaller ^
    --onedir ^
    --windowed ^
    --noconfirm ^
    --name MindFlow ^
    --add-data "assets;assets" ^
    --collect-all=PySide6 ^
    --hidden-import=PySide6.QtSvg ^
    --hidden-import=PySide6.QtPrintSupport ^
    src/app.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败！
    pause
    exit /b 1
)

echo.
echo [4/4] 打包完成！
echo.
echo 产物位置：dist\MindFlow\
echo 启动方式：双击 dist\MindFlow\MindFlow.exe
echo.
echo 测试一下：
start "" "dist\MindFlow\MindFlow.exe"

pause
