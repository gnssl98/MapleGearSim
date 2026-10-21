import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
GAME_DATA_DIR = DATA_DIR / "game"
USER_DATA_DIR = Path(os.environ["MGS_USER_DATA_DIR"]) if os.environ.get("MGS_USER_DATA_DIR") else DATA_DIR / "user"  # 테스트·데모용 분리
FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "dist"
