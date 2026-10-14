@echo off
rem Double-click installer: runs install-mod.ps1 (next to this file) without opening a terminal by hand.
rem If the game is not found by itself it asks for its folder and tries again.
setlocal
title FNAF Help Wanted x Archipelago - installer

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-mod.ps1" %*
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="2" goto done

echo.
echo The game was not found automatically.
echo Type or paste the folder that contains "freddys", then press Enter.
echo Example: D:\SteamLibrary\steamapps\common\FNAFVRHelpWanted
set "ROOT="
set /p "ROOT=Game folder: "
if not defined ROOT goto done
set "ROOT=%ROOT:"=%"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
if not defined ROOT goto done

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-mod.ps1" -GameRoot "%ROOT%" %*
set "CODE=%ERRORLEVEL%"

:done
echo.
pause
exit /b %CODE%
