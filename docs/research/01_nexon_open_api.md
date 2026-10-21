# 01. 넥슨 Open API (메이플스토리 KMS) 조사

> 조사일: 2026-10-15 · 대상: 메이플스토리 한국(KMS)
> 표기: **[공식]** = openapi.nexon.com 확인 / **[래퍼]** = 커뮤니티 SDK(SpiralMoon/maplestory.openapi) 소스 기준. 래퍼는 "넥슨 Open API 패치와 동기화"를 표방하지만 공식 문서가 아니므로 실제 응답으로 재검증 필요.

## 1. 개요

- 넥슨 Open API는 넥슨 게임 데이터를 외부 개발자에게 제공하는 공식 플랫폼. 2023-12 리뉴얼 때 메이플스토리 데이터가 큐브 확률 정보에서 게임 전반으로 확대됨.
- **Base URL**: `https://open.api.nexon.com` (메이플 KMS 경로 prefix: `/maplestory/v1/...`) [공식/래퍼]
- **인증**: HTTP 헤더 `x-nxopen-api-key: <API_KEY>` [공식]
- **호출 한도** [공식, 사전 준비 가이드]:

| 애플리케이션 타입 | 초당 최대 | 일일 최대 |
|---|---|---|
| 개발 단계 | 5 | 1,000 |
| 서비스 단계 | 500 | 20,000,000 |

  - 한도는 **애플리케이션 단위**로 합산(같은 앱의 키 2개를 써도 합산).
  - 앱당 API 키 최대 2개, 넥슨 ID당 같은 게임 앱 최대 3개.
  - 서비스 단계는 서비스 URL·설명·대표 이미지 등 등록 필요. 개인용 도구는 **개발 단계 키(5 rps / 1,000 req/day)** 로 충분.
- **경매장(메이플 옥션) 데이터 엔드포인트는 없음** (2026-10-15 기준 공식 페이지 카테고리 목록에 없음 → `02_auction_house.md` 참고).

## 2. 상세

### 2.1 데이터 갱신 시점 [래퍼 doc 주석 — 공식 문서 문구를 옮긴 것으로 보임]

- 게임 데이터는 **평균 15분 후** 조회 가능 (실시간 아님).
- **2023-12-21 데이터부터** 조회 가능.
- `date=YYYY-MM-DD`(KST)로 과거 일자 조회. **전일 데이터는 다음날 오전 2시(KST)부터** 확정 조회 가능 (예: 12/22 조회 → 22일 00시~23일 00시 사이 데이터).
- `date` 생략 시 최신(약 15분 지연) 데이터.
- **ocid는 게임 콘텐츠 변경으로 바뀔 수 있음** → ocid 영구 캐싱 금지, 캐릭터명으로 재조회 경로 유지.
- 약관상: API로 수집(크롤링)한 데이터는 **30일 이내 갱신 의무** [공식, 사이트 푸터].
- 2026-08-20 업데이트(공지): 기타 능력치 영향 요소(other-stat)·연무장에 마스터라벨 성장/전투 플러스 효과 추가, 스케줄러에 신규 보스 '벨로나' 추가 [공식 공지].

### 2.2 에러 코드 [공식]

| 코드 | HTTP | 의미 |
|---|---|---|
| OPENAPI00001 | 500 | 서버 내부 오류 |
| OPENAPI00002 | 403 | 권한 없음 |
| OPENAPI00003 | 400 | 유효하지 않은 식별자(ocid 등) |
| OPENAPI00004 | 400 | 파라미터 누락/오류 |
| OPENAPI00005 | 400 | 유효하지 않은 API 키 |
| OPENAPI00006 | 400 | 유효하지 않은 게임/API 경로 |
| OPENAPI00007 | 429 | 호출량 초과 |
| OPENAPI00009 | 400 | 데이터 준비 중 |
| OPENAPI00010 | 400 | 게임 점검 중 |
| OPENAPI00011 | 503 | API 점검 중 |

### 2.3 엔드포인트 카테고리 (KMS)

공식 페이지 카테고리: 캐릭터 정보 / 유니온 정보 / 길드 정보 / 연무장 정보 / 확률 정보 / 스케줄러 정보 / 랭킹 정보 / 공지 정보. 경로는 래퍼 소스 기준.

| 분류 | 경로 (`/maplestory/v1` 이하) | 비고 |
|---|---|---|
| 식별자 | `/id?character_name=` | ocid 조회 |
| 계정 | `/character/list`, `/user/achievement` | 계정 단위 — 사용자 본인 계정 연동 키(넥슨 Open ID 로그인 기능 기반) 필요로 추정 |
| 캐릭터 | `/character/basic`, `/character/popularity`, **`/character/stat`**, `/character/hyper-stat`, `/character/propensity`, `/character/ability`, **`/character/item-equipment`**, `/character/cashitem-equipment`, `/character/symbol-equipment`, **`/character/set-effect`**, `/character/beauty-equipment`, `/character/android-equipment`, `/character/pet-equipment`, `/character/skill?character_skill_grade=`, `/character/link-skill`, `/character/vmatrix`, `/character/hexamatrix`, **`/character/hexamatrix-stat`**, `/character/dojang`, **`/character/other-stat`**, `/character/ring-exchange-skill-equipment`, `/character/ring-reserve-skill-equipment` | 공통 파라미터 `ocid`, `date`(선택) |
| 유니온 | `/user/union`, **`/user/union-raider`**, **`/user/union-artifact`**, `/user/union-champion` | ocid 기반 |
| 길드 | `/guild/id`, `/guild/basic` | |
| 연무장 | `/battle-practice/replay-id`, `/result`, `/skill-timeline`, `/character-info` | |
| 스케줄러 | `/scheduler/character-state` | |
| 확률(히스토리) | `/history/starforce`, `/history/cube`, `/history/potential` | **본인 계정 키** 필요(타인 조회 불가), 강화·재설정 이력 |
| 랭킹 | `/ranking/overall`, `/union`, `/guild`, `/dojang`, `/theseed`, `/achievement` | |
| 공지 | `/notice`, `/notice-update`, `/notice-event`, `/notice-cashshop` (+`/detail`) | |

### 2.4 `/character/item-equipment` 응답 구조 [래퍼 타입 정의 기준]

최상위:

```
date, character_gender, character_class,
preset_no                      # 현재 적용 프리셋
item_equipment[]               # 현재 장착 장비
item_equipment_preset_1..3[]   # 프리셋별 장비
title{...}, medal_shape{...}
dragon_equipment[], mechanic_equipment[]   # 에반/메카닉 전용
```

`item_equipment[]` 각 항목 주요 필드:

| 필드 | 의미 | 비고 |
|---|---|---|
| `item_equipment_part` / `item_equipment_slot` | 부위 / 슬롯명 | 슬롯 키로 사용 |
| `item_name`, `item_icon`, `item_description`, `item_shape_name` | 이름·아이콘·외형(신비의 모루) | |
| `item_base_option{}` | 기본 옵션 + `base_equipment_level` | 기본 스탯(아이템 고유) |
| `item_add_option{}` | **추가옵션(추옵)** | str, dex, int, luk, max_hp, max_mp, attack_power, magic_power, armor, speed, jump, boss_damage, damage, all_stat, equipment_level_decrease |
| `item_etc_option{}` | **주문서 작** 등 기타 강화 | str~jump |
| `item_starforce_option{}` | **스타포스로 오른 수치** | str~jump |
| `item_exceptional_option{}` | 익셉셔널 강화 수치 + `exceptional_upgrade` | |
| `item_total_option{}` | 위 합산(최종) | + ignore_monster_armor, all_stat, damage, boss_damage, max_hp_rate, max_mp_rate, equipment_level_decrease |
| `starforce` | 스타포스 수 (문자열) | `"22"` 등 |
| `starforce_scroll_flag` | 놀장강(스타포스 주문서) 적용 여부 | 문자열 플래그 |
| `potential_option_grade` / `additional_potential_option_grade` | 잠재/에디 등급 | 레어/에픽/유니크/레전드리 (한글 문자열) |
| `potential_option_1..3` / `additional_potential_option_1..3` | 잠재 옵션 줄 (문자열) | 예: `"STR : +12%"` 형태 → **파싱 필요** |
| `potential_option_flag`, `additional_potential_option_flag` | 잠재 봉인/설정 여부 플래그 | 정확한 의미 실데이터 확인 필요 |
| `scroll_upgrade`, `scroll_upgradeable_count`, `scroll_resilience_count` | 업그레이드 완료 / 남은 가능 / 복구 가능 횟수 | |
| `cuttable_count` | **가위 사용 가능 횟수** | 거래 가능성 판단에 활용 |
| `golden_hammer_flag` | 황금망치 적용 여부 | |
| `soul_name`, `soul_option` | 소울 | 무기 |
| `equipment_level_increase`, `growth_exp`, `growth_level` | 성장형 장비 | |
| `special_ring_level` | 시드링 레벨 | |
| `date_expire`, `freestyle_flag` | 만료일, 자유 장착(프리스타일 쿠폰) | |

주의: **수치 대부분이 문자열**(`"12"`)로 옴 → 숫자 변환 필요. `%` 옵션(보공·방무·올스탯%·데미지)과 고정치가 같은 객체에 섞여 있음.

### 2.5 스탯 환산 계산에 쓸 다른 엔드포인트 [래퍼 기준]

| 엔드포인트 | 핵심 필드 | 용도 |
|---|---|---|
| `/character/stat` | `final_stat[{stat_name, stat_value}]`, `remain_ap` | 최종 스탯(전투력, 주스탯, 보공, 방무, 크뎀 등) — 시뮬레이터 검증용 기준값 |
| `/character/set-effect` | `set_effect[{set_name, total_set_count, set_effect_info[{set_count,set_option}], set_option_full[]}]` | 세트효과(문자열 옵션) |
| `/character/hyper-stat` | `hyper_stat_preset_n[{stat_type, stat_level, stat_increase}]`, `use_preset_no` | |
| `/character/ability` | `ability_info[{ability_no, ability_grade, ability_value}]` + 프리셋 | |
| `/character/symbol-equipment` | `symbol[{symbol_name, symbol_level, symbol_force, symbol_str..}]` | 아케인/어센틱/그랜드 심볼 |
| `/character/hexamatrix-stat` | `character_hexa_stat_core[_2,_3][{main_stat_name, sub_stat_name_1/2, *_level, stat_grade}]` | 헥사 스탯 |
| `/character/other-stat` | `other_stat[{other_stat_type, stat_info[{stat_name, stat_value}]}]` | 기타 능력치 영향 요소(2026-08 마스터라벨 플러스 반영) |
| `/user/union-raider` | `union_raider_stat[]`, `union_occupied_stat[]`, `union_inner_stat[]`, 프리셋 1~5 | 유니온 공격대/점령 효과(문자열) |
| `/user/union-artifact` | `union_artifact_effect[{name, level}]`, `union_artifact_crystal[]` | 아티팩트 |
| `/user/union` | `union_level`, `union_grade`, `union_artifact_level` 등 | |

## 3. 프로그램 설계 시 시사점

1. **조회 흐름**: 캐릭터명 → `/id`로 ocid → item-equipment / stat / set-effect / union-* / hexamatrix-stat / symbol / other-stat 병렬 호출. 개발 키 **초당 5회** 제한 → 큐잉·직렬화 + 429(OPENAPI00007) 재시도(backoff) 필수.
2. **캐싱**: 데이터가 평균 15분 지연·전일 확정은 익일 02시 → 동일 캐릭터 응답을 최소 15분 캐시. 일 1,000회 한도 고려하여 로컬 저장(SQLite/JSON). ocid 변경 가능성 대비 캐시 키는 (캐릭터명, ocid) 병행.
3. **옵션 파싱 레이어**: 잠재/에디/세트/유니온/어빌은 **자유 문자열**("보스 몬스터 공격 시 데미지 : +40%") → 정규식 파서 + 매핑 테이블이 핵심 모듈. 미인식 문자열은 로깅하여 점진 보강.
4. **스탯 분해**: `item_total_option = base + add(추옵) + etc(작) + starforce + exceptional`로 분해 가능 → "아이템 교체 시 변화량" 계산 시 부위별 구성 요소를 바꿔 끼워 재계산. 단, 잠재옵션 %는 total_option에 포함되지 않으므로 별도 합산 필요(실데이터로 확인).
5. **검증 기준값**: `/character/stat`의 최종 스탯·전투력으로 자체 계산기의 정확도를 회귀 테스트.
6. **세트효과 변화**: 장비 교체 시 세트 카운트가 변함 → `set_option_full`(전체 단계 옵션)을 사용해 교체 후 세트효과를 재계산.
7. **프리셋**: `preset_no`와 `item_equipment_preset_1..3`이 있으므로 현재 프리셋 기준으로만 계산할지 옵션 제공.
8. **경매장 가격은 API로 불가** → 가격 입력 모듈은 별도(02 문서).
9. API 키는 로컬 환경변수/설정 파일로 관리, 저장소 커밋 금지. 2개 키 발급 가능하므로 유출 시 교체.

## 4. 불확실 / 추가 확인 필요

- 엔드포인트 경로·필드명은 **래퍼 소스 기준**. 공식 문서 페이지는 JS 렌더링이라 직접 추출하지 못함 → 키 발급 후 실제 응답 JSON 샘플을 `docs/samples/`에 저장해 검증 필요.
- `potential_option_flag`의 정확한 의미, `starforce_scroll_flag` 값 형식("0"/"1"? "사용"?) 미확인.
- 잠재능력 %옵션이 `item_total_option`에 반영되는지 여부 미확인(반영 안 되는 것으로 알려져 있으나 검증 필요).
- `/character/list`·`/history/*`의 인증 방식(본인 계정 연동 키 요구 조건) 세부 미확인.
- 래퍼 doc의 "평균 15분", "익일 02시" 문구가 2026-10 현재 공식 문구와 동일한지 공식 페이지에서 재확인 필요.
- 2026년 신규 엔드포인트가 래퍼에 아직 반영 안 됐을 가능성.

## 5. 출처

- 넥슨 Open API 메이플스토리 메인(카테고리 목록, 30일 갱신 의무): https://openapi.nexon.com/ko/game/maplestory/
- API 사용하기(헤더, 에러코드): https://openapi.nexon.com/ko/guide/request-api/
- 사전 준비(호출 한도, 키/앱 수 제한): https://openapi.nexon.com/ko/guide/prepare-in-advance/
- 메이플스토리 Open API 업데이트 안내 (2026-08-19 게시, 08-20 적용): https://openapi.nexon.com/ko/support/notice/3528490/
- 메이플스토리 Open API 업데이트 안내(과거): https://openapi.nexon.com/ko/support/notice/2580334/
- SpiralMoon/maplestory.openapi (경로·응답 타입·갱신 주석): https://github.com/SpiralMoon/maplestory.openapi
  - `js/src/maplestory/api/kms/mapleStoryApi.ts`, `js/src/maplestory/api/kms/response/character/characterItemEquipmentBody.ts` 등
- 넥슨 오픈 API 리뉴얼 보도(2023-12): https://byline.network/2023/12/21-311/ , https://m.ddaily.co.kr/page/view/2023121511103003221
