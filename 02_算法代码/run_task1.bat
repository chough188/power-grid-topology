@echo off
setlocal
for %%I in ("%~dp0..") do set "ALGO_ROOT=%%~fI"
for %%I in ("%ALGO_ROOT%\..") do set "PROJECT_ROOT=%%~fI"
set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] 虚拟环境未找到: %PYTHON_EXE%
    echo 请先创建虚拟环境并安装依赖：
    echo   cd ..\..  ^&^& py -3 -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

set "INPUT_DIR=%PROJECT_ROOT%\03_数据集\official"
set "OUTPUT_DIR=%PROJECT_ROOT%\05_分析报告输出"

if not exist "%INPUT_DIR%" (
    echo [WARN] 输入目录不存在，尝试创建: %INPUT_DIR%
    mkdir "%INPUT_DIR%"
)
if not exist "%OUTPUT_DIR%" (
    mkdir "%OUTPUT_DIR%"
)

echo ============================================================
echo  任务一：图模质量校验及修正
echo ============================================================
echo 输入: %INPUT_DIR%
echo 输出: %OUTPUT_DIR%
echo.

pushd "%ALGO_ROOT%"
"%PYTHON_EXE%" -X utf8 run_official_pipeline.py ^
    --input "%INPUT_DIR%" ^
    --output "%OUTPUT_DIR%"
set "EXIT_CODE=%ERRORLEVEL%"
popd

if %EXIT_CODE% neq 0 (
    echo.
    echo [ERROR] 任务一执行失败，错误码: %EXIT_CODE%
    pause
    exit /b %EXIT_CODE%
)

echo.
echo ============================================================
echo  任务一完成！
echo  输出目录: %OUTPUT_DIR%
echo ============================================================
pause
