@echo off
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

if not exist "data\golf\enrichment_review\logs" mkdir "data\golf\enrichment_review\logs"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set STAMP=%%i

venv\Scripts\python.exe scripts\golf_quarterly_refresh.py %* >> "data\golf\enrichment_review\logs\quarterly_%STAMP%.log" 2>&1
