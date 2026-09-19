@echo off
chcp 65001 >nul
setlocal

REM ============================================================
REM  study-liu 打包脚本（PyInstaller）
REM
REM  用法：
REM      build.bat            打包正式版（无控制台窗口，适合演示分发）
REM      build.bat debug      打包调试版（保留控制台，方便看报错）
REM
REM  产物：
REM      dist\study-liu.exe
REM ============================================================

set APP_NAME=study-liu
set ENTRY=app.py
set DEBUG=0
if /i "%1"=="debug" set DEBUG=1

echo ========================================
echo   study-liu 打包
echo ========================================
python --version
echo.

echo [1/4] 检查并安装依赖...
python -m pip install -r requirements.txt --quiet
if errorlevel 1 goto :failed

echo [2/4] 确认 PyInstaller...
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo     未检测到 PyInstaller，正在安装...
    python -m pip install pyinstaller --quiet
    if errorlevel 1 goto :failed
)

echo [3/4] 清理旧的构建产物...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"

echo [4/4] 打包中，首次约需 1-3 分钟，请耐心等待...
echo.

set WINDOW_FLAG=--windowed
if "%DEBUG%"=="1" set WINDOW_FLAG=--console

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  %WINDOW_FLAG% ^
  --name "%APP_NAME%" ^
  --add-data "data/knowledge.json;data" ^
  --hidden-import cryptography.hazmat.backends.openssl ^
  --hidden-import cryptography.hazmat.primitives.ciphers.aead ^
  --hidden-import cryptography.hazmat.primitives.kdf.pbkdf2 ^
  --hidden-import dotenv ^
  --exclude-module easyocr ^
  --exclude-module pytesseract ^
  --exclude-module torch ^
  --exclude-module torchvision ^
  --exclude-module torchaudio ^
  --exclude-module cv2 ^
  --exclude-module scipy ^
  --exclude-module matplotlib ^
  --exclude-module pandas ^
  --exclude-module pytest ^
  --exclude-module _pytest ^
  %ENTRY%

if errorlevel 1 goto :failed

echo.
echo ========================================
echo   打包完成！
echo.
echo   产物位置：dist\%APP_NAME%.exe
echo   首次运行会在 exe 同目录自动创建 data\ 目录，
echo   用于存放设置、知识库、进度与缓存。
echo ========================================
goto :end

:failed
echo.
echo ************************************************
echo   打包失败！请检查上方错误信息。
echo   提示：执行 build.bat debug 可看到完整日志。
echo ************************************************

:end
pause
endlocal
