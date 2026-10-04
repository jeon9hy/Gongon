@echo off
rem Start gongon local server and open the browser. Close this window to stop.
rem Keep this file ASCII-only: cmd misreads UTF-8 Korean text as commands.
rem "python -m" avoids the uvicorn/alembic .exe trampoline, which fails on non-ASCII paths.
cd /d "%~dp0.."
title gongon server
rem Apply DB migrations first (needs DATABASE_URL in .env, see docs/setup.md).
uv run python -m alembic upgrade head
if errorlevel 1 (
  echo.
  echo [gongon] DB migration failed. Check that PostgreSQL is running and DATABASE_URL in .env.
  pause
  exit /b 1
)
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8000"
uv run python -m uvicorn app.main:app --reload
pause
