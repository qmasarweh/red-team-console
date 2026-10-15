@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PORT=7860"
set "OLLAMA_MODEL=qwen2.5-coder:7b"

echo ========================================
echo  Red Team Console
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found. Run setup.bat first.
  pause
  exit /b 1
)

python -c "import flask, requests" >nul 2>&1
if errorlevel 1 (
  echo [WARN] Dependencies missing. Running setup...
  call "%~dp0setup.bat"
  python -c "import flask, requests" >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Setup incomplete.
    pause
    exit /b 1
  )
)

where ollama >nul 2>&1
if errorlevel 1 (
  echo [WARN] Ollama not in PATH. Start Ollama manually if chat fails.
) else (
  echo Checking Ollama service...
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=2)" >nul 2>&1
  if errorlevel 1 (
    echo Starting Ollama...
    start "" ollama serve
    timeout /t 3 /nobreak >nul
  )
)

echo.
echo Opening http://127.0.0.1:%PORT%
echo Press Ctrl+C in this window to stop the server.
echo.

start "" "http://127.0.0.1:%PORT%"
python server.py
if errorlevel 1 (
  echo.
  echo [ERROR] Server exited with an error.
  pause
)
endlocal
