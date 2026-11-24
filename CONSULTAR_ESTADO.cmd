@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
where py >nul 2>&1
if errorlevel 1 goto usepython
py -3 "%~dp0iniciar.py"
goto finish
:usepython
where python >nul 2>&1
if errorlevel 1 goto missing
python "%~dp0iniciar.py"
goto finish
:missing
echo Python nao encontrado. Use o Python 64 bits que executou os testes anteriores.
:finish
echo.
pause
endlocal
