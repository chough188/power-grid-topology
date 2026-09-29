@echo off
setlocal
for %%I in ("%~dp0..") do set "ALGO_ROOT=%%~fI"
for %%I in ("%ALGO_ROOT%\..") do set "PROJECT_ROOT=%%~fI"
set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] 虚拟环境未找到: %PYTHON_EXE%
    echo 请先创建虚拟环境并安装依赖。
    pause
    exit /b 1
)

set "SVG_INPUT=%PROJECT_ROOT%\03_数据集\svg_input"
set "SVG_OUT=%PROJECT_ROOT%\04_SVG输出"
set "DB_DIR=%PROJECT_ROOT%\03_数据集\official"

if not exist "%SVG_INPUT%" mkdir "%SVG_INPUT%"
if not exist "%SVG_OUT%\5.1_原始美化图" mkdir "%SVG_OUT%\5.1_原始美化图"
if not exist "%SVG_OUT%\5.2_设备增删修正图" mkdir "%SVG_OUT%\5.2_设备增删修正图"
if not exist "%SVG_OUT%\5.3_自动生成图\单线图" mkdir "%SVG_OUT%\5.3_自动生成图\单线图"
if not exist "%SVG_OUT%\5.3_自动生成图\联络关系图" mkdir "%SVG_OUT%\5.3_自动生成图\联络关系图"
if not exist "%SVG_OUT%\5.3_自动生成图\全站联络总图" mkdir "%SVG_OUT%\5.3_自动生成图\全站联络总图"
if not exist "%SVG_OUT%\5.3_自动生成图\电源追溯路径图" mkdir "%SVG_OUT%\5.3_自动生成图\电源追溯路径图"

echo ============================================================
echo  任务二：SVG 拓扑图形美化专项任务
echo ============================================================

REM --- 5.1 SVG 标准化美化 ---
echo.
echo [5.1/3] 正在执行 SVG 标准化美化...
echo   输入: %SVG_INPUT%
echo   输出: %SVG_OUT%\5.1_原始美化图
pushd "%ALGO_ROOT%"
"%PYTHON_EXE%" -X utf8 -m svg_engine.beautify ^
    --input "%SVG_INPUT%" ^
    --output "%SVG_OUT%\5.1_原始美化图"
if %ERRORLEVEL% neq 0 (
    echo [WARN] 5.1 美化步骤未完成...
)
popd

REM --- 5.2 SVG 增删设备 ---
echo.
echo [5.2/3] 正在执行 SVG 交互式增删设备...
echo   输入: %SVG_OUT%\5.1_原始美化图
echo   输出: %SVG_OUT%\5.2_设备增删修正图
pushd "%ALGO_ROOT%"
"%PYTHON_EXE%" -X utf8 -m svg_engine.edit_device ^
    --input "%SVG_OUT%\5.1_原始美化图" ^^
    --output "%SVG_OUT%\5.2_设备增删修正图" ^^
    --mode test1
if %ERRORLEVEL% neq 0 (
    echo [WARN] 5.2 增删设备步骤未完成...
)
popd

REM --- 5.3 自动生成 SVG ---
echo.
echo [5.3/3] 正在执行自动生成 SVG 接线图...
echo   输入: %DB_DIR% (数据库)
echo   输出: %SVG_OUT%\5.3_自动生成图
pushd "%ALGO_ROOT%"
"%PYTHON_EXE%" -X utf8 -m svg_engine.auto_generate ^^
    --db "%DB_DIR%" ^^
    --output "%SVG_OUT%\5.3_自动生成图" ^^
    --type single --feeder FD_example_simple
if %ERRORLEVEL% neq 0 (
    echo [WARN] 5.3 自动生成步骤未完成...
)
popd

:end
echo.
echo ============================================================
echo  任务二完成！输出目录：
echo  %SVG_OUT%
echo ============================================================
pause
