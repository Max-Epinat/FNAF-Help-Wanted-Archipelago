@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0run-client.ps1"
endlocal
