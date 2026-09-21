@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Tai video - chay tren may tinh

for /f "delims=" %%i in ('py -c "import secrets;print(secrets.token_hex(16))"') do set SECRET_KEY=%%i
for /f "delims=" %%i in ('py -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect((chr(56)+chr(46)+chr(56)+chr(46)+chr(56)+chr(46)+chr(56),80));print(s.getsockname()[0]);s.close()"') do set LANIP=%%i
set PORT=5000

echo.
set /p APP_PASSWORD=Dat mat khau cho lan chay nay: 
echo.
echo ==================================================
echo    May tinh nay:  http://localhost:%PORT%
echo    Tu iPhone:     http://%LANIP%:%PORT%
echo ==================================================
echo    iPhone phai dung chung WiFi voi may tinh nay.
echo    Dong cua so nay la tat server.
echo.

py app.py
if errorlevel 1 pause
