@echo off
chcp 65001 >nul
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
  echo [MapleGearSim] uv 가 필요합니다. PowerShell 에서 아래 명령으로 설치한 뒤 다시 실행하세요.
  echo   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  pause
  exit /b 1
)

if not exist "frontend\dist\index.html" (
  where npm >nul 2>nul
  if errorlevel 1 (
    echo [MapleGearSim] frontend\dist 가 없습니다. Node.js 를 설치하거나 빌드된 dist 폴더를 받아주세요.
    pause
    exit /b 1
  )
  pushd frontend
  call npm install
  call npm run build
  popd
)

cd backend
echo [MapleGearSim] http://127.0.0.1:8765 에서 실행합니다. 종료하려면 이 창을 닫으세요.
uv run --python 3.12 python -m app.main
pause
