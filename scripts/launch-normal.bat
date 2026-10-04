@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0launch-game.ps1" -Normal %*
endlocal
