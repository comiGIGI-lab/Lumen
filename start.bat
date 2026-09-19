@echo off
setlocal
chcp 65001 >nul
title study-liu Web - One Click Launcher
cd /d "%~dp0"

echo ==================================================
echo   study-liu Web  -  One Click Launcher
echo ==================================================
echo.

set "NODE="

rem ---- 1) explicit override: set NODE_EXE if needed
if defined NODE_EXE if exist "%NODE_EXE%" set "NODE=%NODE_EXE%"

rem ---- 2) look up PATH
if not defined NODE for /f "delims=" %%i in ('where node 2^>nul') do (
  if not defined NODE set "NODE=%%i"
)

rem ---- 3) common install locations
if not defined NODE for %%P in (
  "%LOCALAPPDATA%\Programs\nodejs\node.exe"
  "%LOCALAPPDATA%\Programs\node\node.exe"
  "%ProgramFiles%\nodejs\node.exe"
  "%ProgramFiles(x86)%\nodejs\node.exe"
) do (
  if not defined NODE if exist "%%~P" set "NODE=%%~P"
)

rem ---- 4) WorkBuddy managed runtimes
if not defined NODE for /d %%D in ("%USERPROFILE%\.workbuddy\binaries\node\versions\*") do (
  if not defined NODE if exist "%%~fD\node.exe" set "NODE=%%~fD\node.exe"
)

rem ---- 5) nvm-windows
if not defined NODE for /d %%D in ("%APPDATA%\nvm\v*") do (
  if not defined NODE if exist "%%~fD\node.exe" set "NODE=%%~fD\node.exe"
)

if not defined NODE (
  echo [x] Node.js was not found on this machine.
  echo     Please install Node 18+ from https://nodejs.org
  echo     Or set NODE_EXE to the full path of node.exe
  echo.
  pause
  exit /b 1
)

echo [*] node.exe : %NODE%
echo [*] Starting backend + frontend ...
echo [*] The browser will open automatically when ready.
echo [*] Press Ctrl+C in this window to stop.
echo.

"%NODE%" "scripts\dev.mjs"
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo [*] Services stopped. You can close this window.
) else (
  echo [x] Launcher exited with code %RC%.
)
echo.
pause
endlocal
