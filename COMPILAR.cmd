@echo off
setlocal
cd /d "%~dp0"
where cl >nul 2>&1
if errorlevel 1 (
 echo Abra um x64 Native Tools Command Prompt do Visual Studio 2019 ou 2022.
 echo O executavel pronto ja esta incluido. Nao precisa compilar para testar.
 exit /b 1
)
cl /nologo /O2 /EHsc /MD /std:c++17 /utf-8 /D_ITERATOR_DEBUG_LEVEL=0 /D_WIN32_WINNT=0x0602 /W4 src\adapter.cpp /Foadapter.obj /Feyoosee_adapter.exe /link /MACHINE:X64 kernel32.lib bcrypt.lib user32.lib gdi32.lib winmm.lib mfreadwrite.lib mfplat.lib mfuuid.lib ole32.lib
exit /b %errorlevel%
