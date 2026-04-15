@echo off
setlocal

REM One-click wrapper that launches the PowerShell starter script.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_dev.ps1" %*
