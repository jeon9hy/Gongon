@echo off
rem Start gongon local server and open the browser. Close this window to stop.
rem Keep this file ASCII-only: cmd misreads UTF-8 Korean text as commands.
rem "python -m uvicorn" avoids the uvicorn.exe trampoline, which fails on non-ASCII paths.
cd /d "%~dp0.."
title gongon server
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8000"
uv run python -m uvicorn app.main:app --reload
pause
