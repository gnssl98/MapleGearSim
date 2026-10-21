# 10. 환산 주스탯 계산 로직 (simaple 분석 + 공개 공식 + 직업 데이터)

> 작성일: 2026-10-15 / 대상: KMS / 선행 문서: `05_hwansan_stat.md`
> 표기: **[확인]** 1차 출처(코드·공식 공지·문서)에서 직접 확인, **[커뮤니티]** 커뮤니티 글 기준, **[미검증]** 이번 조사에서 1차 확인 못 함

---

## 1. 개요

- 환산 주스탯 계산은 결국 두 단계다.
  1. **데미지 기대값 함수** `D(spec)`: 스탯·공격력·데미지%·보공·최종뎀·크뎀·방무 등을 곱연산으로 묶은 스칼라.
  2. **주스탯 단위로 역산(inversion)**: `D` 값을 "주스탯이 몇이면 이 데미지가 나오는가"로 바꾼다.
- 오픈소스 **simaple**(MIT)은 (1)을 `DamageLogic.get_damage_factor`로, (2)를 **기준 스펙(GearBlueprint) 여러 개로 "데미지 → 주스탯" 회귀 곡선을 만들어 역산**하는 `RegressionMetric`으로 구현한다. 원조 "환산 엑셀 시트" 방식(기준 세팅 대비 비교)을 코드화한 것으로 보인다. [확인: 코드]
- maplescouter의 계산식·가정은 **공개되어 있지 않다**(가이드/FAQ/사이트맵/인벤 운영 가이드 확인, 기준 방어율·크리 가정 언급 없음). 따라서 우리 수치는 maplescouter와 **절대값이 일치하지 않을 것**을 전제로 설계한다. [확인]
- 우리 프로그램 권장안: **"한계 효율(차분) 방식"**을 기본으로 하고(장비 교체 Δ를 주스탯 단위로), simaple식 **기준 스펙 회귀**는 "절대 환산값" 표시가 필요할 때 선택적으로 쓴다(§5).

---

## 2. simaple 로직 분석

### 2.1 저장소 정보
- URL: https://github.com/simaple-team/simaple — `git clone --depth 1` 시점 HEAD `669abf2` "Feature/existence (#369)", **마지막 커밋 2025-04-15** [확인]
- 라이선스: MIT, "Copyright (c) 2022 Bumju Kwak and other contributers" (`LICENSE`) [확인]
- README.md 69–70행: "GearBlueprint를 통해, 환산 주스텟 등에 사용되는 기준 캐릭터 스펙의 성능 계산", "환산 주스텟 계산, 스텟별 효율 계산". README.en.md 12행: "converted stat (via the popular KMS Stat Conversion sheet)". [확인]
- **유지보수 상태**: 2025-04 이후 커밋 없음 → **렌(2025-06-19 출시) 미포함**(`simaple/core/jobtype.py`에 ren 없음), 2025 하반기~2026 밸런스 패치 미반영. 기준 블루프린트도 Lv 245~270, 22성/레전 수준의 2023~2024년 스펙 기준. **코드 구조·공식 참고용이지 상수 최신본으로 쓰면 안 됨.** [확인]

### 2.2 핵심 데미지 공식 — `simaple/core/damage.py`

`DamageLogic`(11행)의 필드: `attack_range_constant`(무기상수 계열 상수), `mastery`(숙련도).

**(a) 스탯 반영치** — `simaple/core/base.py` 235–245행
```
주스탯_eff = int( 순스탯 × (1 + 스탯% × 0.01) + 미적용(static)스탯 )
```
- `STRBasedDamageLogic.get_base_stat_factor` (damage.py 116–119): `STR_eff × 4 + DEX_eff`
- `LUKBasedDamageLogic` (184–191): `LUK_eff × 4 + DEX_eff` ← 나이트로드
- `LUKBasedDualSubDamageLogic` (208–217): `LUK_eff × 4 + DEX_eff + STR_eff` (섀도어/듀블/카데나용 클래스. 단, 데이터에선 shadower가 `LUKBasedDamageLogic`으로 지정되어 있어 불일치 존재)
- `INTBasedDamageLogic` (136–143): `INT_eff × 4 + LUK_eff`, 공격 타입 = 마력
- 심볼 스탯은 `get_symbol_stat` → `*_static`(미적용 스탯)으로 들어감 (132–133 등)

**(b) 공격력 반영치** — base.py 247–251행
```
공격력_eff = 공격력 × (1 + 공격력% × 0.01)        (마법사는 마력)
```

**(c) 일반 데미지 항** — damage.py 66–69
```
(1 + (보공% + 데미지%) × 0.01) × (1 + 최종뎀% × 0.01)
```
- 보공·데미지는 합연산, 최종뎀은 스탯 합산 시 곱연산 누적: base.py 145–147 `FD = a + b + 0.01ab`

**(d) 방어율 항** — damage.py 71–72, 기본 `armor=300` (77행)
```
armor_factor = 1 − 0.0001 × armor × (100 − 방무%)      # armor=300 → 보스 방어율 300%
```
- 방무 누적: base.py 148–149 `방무 = 100 − 0.01 × (100−a)(100−b)` (곱연산)

**(e) 크리티컬 항** — damage.py 74–75
```
crit_factor = 1 + (35 + 크뎀%) × min(100, 크확%) × 0.0001
```
- **기본 크리 배율 평균 35%**(120~150%의 중간) 가정. 크확 100% 상한.

**(f) 속성 항** — damage.py 99–100: `0.5 × (1 + min(100, 속성내성무시%) × 0.01)` (상수배라 비교 시 상쇄)

**(g) 최종 기대 데미지 계수** — damage.py 77–89
```
D = (c) × (d) × (e) × (a) × (b) × (f) × attack_range_constant × 0.01 × ((1 + mastery) / 2)
```
- 참고: 상태창 **최대 스탯공격력** 재현식(52–61): `(1+데미지%)(1+최종뎀%) × (a) × (b) × attack_range_constant × 0.01` (보공 제외), 최소 = 최대 × mastery.
- `get_compat_power`(102–109): 전투력 유사 지표 `(a)×0.01 × int(b) × (1+보공+데미지) × (1+0.01(35+크뎀)) × 1.1(제네시스 무기 시)`.

### 2.3 주스탯으로의 역산 — `simaple/metric/metric.py`

`RegressionMetric` (19–61행):
1. `item_independent_stat`(직업 패시브 등 아이템 무관 스탯, `get_passive(...)`로 생성)을 모든 스펙에 더함 (43, 47행).
2. 기준 스펙 여러 개를 `add_reference`로 등록 (31–32). 테스트 예시(`tests/metric/test_metric.py` 22–35): Epic, EpicUnique, Unique, Legendary18, LegendaryHalf, Legendary 6개.
3. 각 기준 스펙에 대해 x = `get_damage_factor(stat)/1e9`, y = `get_major_stat(stat)`(= 주스탯_eff, 즉 `int(순×(1+%)+미적용)`) 계산 (42–49).
4. **3차 다항 + Ridge(alpha=1e-3)** 회귀로 `x → y` 곡선 학습 (34–40).
5. 대상 스펙의 `D`를 넣어 예측한 y = **환산 주스탯** (51–61).

즉 simaple의 환산 = "**이 데미지를 내는 '기준 세팅 계열' 캐릭터의 주스탯은 얼마인가**". 공격력·보공 등 다른 요소가 기준 세팅들과 함께 자라는 것을 전제로 한 보간이다. (주의: 기준 스펙이 오래되어 현 스펙(헥사·고레벨) 영역에서는 **외삽**이 되어 부정확.)

- 기준 스펙 정의: `simaple/data/baseline/blueprints/*.yaml` — Epic(에픽둘둘, Lv245, 유니온 28블록, 12성), EpicUnique(Lv250), Unique, Legendary18(18성, Lv260), LegendaryHalf(Lv260), Legendary(레전둘둘, 22성, Lv270, union_block_count 33). 빌드: `simaple/data/baseline/__init__.py` 73–81 `get_baseline_gearset()` → `GearsetBlueprint.build()` (`simaple/gear/blueprint/gearset_blueprint.py` 17–39), 개별 장비 `GeneralizedGearBlueprint`/`PracticalGearBlueprint` (`simaple/gear/blueprint/gear_blueprint.py` 68, 134).
- 미리 계산된 기준 스탯 예: `tests/metric/refs/Legendary.json` (아크메이지 기준).

### 2.4 스탯 효율(한계 효율) 사용처
- 각 optimizer가 `get_damage_factor(stat + 후보, armor)`의 크기를 직접 비교(하이퍼스탯 `simaple/optimizer/hyperstat_optimizer.py` 27, 유니온 `union_optimizer.py` 36, 링크 `link_optimizer.py` 37, 무기 잠재 `weapon_potential_optimizer.py` 81–113, 아티팩트 `preset.py` 91–99). 즉 **"D의 비율로 비교"** 하는 방식이 기본. [확인]

### 2.5 직업 상수 데이터 — `simaple/data/jobs/resources/damage_logic.yaml`, `.../adele/damage_logic.yaml`
| 직업 | 클래스 | attack_range_constant | mastery 식 | 파일/행 |
|---|---|---|---|---|
| 아델 | STRBased | **1.3** | `0.90 + 0.01×((skill_level+1)//2)` | `adele/damage_logic.yaml` 1–13 |
| 나이트로드 | LUKBased (LUK×4+DEX) | **1.75** | `0.85 + 0.01×((skill_level+1)//2)` | `damage_logic.yaml` 366–375 |
| 렌 | (없음) | – | – | 미지원 |

- simaple은 **무기상수와 직업보정을 분리하지 않고** `attack_range_constant` 하나로 둔다(예: 다크나이트 1.49, 제로 1.49, 팔라딘 1.34, 히어로 계열 등). 아델·나로 값은 각 무기상수(튜너 1.3, 아대 1.75)와 같으므로 이 두 직업의 직업보정은 1.0으로 취급된 셈. [확인: 코드]
- mastery의 skill_level은 5차/6차 마스터리 코어 등 추가 숙련도 레벨로 추정. [미검증]

---

## 3. 기타 공개 공식 / 오픈소스

| 출처 | 내용 | 비고 |
|---|---|---|
| 나무위키 「메이플스토리/스탯」 | 크리 기본 120~150% → **평균 크리 보정 `1 + 크확 × (0.35 + 크뎀%)`**; 방어율 보정 `1 − 몹방어율 × Π(1−방무_i)`; 예시 보스 방어율 카오스 벨룸 200%, 윌/데미안 300%, 그란디스 보스 380%; 숙련도 기본(마법 25/근접 20/원거리 15) + 70%p → 95/90/85%, **평균 숙련도 보정 `(1+숙련도)/2`**; 최대 스탯공격력 = 스탯반영치×총공×데미지%(보공 제외)×최종뎀×무기상수, 최소 = 최대×숙련도; "직업 상수"는 비공식 용어 | simaple 공식과 일치 [확인] |
| 인벤 34689 (2023) | `(주스탯×4+부스탯)×총공격력×무기상수×직업보정상수/100` 후 퍼뎀·크리·공%·(데미지+보공)·방무·최종뎀 곱 | 직업보정상수 표 없음 [커뮤니티] |
| 인벤 22224 (2020) | "x의 y 대비 효율 = 딜상승률 비" (한계효율 정의), 미적용 스탯 분리 | 05 문서 참조 [커뮤니티] |
| 인벤 31052 등 | 경험칙: 주스탯 40(심볼 제외) ≈ 주스탯% 4% ≈ 공격력 10 | 스펙 의존 [커뮤니티] |
| maplescouter (운영 측 공개 설명) | Open API 기반, 환산 계산식/가정 미공개. 인벤 운영 가이드(2026-06-24)도 기능 설명(보스 컷 = 이지 림보 200% 기준 배율, 헥사 환산 vs 일반 환산 차이 = 6차 스킬 진행도)만 있음 | 코드/역공학 사용 금지 |
| GitHub limchanggeon/MAGPT | 추옵 환산 `주스탯 + 올스탯 1%당 10` (표시용 관례라고 명시) | 단순 관례 |
| GitHub Skylark51/MapleManageForMe | Open API 스탯 기반 비교 휴리스틱, maplescouter 공식 미복제 명시 | 참고만 |

→ **현재 공개된 오픈소스 중 실제 데미지식 + 역산을 갖춘 것은 simaple이 사실상 유일**. 나머지는 경험칙 계수.

---

## 4. 직업 데이터

| 항목 | 아델 (Adele) | 나이트로드 (Night Lord) | 렌 (Ren) |
|---|---|---|---|
| 계열 | 전사 (레프) | 도적 (모험가) | 전사 (아니마) |
| 주스탯 | STR [확인: simaple STRBased] | LUK [확인: simaple LUKBased] | **STR** [나무위키; 공식 공지 스킬 "신체 단련을 통해 힘을 증가시킨다"] |
| 부스탯 | DEX | DEX (단일) | DEX [나무위키] |
| 스탯 반영식 | 4×STR + DEX | 4×LUK + DEX | 4×STR + DEX |
| 주무기 | 튜너 (한손) | 아대 (두손) | **장검** [공식 공지 스킬명 "장검 숙련/장검 가속", 기사] |
| 보조무기 | 브레이슬릿 [미검증] | 표창 [미검증] | 여의보주 [확인: 공식 공지 장비 목록] |
| 공격 타입 | 공격력 | 공격력 | 공격력 |
| 무기상수 | **1.3** [나무위키 튜너/스탯, simaple] | **1.75** (전 무기 1위) [나무위키 아대/스탯, simaple] | **1.3** [나무위키; 공식 확인 X] |
| 직업보정 | 1.0 (simaple 상 별도 보정 없음) [미검증] | 1.0 [미검증] | 1.0 가정 [미검증] |
| 숙련도(최종) | 90% + 추가 (simaple: 0.90+) | 85% + 추가 (simaple: 0.85+) | 근접 90% 추정 [미검증] |
| 출시 | 2020 | – | **2025-06-19** (여름 1차 "ASSEMBLE") [확인: 공식 공지 News/Update/775] |

> 렌의 무기상수·직업보정은 공식 표기가 없음. 아래 §5의 "최대 스탯공격력 역산"으로 실측 검증 권장.

---

## 5. 우리 프로그램 적용 설계안

### 5.1 입력 (Nexon Open API)
| 단계 | 엔드포인트 (`/maplestory/v1/...`) | 사용 필드 |
|---|---|---|
| 직업/레벨 | `id`, `character/basic` | `character_class`, `character_level` → 직업 테이블 lookup |
| 최종 스탯 | `character/stat` | STR/DEX/LUK, 공격력, 데미지, 보스 몬스터 데미지, 최종 데미지, 방어율 무시, 크리티컬 확률/데미지, **최대 스탯공격력**, 전투력 [필드명 미검증] |
| 미적용 스탯 분리 | `character/symbol-equipment`, `character/hyper-stat`, `character/ability`, `character/hexamatrix-stat` | 고정(%) 미적용 주스탯 |
| 부위 분해 | `character/item-equipment`, `character/set-effect` | 부위별 total/base/add/etc/starforce/잠재/에디 옵션 |
| 기타 | `user/union-raider`, `union-artifact`, `character/link-skill`, `character/skill` | 공격력%·보공·방무 등 |

### 5.2 계산 단계
1. **직업 설정 로드**: `jobs.yaml` 에 `{main, sub[], attack_type, weapon_const, job_corr, mastery}` (아델/나로/렌, §4). 버전 태그.
2. **스탯 분해**: 장비/세트/심볼/하이퍼/어빌/헥사스탯 합산으로 `순주스탯, 주스탯%, 미적용주스탯`(부스탯 동일), `순공, 공%` 를 구성. 최종값(`character/stat`)과의 차이를 "기타(패시브/유니온 등)" 잔차로 흡수.
3. **보정 검증(캘리브레이션)**: simaple 52–61행 식으로 `최대 스탯공격력`을 재계산 → API 값과 비교. 비율 = `weapon_const × job_corr` 실측치. 렌처럼 상수가 불확실한 직업은 이 값으로 보정(오차 >1%면 경고).
4. **데미지 함수** `D(spec)` = simaple §2.2(g)와 동일 구조 (보스 방어율 파라미터: 기본 300, 옵션 380), 크리 평균 35%.
5. **한계 효율**: `k_main = D(spec + 주스탯_eff 1) / D(spec) − 1` (실제로는 `1/(4·M_eff + S_eff) × 4` 해석해 사용 가능).
6. **부위/옵션 환산**: 후보 변경 Δ에 대해 `환산Δ = ln(D(spec+Δ)/D(spec)) / ln(D(spec+1주스탯)/D(spec))` 또는 근사 `(D'/D − 1)/k_main`. 비선형(방무·보공 포화) 자동 반영.
7. **절대 환산값(선택)**: (a) 단순형: `환산 = M_eff × D(spec)/D(spec 의 주스탯 외 요소를 기준값으로 고정)`, 또는 (b) simaple식 기준 스펙 3차 회귀. 기준 스펙은 **2026 현행 스펙 구간**으로 재작성 필요 → v1에서는 "Δ 환산" 위주로 출시, 절대값은 "자체 기준(maplescouter와 다름)" 명시.
8. **억당 환산**: `환산Δ / 순비용(억)` (05 문서 §2.5).

### 5.3 구현 메모
- 정수 절삭: simaple은 스탯 반영치를 `int()` 절삭 (base.py 237–243). 게임 표시값과 맞추려면 동일하게.
- 최종뎀/방무는 덧셈 금지(곱연산 누적 함수 사용).
- 기준 보스 방어율·크리 평균·숙련도는 설정값으로 노출.

---

## 6. 불확실 항목
- [ ] 렌 무기상수 1.3·부스탯 DEX: 나무위키 기준, 공식 수치 미확인 → §5.2-3 실측으로 확인.
- [ ] 직업보정상수: 공식 용어 아님(나무위키). 아델/나로/렌 = 1.0 가정. 실측 필요.
- [ ] 아델/나로 보조무기명, 렌 숙련도 수치.
- [ ] `character/stat` 필드명(최대 스탯공격력 등) 공식 문서 대조.
- [ ] 2025-04 이후 패치(크리 공식, 숙련도, 6차 마스터리 등)가 simaple 공식에 영향이 있는지.
- [ ] maplescouter의 기준 방어율·크리·도핑 가정(비공개) → 절대값 일치 불가.
- [ ] simaple 기준 블루프린트가 구버전(Lv245~270) → 현 스펙 외삽 오차.

---

## 7. 출처
- simaple: https://github.com/simaple-team/simaple (HEAD 669abf2, 2025-04-15) — `simaple/core/damage.py`, `simaple/core/base.py`, `simaple/metric/metric.py`, `simaple/data/jobs/resources/damage_logic.yaml`, `simaple/data/jobs/resources/adele/damage_logic.yaml`, `simaple/data/baseline/__init__.py`, `simaple/data/baseline/blueprints/*.yaml`, `simaple/gear/blueprint/*.py`, `tests/metric/test_metric.py`, `README.md`, `LICENSE`
- 나무위키 메이플스토리/스탯: https://namu.wiki/w/메이플스토리/스탯
- 나무위키 렌(메이플스토리): https://namu.wiki/w/렌(메이플스토리)
- 나무위키 튜너: https://namu.wiki/w/튜너(메이플스토리) / 아대: https://namu.wiki/w/아대
- 메이플스토리 공식 업데이트(2025-06-19, 렌): https://maplestory.nexon.com/News/Update/775
- 기사(렌 장검 사용): https://v.daum.net/v/20250621182512204
- 인벤 34689: https://www.inven.co.kr/board/maple/2304/34689 / 22224: https://www.inven.co.kr/board/maple/2304/22224 / 31052: https://www.inven.co.kr/board/maple/2322/31052
- 인벤 환산주스탯 사이트 가이드(2026-06-24): https://www.inven.co.kr/board/maple/5974/6771574
- maplescouter: https://maplescouter.com/ko/guide , https://maplescouter.com/ko/sitemap
- MAGPT: https://github.com/limchanggeon/MAGPT / MapleManageForMe: https://github.com/Skylark51/MapleManageForMe

---

## 8. 라이선스 주의 (MIT)
- simaple은 MIT. 공식(수학식) 자체는 저작권 대상이 아니므로 **자체 구현**이 원칙. 코드·YAML 데이터(직업 상수, 블루프린트)를 **복사/포팅할 경우** 배포물에 다음 고지를 포함:
  `Copyright (c) 2022 Bumju Kwak and other contributers` + MIT 허가 문구 전문 (`THIRD_PARTY_NOTICES` 등).
- maplescouter: 코드/응답 역공학·복제 금지. 운영진의 공개 설명만 인용.
- 나무위키(CC BY-NC-SA 2.0 KR) 문장을 그대로 옮길 경우 출처·비영리·동일조건 유의 → 수치만 사실로 사용.
- Nexon Open API: 30일 내 갱신 의무 등 이용약관 준수 (05 문서 참조).
