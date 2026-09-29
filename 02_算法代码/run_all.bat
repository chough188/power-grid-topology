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

echo ============================================================
echo  一键运行全部比赛任务（任务一 + 任务二）
echo ============================================================
echo.

:: --- 任务一 ---
echo [阶段 1/2] 执行任务一：图模质量校验...
call "%ALGO_ROOT%\run_task1.bat"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] 任务一失败，停止后续执行
    pause
    exit /b %ERRORLEVEL%
)

:: --- 任务二 ---
echo.
echo [阶段 2/2] 执行任务二：SVG 拓扑图形处理...
call "%ALGO_ROOT%\run_task2.bat"
if %ERRORLEVEL% neq 0 (
    echo [WARN] 任务二部分步骤失败，但任务一已完成
)

echo.
echo ============================================================
echo  全部任务执行完毕！
echo ============================================================
echo.
echo 成果目录：
echo   分析报告: %PROJECT_ROOT%\05_分析报告输出\
echo   SVG 图形: %PROJECT_ROOT%\04_SVG输出\
echo.
pause
