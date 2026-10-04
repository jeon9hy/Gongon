@echo off
rem Make sure the local PostgreSQL Windows service is running before the app starts.
rem Keep this file ASCII-only: cmd misreads UTF-8 Korean text as commands.
rem Skips quietly when no local PostgreSQL service exists (e.g. a remote DB such as Supabase).
setlocal
rem Use full paths: another find/timeout (e.g. from Git) on PATH would break the checks.
rem No quotes inside for /f below: cmd strips a leading quote there (SystemRoot has no spaces).
set "SYS=%SystemRoot%\System32"

set "PG_SERVICE="
for /f "tokens=2" %%s in ('%SYS%\sc.exe query state^= all ^| %SYS%\findstr.exe /r /c:"SERVICE_NAME: postgresql"') do if not defined PG_SERVICE set "PG_SERVICE=%%s"
if not defined PG_SERVICE (
  echo [gongon] No local PostgreSQL service found. Using DATABASE_URL as is.
  exit /b 0
)

"%SYS%\sc.exe" query "%PG_SERVICE%" | "%SYS%\find.exe" "RUNNING" >nul
if not errorlevel 1 (
  echo [gongon] PostgreSQL is running: %PG_SERVICE%
  exit /b 0
)

echo [gongon] Starting PostgreSQL: %PG_SERVICE%
"%SYS%\net.exe" start "%PG_SERVICE%" >nul 2>&1
if not errorlevel 1 goto wait

rem Starting a service needs administrator rights. Ask once through the UAC prompt.
echo [gongon] Administrator permission is needed to start PostgreSQL. Please approve the prompt.
"%SYS%\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -Command "Start-Process -FilePath sc.exe -ArgumentList 'start','%PG_SERVICE%' -Verb RunAs -WindowStyle Hidden -Wait" >nul 2>&1

:wait
set /a TRIES=0
:wait_loop
"%SYS%\sc.exe" query "%PG_SERVICE%" | "%SYS%\find.exe" "RUNNING" >nul
if not errorlevel 1 (
  echo [gongon] PostgreSQL is running: %PG_SERVICE%
  exit /b 0
)
set /a TRIES+=1
if %TRIES% geq 20 (
  echo [gongon] PostgreSQL did not start: %PG_SERVICE%
  exit /b 1
)
"%SYS%\timeout.exe" /t 1 /nobreak >nul
goto wait_loop
