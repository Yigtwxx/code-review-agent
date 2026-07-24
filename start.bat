@echo off
rem Boots the local dev stack on Windows: MongoDB (only if nothing already
rem answers on the port), the FastAPI backend on 8001 and the Next.js frontend
rem on 3000. Each server opens in its own window; close a window to stop it.
rem
rem Usage:  start.bat
rem Ports can be overridden:  set BACKEND_PORT=8002 && start.bat
setlocal enabledelayedexpansion

set "ROOT_DIR=%~dp0"
if not defined BACKEND_PORT set "BACKEND_PORT=8001"
if not defined FRONTEND_PORT set "FRONTEND_PORT=3000"
if not defined MONGO_PORT set "MONGO_PORT=27017"
if not defined OLLAMA_PORT set "OLLAMA_PORT=11434"

rem --- prerequisites ---------------------------------------------------------
where uv >nul 2>&1
if errorlevel 1 (
  echo [x] uv not found on PATH - install it with: powershell -c "irm https://astral.sh/uv/install.ps1 ^| iex"
  exit /b 1
)
where npm >nul 2>&1
if errorlevel 1 (
  echo [x] npm not found on PATH - install Node.js 20+ from https://nodejs.org
  exit /b 1
)

call :free_port %BACKEND_PORT% backend
if errorlevel 1 exit /b 1
call :free_port %FRONTEND_PORT% frontend
if errorlevel 1 exit /b 1

rem --- dependencies ----------------------------------------------------------
echo ==^> syncing backend dependencies ^(uv^)
uv sync --project "%ROOT_DIR%backend"
if errorlevel 1 exit /b 1

if not exist "%ROOT_DIR%frontend\node_modules" (
  echo ==^> installing frontend dependencies ^(npm^)
  pushd "%ROOT_DIR%frontend"
  call npm install
  popd
  if errorlevel 1 exit /b 1
)

rem --- env files -------------------------------------------------------------
echo ==^> checking env files
uv run --project "%ROOT_DIR%backend" python "%ROOT_DIR%tools\init_env.py"
if errorlevel 1 exit /b 1

rem --- infrastructure --------------------------------------------------------
set "MONGO_URL="
for /f "usebackq tokens=1,* delims==" %%a in ("%ROOT_DIR%.env") do (
  if /i "%%a"=="MONGO_URL" set "MONGO_URL=%%b"
)
set "MONGO_IS_LOCAL="
echo !MONGO_URL! | findstr /i /c:"localhost" /c:"127.0.0.1" >nul && set "MONGO_IS_LOCAL=1"

if defined MONGO_IS_LOCAL (
  call :port_open %MONGO_PORT%
  if "!PORT_OPEN!"=="1" (
    echo ==^> mongodb already listening on %MONGO_PORT% - leaving it alone
  ) else (
    where docker >nul 2>&1
    if errorlevel 1 (
      echo [!] nothing is listening on %MONGO_PORT% and docker is unavailable - the backend will fail to connect
    ) else (
      echo ==^> starting mongodb ^(docker compose^)
      pushd "%ROOT_DIR%"
      docker compose up -d mongo
      popd
    )
  )
) else (
  echo ==^> MONGO_URL points at a remote host - skipping local mongodb
)

call :port_open %OLLAMA_PORT%
if not "!PORT_OPEN!"=="1" (
  echo [!] ollama is not answering on %OLLAMA_PORT% - reviews will fail until "ollama serve" is running
)

rem --- servers ---------------------------------------------------------------
echo ==^> backend  -^> http://localhost:%BACKEND_PORT%/docs
start "Code Review Agent - backend" cmd /k "cd /d "%ROOT_DIR%backend" && uv run uvicorn app.main:app --reload --port %BACKEND_PORT%"

echo ==^> frontend -^> http://localhost:%FRONTEND_PORT%
start "Code Review Agent - frontend" cmd /k "cd /d "%ROOT_DIR%frontend" && npm run dev -- --port %FRONTEND_PORT%"

echo.
echo ==^> both servers started in their own windows; close a window to stop it
endlocal
exit /b 0

rem --- helpers ---------------------------------------------------------------
:port_open
rem Sets PORT_OPEN=1 when something is LISTENING on the given local TCP port.
set "PORT_OPEN="
for /f "tokens=*" %%l in ('netstat -ano -p tcp ^| findstr /r /c:":%~1 .*LISTENING"') do set "PORT_OPEN=1"
exit /b 0

:free_port
rem Takes the port back by killing whatever listens on it, so a stale server
rem from a previous run cannot block startup. %1 = port, %2 = label.
set "FREED="
for /f "tokens=5" %%p in ('netstat -ano -p tcp ^| findstr /r /c:":%~1 .*LISTENING"') do (
  if not "%%p"=="0" (
    echo [!] port %~1 ^(%~2^) is held by PID %%p - stopping it
    taskkill /PID %%p /T /F >nul 2>&1
    set "FREED=1"
  )
)
if defined FREED (
  rem give the OS a moment to release the socket
  timeout /t 2 /nobreak >nul
  call :port_open %~1
  if "!PORT_OPEN!"=="1" (
    echo [x] could not free port %~1
    exit /b 1
  )
)
exit /b 0
