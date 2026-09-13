@echo off
chcp 65001 >nul
cd /d %~dp0
venv\Scripts\python.exe -m PyInstaller --noconfirm "一键投稿.spec"
echo.
echo 产物: dist\一键投稿.exe
pause
