"""잠재능력 / 에디셔널 메소 재설정 엔진.

- 등급 상승: 단계별 절단 기하분포 (천장 N회째 보장). E[T] = (1 - (1-p)^N) / p
- 옵션 목표: 공식 확률표의 3줄을 열거(줄 개수 제한 재정규화 포함)해 1회 성공 확률 q 계산
- 분포: 몬테카를로
근거: docs/research/04_potential_additional_options.md §2, §6
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

import numpy as np
import yaml

from app.paths import GAME_DATA_DIR

Kind = Literal["potential", "additional"]
GRADES = ["rare", "epic", "unique", "legendary"]
GRADE_NAMES = {"rare": "레어", "epic": "에픽", "unique": "유니크", "legendary": "레전드리"}


@lru_cache(maxsize=1)
def load_config() -> dict:
    with open(GAME_DATA_DIR / "potential.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_option_tables() -> dict:
    path = GAME_DATA_DIR / "potential_options.json"
    if not path.exists():
        return {"tables": {}}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_jobs() -> dict:
    with open(GAME_DATA_DIR / "jobs.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------- 옵션 파싱

_STAT = r"(STR|DEX|INT|LUK)"
_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(rf"^{_STAT} \+(\d+)%$"), "{0}%"),
    (re.compile(r"^올스탯 \+(\d+)%$"), "ALL%"),
    (re.compile(r"^최대 (HP|MP) \+(\d+)%$"), "{0}%"),
    (re.compile(r"^공격력 \+(\d+)%$"), "ATT%"),
    (re.compile(r"^마력 \+(\d+)%$"), "MATT%"),
    (re.compile(r"^공격력 \+(\d+)$"), "ATT"),
    (re.compile(r"^마력 \+(\d+)$"), "MATT"),
    (re.compile(rf"^{_STAT} \+(\d+)$"), "{0}"),
    (re.compile(r"^올스탯 \+(\d+)$"), "ALL"),
    (re.compile(rf"^캐릭터 기준 9레벨 당 {_STAT} \+(\d+)$"), "{0}/9LV"),
    (re.compile(r"^크리티컬 확률 \+(\d+)%$"), "CRIT_RATE"),
    (re.compile(r"^크리티컬 데미지 \+(\d+)%$"), "CRIT_DMG"),
    (re.compile(r"^보스 몬스터 (?:공격 시 )?데미지 \+(\d+)%$"), "BOSS%"),
    (re.compile(r"^몬스터 방어율 무시 \+(\d+)%$"), "IED%"),
    (re.compile(r"^데미지 \+(\d+)%$"), "DMG%"),
    (re.compile(r"재사용 대기시간 -(\d+)초"), "CDR"),
    (re.compile(r"^메소 획득량 \+(\d+)%$"), "MESO%"),
    (re.compile(r"^아이템 드롭률 \+(\d+)%$"), "DROP%"),
]


def parse_option(text: str) -> tuple[str, float]:
    for pat, key in _PATTERNS:
        m = pat.search(text)
        if m:
            groups = m.groups()
            return key.format(*groups[:-1]), float(groups[-1])
    return "OTHER", 0.0


# ---------------------------------------------------------------- 등급 상승


def cost_per_attempt(kind: Kind, level: int, grade: str) -> int:
    rows = load_config()["methods"][kind]["cost"]
    row = rows[0]
    for r in rows:
        if level >= r["min_level"]:
            row = r
    return row[grade]


@dataclass
class GradeStage:
    grade: str  # 현재 등급 (이 등급에서 다음 등급으로)
    p: float
    pity: int  # 남은 천장 횟수
    cost: int
    expected_attempts: float


def grade_stages(kind: Kind, level: int, current: str, target: str,
                 pity_used: dict[str, int] | None = None, miracle: bool = False) -> list[GradeStage]:
    cfg = load_config()
    m = cfg["methods"][kind]
    pity_used = pity_used or {}
    stages = []
    for g in GRADES[GRADES.index(current):GRADES.index(target)]:
        p = m["grade_up"][g] * (cfg["miracle_time_multiplier"] if miracle else 1)
        n = max(1, m["pity"][g] - pity_used.get(g, 0))
        e = (1 - (1 - p) ** n) / p
        stages.append(GradeStage(g, p, n, cost_per_attempt(kind, level, g), e))
    return stages


# ---------------------------------------------------------------- 옵션 목표


@dataclass
class Condition:
    """keys 의 값 합(sum) 또는 해당 줄 수(count)가 min 이상."""
    keys: list[str]
    min: float
    mode: Literal["sum", "count"] = "sum"


def _table_key(kind: Kind, grade: str, part: str, level: int) -> str:
    tables = load_option_tables()["tables"]
    levels = sorted({int(k.rsplit("/", 1)[1]) for k in tables if k.startswith(f"{kind}/{grade}/{part}/")})
    if not levels:
        raise KeyError(f"옵션 확률표 없음: {kind}/{grade}/{part} (scripts/fetch_potential_tables.py 실행 필요)")
    chosen = max([lv for lv in levels if lv <= level], default=levels[0])
    return f"{kind}/{grade}/{part}/{chosen}"


@dataclass
class _Bucket:
    key: str
    value: float
    group: int  # 줄 제한 그룹 인덱스 (-1 = 없음)
    prob: float


def _buckets(lines: list[list[dict]]) -> list[list[_Bucket]]:
    limits = load_config()["line_limits"]
    out = []
    for line in lines:
        agg: dict[tuple, float] = defaultdict(float)
        for row in line:
            key, val = parse_option(row["option"])
            group = next((i for i, lim in enumerate(limits) if re.search(lim["pattern"], row["option"])), -1)
            agg[(key, val, group)] += row["prob"]
        out.append([_Bucket(k, v, g, p) for (k, v, g), p in agg.items()])
    return out


def _satisfies(opts: tuple[_Bucket, ...], conditions: list[Condition]) -> bool:
    for c in conditions:
        if c.mode == "count":
            total = sum(1 for o in opts if o.key in c.keys)
        else:
            total = sum(o.value for o in opts if o.key in c.keys)
        if total < c.min - 1e-9:
            return False
    return True


def option_probability(kind: Kind, part: str, level: int, conditions: list[Condition],
                       grade: str = "legendary", fixed_first: str | None = None) -> float:
    """1회 재설정 결과가 조건을 모두 만족할 확률. fixed_first 는 프라임 큐브(첫 줄 고정)용 옵션 텍스트."""
    lines = load_option_tables()["tables"][_table_key(kind, grade, part, level)]
    b1, b2, b3 = _buckets(lines)
    limits = load_config()["line_limits"]

    if fixed_first is not None:
        key, val = parse_option(fixed_first)
        group = next((i for i, lim in enumerate(limits) if re.search(lim["pattern"], fixed_first)), -1)
        b1 = [_Bucket(key, val, group, 1.0)]

    def renorm(bs: list[_Bucket], used: list[int]) -> list[tuple[_Bucket, float]]:
        blocked = {g for g in set(used) if g >= 0 and used.count(g) >= limits[g]["max"]}
        if not blocked:
            return [(b, b.prob) for b in bs]
        excluded = sum(b.prob for b in bs if b.group in blocked)
        return [(b, b.prob / (1 - excluded)) for b in bs if b.group not in blocked]

    q = 0.0
    for o1 in b1:
        for o2, p2 in renorm(b2, [o1.group]):
            p12 = o1.prob * p2
            for o3, p3 in renorm(b3, [o1.group, o2.group]):
                if _satisfies((o1, o2, o3), conditions):
                    q += p12 * p3
    return q


# ---------------------------------------------------------------- 프리셋


def presets(job: str, part: str, kind: Kind, level: int) -> list[dict]:
    """직업·부위·종류별 대표 목표. 반환: [{id, label, conditions}]"""
    j = load_jobs()["jobs"][job]
    main = f"{j['main_stat']}%"
    att = "ATT%" if j["attack"] == "ATT" else "MATT%"
    att_flat = "ATT" if j["attack"] == "ATT" else "MATT"
    att_name = "공격력" if j["attack"] == "ATT" else "마력"
    bump = 1 if level >= 250 else 0  # 250제는 수치 +1%p
    weaponish = part in ("weapon", "secondary", "force_shield", "shield", "emblem")
    out: list[dict] = []

    def add(pid: str, label: str, conds: list[Condition]):
        out.append({"id": pid, "label": label, "conditions": conds})

    if kind == "potential":
        if weaponish:
            add("att2", f"{att_name}% 2줄+", [Condition([att], 2, "count")])
            add("att3", f"{att_name}% 3줄", [Condition([att], 3, "count")])
            if part != "emblem":
                add("att_boss3", f"{att_name}%/보공 3유효", [Condition([att, "BOSS%"], 3, "count")])
            add("att_ied3", f"{att_name}%/방무 3유효", [Condition([att, "IED%"], 3, "count")])
        else:
            for total in (21, 24, 27, 30, 33):
                t = total + bump * 3
                add(f"main{t}", f"주스탯 {t}%+", [Condition([main, "ALL%"], t)])
            if part == "gloves":
                add("cd1", "크뎀 1줄+", [Condition(["CRIT_DMG"], 1, "count")])
                add("cd2", "크뎀 2줄+", [Condition(["CRIT_DMG"], 2, "count")])
            if part == "hat":
                add("cdr2", "쿨감 -2초+", [Condition(["CDR"], 2)])
                add("cdr4", "쿨감 -4초+", [Condition(["CDR"], 4)])
            if part in ("ring", "pendant", "earring", "face", "eye"):
                add("drop_meso2", "드메 2줄+", [Condition(["MESO%", "DROP%"], 2, "count")])
    else:  # additional
        if weaponish:
            add("a_att1", f"에디 {att_name}% 1줄+", [Condition([att], 1, "count")])
            add("a_att2", f"에디 {att_name}% 2줄+", [Condition([att], 2, "count")])
        else:
            add("a_flat1", f"에디 {att_name} +n 1줄+", [Condition([att_flat], 1, "count")])
            add("a_main", f"에디 주스탯% 합 {12 + bump * 3}+", [Condition([main, "ALL%"], 12 + bump * 3)])
            if part == "gloves":
                add("a_cd", "에디 크뎀 1줄+", [Condition(["CRIT_DMG"], 1, "count")])
    return out


# ---------------------------------------------------------------- 통합 계산


@dataclass
class PotentialResult:
    stages: list[GradeStage]
    grade_up_expected_meso: float
    option_prob: float | None
    option_expected_attempts: float | None
    option_expected_meso: float | None
    expected_total_meso: float
    percentiles: dict[str, float]
    histogram: list[dict] = field(default_factory=list)
    samples: np.ndarray | None = field(default=None, repr=False)


PCTS = (50, 75, 90, 95, 99)


def calculate(kind: Kind, part: str, level: int, current: str, target_grade: str = "legendary",
              conditions: list[Condition] | None = None, pity_used: dict[str, int] | None = None,
              miracle: bool = False, trials: int = 200_000, seed: int | None = None,
              bins: int = 40) -> PotentialResult:
    stages = grade_stages(kind, level, current, target_grade, pity_used, miracle)
    gu_meso = sum(s.expected_attempts * s.cost for s in stages)

    q = option_probability(kind, part, level, conditions, target_grade) if conditions else None
    opt_cost = cost_per_attempt(kind, level, target_grade)
    if q is not None and q <= 0:
        raise ValueError("목표 옵션이 이 부위/등급에서 나올 수 없습니다")

    rng = np.random.default_rng(seed)
    total = np.zeros(trials)
    for s in stages:
        total += np.minimum(rng.geometric(s.p, trials), s.pity) * s.cost
    if q is not None:
        total += rng.geometric(q, trials) * opt_cost

    hi = float(np.percentile(total, 99))
    lo = float(total.min())
    counts, edges = np.histogram(np.clip(total, lo, hi), bins=bins, range=(lo, max(hi, lo + 1)))

    return PotentialResult(
        stages=stages,
        grade_up_expected_meso=gu_meso,
        option_prob=q,
        option_expected_attempts=(1 / q) if q else None,
        option_expected_meso=(opt_cost / q) if q else None,
        expected_total_meso=gu_meso + ((opt_cost / q) if q else 0.0),
        percentiles={f"p{p}": float(v) for p, v in zip(PCTS, np.percentile(total, PCTS))},
        histogram=[{"lo": float(edges[i]), "hi": float(edges[i + 1]), "count": int(c)} for i, c in enumerate(counts)],
        samples=total,
    )


def attempts_for_confidence(q: float, confidence: float) -> int:
    """확률 confidence 로 성공하기 위한 시도 횟수."""
    return math.ceil(math.log(1 - confidence) / math.log(1 - q))
