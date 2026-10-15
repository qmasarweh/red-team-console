@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  Red Team Console - Setup
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.10+ and retry.
  echo https://www.python.org/downloads/
  pause
  exit /b 1
)

echo [1/3] Installing Python packages...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install failed.
  pause
  exit /b 1
)

echo.
echo [2/3] Checking Ollama...
where ollama >nul 2>&1
if errorlevel 1 (
  echo [WARN] Ollama not found in PATH.
  echo Install from https://ollama.com then run setup.bat again.
  echo.
  pause
  exit /b 0
)

ollama --version
echo.

echo [3/3] Pulling default coding model qwen2.5-coder:7b ...
echo This may take a while depending on your connection.
ollama pull qwen2.5-coder:7b
if errorlevel 1 (
  echo [WARN] Model pull failed. You can pull manually later:
  echo   ollama pull qwen2.5-coder:7b
)

echo.
echo Optional abliterated 14B model ^(stronger, ~9GB^):
choice /C YN /M "Pull huihui_ai/qwen2.5-coder-abliterate:14b now"
if errorlevel 2 goto done
if errorlevel 1 (
  ollama pull huihui_ai/qwen2.5-coder-abliterate:14b
)

:done
echo.
echo ========================================
echo  Setup complete.
echo  Run start.bat to launch the console.
echo ========================================
pause
endlocal
