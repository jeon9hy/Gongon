"""중기예보 참고 단계(D-042).

기준값과 비교할 수 없으므로 '확인 필요'보다 높이지 않고 '진행'도 내지 않는다.

중기예보는 하루 오전·오후의 강수확률(%)과 날씨 문구만 준다. 문구의 현상(비·눈·비/눈·소나기,
활용가이드 '날씨예보 종류')이 공종 기준의 강우·적설 조건과 관련되면 '확인 필요', 그 밖에는
'판정 불가'다. 강수확률에 임의 기준(예: 60% 이상)을 두지 않고 숫자 그대로 보여 준다.
오전·오후의 시간 범위는 활용가이드에 정의가 없어,
그날 어느 쪽이든 현상이 있으면 그날 전체에 적용한다.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from engine.judgment.types import Element, RuleSet, Verdict

_RAIN_WORDS = ("비", "소나기")
_SNOW_WORDS = ("눈",)


@dataclass(frozen=True, slots=True)
class MidPart:
    label: str  # 오전 | 오후 | 하루
    rain_probability_pct: int | None
    weather: str | None


def mid_reference(rule_set: RuleSet, parts: Sequence[MidPart]) -> tuple[Verdict, str]:
    """(단계, 사유). parts가 비면 판정 불가."""
    summary = " · ".join(_part_text(p) for p in parts) or "중기예보 없음"
    elements = {c.element for c in rule_set.conditions}
    related = []
    if Element.PRECIPITATION_MM_PER_H in elements:
        related += [p for p in parts if _has(p.weather, _RAIN_WORDS)]
    if Element.SNOWFALL_CM_PER_H in elements:
        related += [p for p in parts if _has(p.weather, _SNOW_WORDS)]
    if related:
        return (
            Verdict.CHECK,
            f"중기예보 {summary} → 강수 현상 예보 · 강우량·풍속 없음, 단기예보 나오면 다시 판정",
        )
    return (
        Verdict.UNAVAILABLE,
        f"중기예보 {summary} → 기준과 직접 비교할 값 없음(풍속·강우량 미제공)",
    )


def _has(weather: str | None, words: tuple[str, ...]) -> bool:
    return weather is not None and any(word in weather for word in words)


def _part_text(part: MidPart) -> str:
    pct = "" if part.rain_probability_pct is None else f" {part.rain_probability_pct}%"
    return f"{part.label} {part.weather or '날씨 없음'}{pct}"
