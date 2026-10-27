@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "APPDIR=%~dp0"
set "WATCHDOG=%~dp0server_watchdog.pyw"
set "URL=http://127.0.0.1:8501"

echo ==============================================
echo    Library Management System - Launcher
echo ==============================================
echo.

rem --- Step 1: find a real Python, skipping the WindowsApps store stub --
set "PYTHON="
for /f "delims=" %%I in ('where python 2^>nul ^| findstr /i /v /c:"WindowsApps"') do if not defined PYTHON set "PYTHON=%%I"
if not defined PYTHON goto :no_python

set "PYTHONW="
for %%I in ("%PYTHON%") do set "PYTHONW=%%~dpIpythonw.exe"
if not exist "%PYTHONW%" goto :no_python

rem --- Step 2: install the dependencies if they are missing ------------
"%PYTHON%" -c "import streamlit, pandas" 2>nul
if errorlevel 1 (
    echo Dependencies are missing - installing them now, this can take a minute...
    "%PYTHON%" -m pip install -r "%APPDIR%requirements.txt"
    echo.
    "%PYTHON%" -c "import streamlit, pandas" 2>nul
    if errorlevel 1 goto :deps_failed
)

rem --- Step 3: if the server is already healthy, just open the app -----
call :is_healthy
if not errorlevel 1 goto :already_running

rem --- Step 4: reclaim port 8501 if something else is squatting on it --
call :port_busy
if errorlevel 1 goto :port_free
call :is_healthy
if not errorlevel 1 goto :already_running
echo Port 8501 is used by another process - stopping that process...
powershell -NoProfile -Command "Get-NetTCPConnection -State Listen -LocalPort 8501 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Write-Output ('Stopping process ' + $_ + ' that was using port 8501'); Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
set /a WAITFREE=0
:wait_free
call :port_busy
if errorlevel 1 goto :port_free
set /a WAITFREE+=1
if %WAITFREE% geq 15 goto :port_stuck
timeout /t 1 >nul
goto :wait_free

:port_free
if not exist "%WATCHDOG%" goto :no_watchdog
call :watchdog_running
if not errorlevel 1 goto :wait_ready
echo Starting the background server...
start "" "%PYTHONW%" "%WATCHDOG%"

rem --- Step 5: wait until the health check says the app is ready --------
:wait_ready
set /a TRIES=0
:health_loop
call :is_healthy
if not errorlevel 1 goto :ready
set /a TRIES+=1
if %TRIES% geq 60 goto :failed
timeout /t 1 >nul
goto :health_loop

:ready
echo The server is ready: %URL%
echo.
start "" %URL%
echo The app has been opened in your browser.
echo.
echo The server now runs in the background - it restarts itself if it
echo ever stops, and it can start automatically with Windows if you run
echo "Enable Auto Start.bat" once. You can close this window.
echo To stop the server, run "Disable Auto Start.bat".
echo.
pause
exit /b 0

:already_running
echo The server is already running - opening it in your browser.
start "" %URL%
echo.
echo You can close this window.
echo.
pause
exit /b 0

rem --------------------------------------------------------------------- #
rem error paths                                                           #
rem --------------------------------------------------------------------- #
:no_python
echo ERROR: Python was not found on your PATH.
echo Install it from https://www.python.org/downloads/ and make sure to
echo tick "Add python.exe to PATH" during setup, then run this again.
echo.
pause
exit /b 1

:deps_failed
echo.
echo ERROR: the dependencies could not be installed automatically.
echo Check the pip output above, then run this again - or install them
echo by hand with:
echo     "%PYTHON%" -m pip install -r "%APPDIR%requirements.txt"
echo.
pause
exit /b 1

:no_watchdog
echo.
echo ERROR: server_watchdog.pyw is missing from this folder:
echo     %APPDIR%
echo Restore that file and run this launcher again.
echo.
pause
exit /b 1

:port_stuck
echo.
echo ERROR: port 8501 could not be freed within 15 seconds.
echo Another program may be holding it. Close that program, then run
echo this launcher again.
echo.
pause
exit /b 1

:failed
echo.
echo ERROR: the server did not become ready within about 60 seconds.
echo.
echo Recent log entries:
powershell -NoProfile -Command "if (Test-Path '.\server.log') { Get-Content '.\server.log' -Tail 15 } else { Write-Output 'server.log has not been created yet.' }"
echo.
echo Read the messages above. The usual causes are:
echo   - another program is holding port 8501 - see server.log
echo   - Python reported an error while starting Streamlit
echo Close any other copy of this app, then run this launcher again.
echo.
pause
exit /b 1

rem --------------------------------------------------------------------- #
rem subroutines                                                           #
rem --------------------------------------------------------------------- #
:is_healthy
"%PYTHON%" -c "import urllib.request as u,sys; sys.exit(0 if u.urlopen('http://127.0.0.1:8501/_stcore/health',timeout=2).read().strip()==b'ok' else 1)" 2>nul
exit /b %errorlevel%

:port_busy
"%PYTHON%" -c "import socket,sys; s=socket.socket(); s.settimeout(1); r=s.connect_ex(('127.0.0.1',8501)); s.close(); sys.exit(0 if r==0 else 1)" 2>nul
exit /b %errorlevel%

:watchdog_running
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*server_watchdog.pyw*' }) { exit 0 } else { exit 1 }" >nul 2>&1
exit /b %errorlevel%
