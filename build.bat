@echo off
chcp 65001 >nul
cd /d %~dp0
venv\Scripts\python.exe -m PyInstaller --noconfirm "PushAnything.spec"
echo.
echo 产物: dist\PushAnything.exe
pause
