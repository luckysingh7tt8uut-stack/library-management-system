@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "APPDIR=%~dp0"
set "WATCHDOG=%~dp0server_watchdog.pyw"
set "URL=http://127.0.0.1:8501"

echo ==============================================
echo    Library Manager - Enable Auto Start
echo ==============================================
echo.
echo This switches ON automatic startup: the server will launch by
echo itself every time you log into Windows, so the link
echo %URL% always works.
echo.

rem --- find a real Python, skipping the WindowsApps store stub ---------
set "PYTHON="
for /f "delims=" %%I in ('where python 2^>nul ^| findstr /i /v /c:"WindowsApps"') do if not defined PYTHON set "PYTHON=%%I"
if not defined PYTHON goto :no_python

set "PYTHONW="
for %%I in ("%PYTHON%") do set "PYTHONW=%%~dpIpythonw.exe"
if not exist "%PYTHONW%" goto :no_python

if not exist "%WATCHDOG%" goto :no_watchdog

rem --- create the shortcut in the Windows Startup folder ---------------
echo Creating the auto-start shortcut...
powershell -NoProfile -Command "$sh=New-Object -ComObject WScript.Shell; $lnk=$sh.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Startup')) 'Library Manager Server.lnk')); $lnk.TargetPath=$env:PYTHONW; $lnk.Arguments=([char]34+$env:WATCHDOG+[char]34); $lnk.WorkingDirectory=$env:APPDIR; $lnk.WindowStyle=7; $lnk.Description='Starts the Library Management System at http://127.0.0.1:8501 when you log in'; $lnk.Save()"
if errorlevel 1 goto :shortcut_failed
echo Auto start is now ON.
echo.

rem --- make sure the server is running right now -----------------------
call :is_healthy
if not errorlevel 1 goto :wait_ready
call :watchdog_running
if not errorlevel 1 goto :wait_ready
echo Starting the background server now...
start "" "%PYTHONW%" "%WATCHDOG%"

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
echo The app has been opened in your browser - and it will now start
echo automatically with Windows from now on.
echo.
echo You can close this window. To switch auto start off again, run
echo "Disable Auto Start.bat".
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

:no_watchdog
echo ERROR: server_watchdog.pyw is missing from this folder:
echo     %APPDIR%
echo Restore that file and run this again.
echo.
pause
exit /b 1

:shortcut_failed
echo.
echo ERROR: the auto-start shortcut could not be created.
echo Check the message above, then run this again.
echo.
pause
exit /b 1

:failed
echo.
echo ERROR: the server did not become ready within about 60 seconds.
echo Auto start is switched ON, but the server is not up yet.
echo.
echo Recent log entries:
powershell -NoProfile -Command "if (Test-Path '.\server.log') { Get-Content '.\server.log' -Tail 15 } else { Write-Output 'server.log has not been created yet.' }"
echo.
echo Read the messages above, fix the cause, then run this again.
echo.
pause
exit /b 1

rem --------------------------------------------------------------------- #
rem subroutines                                                           #
rem --------------------------------------------------------------------- #
:is_healthy
"%PYTHON%" -c "import urllib.request as u,sys; sys.exit(0 if u.urlopen('http://127.0.0.1:8501/_stcore/health',timeout=2).read().strip()==b'ok' else 1)" 2>nul
exit /b %errorlevel%

:watchdog_running
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*server_watchdog.pyw*' }) { exit 0 } else { exit 1 }" >nul 2>&1
exit /b %errorlevel%
