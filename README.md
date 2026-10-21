# MapleGearSim

메이플스토리(KMS) **템 맞추기 개인용 시뮬레이터**입니다. 내 캐릭터 장비를 불러와서 다음을 계산합니다.

- 직작(스타포스·잠재·에디·추옵) 비용의 기댓값과 분포
- 경매장 완제품을 사도 되는 상한가
- 예산 안에서 환산이 가장 많이 오르는 업그레이드 조합
- 확률형 BM과 MVP 작의 손익

로컬 PC에서만 돌아가는 웹 앱(FastAPI + React)입니다. 서버나 계정 없이 쓸 수 있습니다.

## 주요 기능

| 탭 | 하는 일 |
|---|---|
| 내 캐릭터 | 넥슨 오픈 API로 장착 장비·전투력을 불러와 아이템 이미지 타일로 표시. 부위별 다음 단계 장비(앱솔 → 아케인 → 에테르넬 등)도 보여 줌 |
| 업그레이드 추천 | 예산(메소)을 넣으면 스타포스·잠재·에디·추옵·교체 중에서 메소당 환산 상승이 큰 조합을 추천 |
| 구매 상한가 | 지금 장비 강화본과 상위 장비 완제품을 경매장에서 이 가격까지는 사도 된다는 상한가 (직작 기댓값 기준) |
| 직작 계산기 | 노작부터 목표 스펙까지의 비용 기댓값과 분포, 운(상위 %) |
| 시세 기록 | 경매장에서 본 매물을 직접 기록 (자동 수집 없음) |
| 강화 가계부 | 실제로 쓴 메소와 내 강화 운 |
| 확률형 BM | 공식 확률표를 바탕으로, 현질 금액을 넣으면 기대 회수액과 본전에 필요한 당첨 개수, 그 확률을 계산 |
| MVP 작 | MVP 등급 기준 금액을 채우는 가장 싼 방법 비교 (회수액·스타포스 할인·수수료 반영) |
| 설정 | MVP 등급, 진행 중인 이벤트(스타포스 할인 등), 보유 이벤트 아이템, **1억 메소당 현금 시세** |

이벤트 아이템(17성 강화권, 유니크 잠재 주문서, 에픽 에디 주문서)을 갖고 있으면 상한가, 직작 계산기, 추천에 반영됩니다.

## 실행

### Windows
1. [uv](https://docs.astral.sh/uv/)를 설치합니다 (최초 1회).
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
2. `start.bat`을 더블클릭하면 브라우저에서 `http://127.0.0.1:8765`가 열립니다.

### macOS / Linux
```bash
./start.sh
```
`frontend/src`가 빌드 결과보다 새로우면 프론트엔드를 다시 빌드합니다. 같은 포트에 예전 서버가 떠 있으면 종료한 뒤 실행합니다.

### 넥슨 오픈 API 키
캐릭터 불러오기에는 [넥슨 오픈 API](https://openapi.nexon.com/) 키가 필요합니다. 프로젝트 루트에 `.env` 파일을 만들고 아래처럼 적거나, 같은 이름의 환경변수로 넣어 주세요.

```
NEXON_API_KEY=발급받은_키
```

`.env`와 `data/user/`(내 설정·시세 기록)는 git에 올라가지 않습니다. 키는 내 PC에서만 쓰고 다른 곳에 보내지 않습니다.

## 데이터 출처와 원칙

- **장비·캐릭터:** 넥슨 오픈 API. 사용자가 버튼을 누를 때만 호출하고, 주기적으로 자동 호출하지 않습니다.
- **아이템 이미지:** 넥슨 오픈 API 아이콘과 [maplestory.io](https://maplestory.io) (로컬 캐시)
- **강화·잠재 확률:** 메이플스토리 공식 확률 공개 페이지와 커뮤니티 검증 자료. ⚠ 표시는 미검증 수치입니다. 자세한 내용은 `docs/research/`에 있습니다.
- **확률형 BM:**
  - 상시 상품은 하드코딩한 스냅숏(`data/game/bm_tables.json`)을 씁니다.
  - 이벤트 상품은 BM 탭을 열 때 30일이 지났으면 공식 확률 페이지에서 다시 받습니다.
  - 상품 가격과 묶음 구성은 `data/game/bm_products.yaml`에 출처와 기준일을 함께 적어 둡니다 (공식 공지·나무위키·인벤 등).
- **경매장 시세:** 넥슨 API에 없습니다. 제재 위험이 있어서 스크래핑이나 자동화도 하지 않습니다. 시세는 직접 기록하거나 입력합니다.

Data based on NEXON Open API. 개인용 비공식 도구이며 넥슨과 관계없습니다.

## 구조

| 경로 | 내용 |
|---|---|
| `backend/app/engine/` | 계산 엔진: starforce, potential, flame, compare, recommend, shopping, next_step, tickets, bm, bm_source, mvp |
| `backend/app/api/` | REST API: character, craft, market, data, ledger, icons, bm |
| `backend/app/nexon/` | 넥슨 오픈 API 클라이언트 (캐시 포함) |
| `backend/scripts/` | 데이터 수집 스크립트: 잠재 확률표, 아이템 카탈로그, BM 확률표 스냅숏 (패치 후 수동 실행) |
| `data/game/` | 게임 수치 테이블. 패치가 나오면 이 파일들만 고치면 됩니다 |
| `data/user/` | 내 설정·시세 기록 (git 제외) |
| `data/cache/` | API·아이콘·BM 확률표 캐시 (git 제외) |
| `frontend/` | React + Vite + TypeScript UI. `npm run build`로 `frontend/dist`를 만듭니다 |
| `docs/` | 요구사항, 계획(`02_plan.md`), 리서치, 약관 정리 |

## 개발

```bash
cd backend && uv run pytest          # 엔진/API 테스트
cd frontend && npm install && npm run dev   # UI 개발 서버 (API는 8765로 프록시)
```

데이터 갱신 (패치 후):

```bash
cd backend
uv run python scripts/fetch_potential_tables.py   # 잠재 옵션 확률표
uv run python scripts/fetch_item_catalog.py       # 상위 장비 카탈로그 (maplestory.io)
uv run python scripts/fetch_bm_tables.py          # 확률형 BM 전체 스냅숏
```
