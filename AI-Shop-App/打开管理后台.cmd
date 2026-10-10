@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
  python launch.py --admin
) else (
  where py >nul 2>nul
  if errorlevel 1 (
    echo 请先安装 Python 3.10 或更新版本，并添加到 PATH。
    pause
    exit /b 1
  )
  py -3 launch.py --admin
)
