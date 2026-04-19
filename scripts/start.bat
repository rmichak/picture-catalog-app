@echo off
REM Dev launcher for Windows.
REM Starts the backend (uvicorn) and the frontend (vite) in two new console windows.

setlocal
set ROOT=%~dp0..
cd /d "%ROOT%"

if not exist "backend\.venv" (
  echo ==^> Creating Python venv ^(uv venv --python 3.12^)
  pushd backend
  uv venv --python 3.12
  popd
)

echo ==^> Installing backend deps
pushd backend
uv pip install -e ".[dev]"
popd

if not exist "frontend\node_modules" (
  echo ==^> Installing frontend deps
  pushd frontend
  call npm install
  popd
)

echo ==^> Starting backend on http://localhost:8000
start "picture-catalog backend" cmd /k "cd /d backend && .venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

echo ==^> Starting frontend on http://localhost:5173
start "picture-catalog frontend" cmd /k "cd /d frontend && npm run dev"

timeout /t 3 >nul
start http://localhost:5173

endlocal
