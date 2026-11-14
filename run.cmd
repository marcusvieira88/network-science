@echo off
rem The one command on Windows, without make or bash (contracts/cli.md):
rem   run.cmd          every step, then serve the explorer until Ctrl+C
rem   run.cmd check    every step except serving
rem Both run `uv run --locked enron-case all|check`, exactly what `make` runs on macOS and Linux.
setlocal
where uv >nul 2>nul || (echo ==^> missing prerequisite: uv ^(https://docs.astral.sh/uv/^) 1>&2 & exit /b 1)
set "mode=%~1"
if not defined mode set "mode=all"
cd /d "%~dp0"
uv run --locked enron-case %mode%
exit /b %ERRORLEVEL%
