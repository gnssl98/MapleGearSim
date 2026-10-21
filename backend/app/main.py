"""MapleGearSim 로컬 서버. `python -m app.main` 으로 실행하면 브라우저가 열린다."""

from __future__ import annotations

import os
import socket
import threading
import webbrowser

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import bm, character, craft, data, icons, ledger, market
from app.paths import FRONTEND_DIST_DIR

app = FastAPI(title="MapleGearSim")
app.include_router(craft.router)
app.include_router(data.router)
app.include_router(character.router)
app.include_router(market.router)
app.include_router(ledger.router)
app.include_router(icons.router)
app.include_router(bm.router)

if FRONTEND_DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        # index.html 은 캐시하지 않는다 (빌드마다 바뀌는 asset 파일명을 바로 반영)
        return FileResponse(FRONTEND_DIST_DIR / "index.html", headers={"Cache-Control": "no-cache"})


def main() -> None:
    import uvicorn

    host = "127.0.0.1"  # 로컬 전용
    port = int(os.environ.get("MGS_PORT", "8765"))
    with socket.socket() as sock:
        if sock.connect_ex((host, port)) == 0:
            raise SystemExit(f"{host}:{port} 를 이미 다른 프로그램(이전에 띄운 서버 등)이 쓰고 있습니다. "
                             "그 서버를 끄고 다시 실행하세요. 예: lsof -ti tcp:%d | xargs kill" % port)
    if os.environ.get("MGS_NO_BROWSER") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
