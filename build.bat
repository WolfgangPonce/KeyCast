@echo off
setlocal

echo ============================================================
echo  KeyCast builder
echo ============================================================
echo.

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.9+ and add it to PATH.
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

echo.
echo [2/3] Building KeyCast.exe ...
pyinstaller ^
    --onefile ^
    --windowed ^
    --name KeyCast ^
    --hidden-import=pynput.keyboard._win32 ^
    --hidden-import=pynput.mouse._win32 ^
    --hidden-import=PyQt6.sip ^
    main.py

if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo [3/3] Done!
if exist "dist\KeyCast.exe" (
    echo  KeyCast.exe is ready in the dist\ folder.
    echo  You can move it anywhere — it is fully self-contained.
) else (
    echo  WARNING: dist\KeyCast.exe not found. Check output above.
)

echo.
pause
