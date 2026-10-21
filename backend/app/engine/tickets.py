"""이벤트 보상 아이템: 유니크 잠재능력 부여 주문서, 에픽 에디셔널 잠재능력 부여 주문서, 스타포스 17성 강화권.

보유하고 있으면(개수 > 0) 직작 기대 비용 계산에서
- 잠재 등급이 유니크 미만이면 유니크부터 시작
- 에디 등급이 에픽 미만이면 에픽부터 시작
- 17성 미만이고 장비 레벨이 강화권 사용 상한 이하면 17성부터 시작 (목표 17성 이상일 때만)
으로 본다. 아이템 자체 비용은 0 (이벤트로 받은 교환 불가 아이템 가정).
⚠ 강화권의 사용 가능 레벨은 이벤트마다 달라 설정값(star17_max_level)으로 둔다.
여러 부위가 같은 아이템을 동시에 쓰는 경우(보유 개수 초과)는 고려하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

GRADES = ("rare", "epic", "unique", "legendary")


def _rank(grade: str | None) -> int:
    return GRADES.index(grade) if grade in GRADES else 0


@dataclass(frozen=True)
class Tickets:
    unique_potential: int = 0
    epic_additional: int = 0
    star17: int = 0
    star17_max_level: int = 200

    def star_start(self, level: int, start: int, target: int) -> int:
        if self.star17 > 0 and start < 17 <= target and 0 < level <= self.star17_max_level:
            return 17
        return start

    def grade_start(self, kind: str, grade: str | None) -> str:
        grade = grade if grade in GRADES else "rare"
        if kind == "potential" and self.unique_potential > 0 and _rank(grade) < _rank("unique"):
            return "unique"
        if kind == "additional" and self.epic_additional > 0 and _rank(grade) < _rank("epic"):
            return "epic"
        return grade


def note(kind: str) -> str:
    return {"star17": "17성 강화권 사용 (17성부터)", "potential": "유니크 잠재 주문서 사용 (유니크부터)",
            "additional": "에픽 에디 주문서 사용 (에픽부터)"}[kind]
