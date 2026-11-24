@echo off
setlocal
cd /d "%~dp0"
where pyw >nul 2>&1
if not errorlevel 1 (
 start "" pyw -3 "%~dp0painel.py"
 exit /b
)
where pythonw >nul 2>&1
if not errorlevel 1 (
 start "" pythonw "%~dp0painel.py"
 exit /b
)
where py >nul 2>&1
if not errorlevel 1 (
 py -3 "%~dp0painel.py"
 exit /b
)
python "%~dp0painel.py"
if errorlevel 1 pause
