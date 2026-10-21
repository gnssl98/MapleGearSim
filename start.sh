#!/usr/bin/env bash
# macOS/Linux 개발용 실행 스크립트
set -e
cd "$(dirname "$0")"
# 화면 소스가 마지막 빌드보다 새로우면 다시 빌드
if [ ! -f frontend/dist/index.html ] || [ -n "$(find frontend/src frontend/index.html -newer frontend/dist/index.html -print -quit)" ]; then
  (cd frontend && { [ -d node_modules ] || npm install; } && npm run build)
fi
# 이전에 띄운 MapleGearSim 서버가 남아 있으면 종료 (다른 프로그램이면 건드리지 않음)
for pid in $(lsof -ti tcp:"${MGS_PORT:-8765}" 2>/dev/null); do
  if ps -o command= -p "$pid" | grep -q "app.main"; then kill "$pid"; sleep 1; fi
done
cd backend && uv run --python 3.12 python -m app.main
