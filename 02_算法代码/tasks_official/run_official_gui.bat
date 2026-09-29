@echo off
setlocal
for %%I in ("%~dp0..") do set "ALGO_ROOT=%%~fI"
for %%I in ("%ALGO_ROOT%\..") do set "PROJECT_ROOT=%%~fI"
set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\pythonw.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=pyw"

pushd "%ALGO_ROOT%"
"%PYTHON_EXE%" -X utf8 -m tasks_official.gui
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
