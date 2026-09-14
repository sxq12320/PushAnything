@echo off
:: 打包绿色 exe + 安装程序（需已安装 Inno Setup 6）
setlocal
cd /d %~dp0
call build.bat || exit /b 1
set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" (echo [x] 未找到 Inno Setup，请先安装 & exit /b 1)
"%ISCC%" installer\installer.iss || exit /b 1
echo.
echo [OK] dist\PushAnything.exe  +  installer\PushAnything_Setup_*.exe
