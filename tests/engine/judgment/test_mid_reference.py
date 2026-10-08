"""중기예보 참고 단계(D-042): 기준과 비교할 수 없으므로 '진행'·'중지 검토'를 내지 않는다."""

import pytest

from engine.judgment import Condition, Element, MidPart, RuleSet, Verdict, mid_reference


def rule_set(*elements: Element) -> RuleSet:
    return RuleSet(
        work_type="test",
        work_type_label="시험 공종",
        rule_version="t1",
        source="시험",
        source_verified=False,
        conditions=tuple(
            Condition(f"c{i}", e, ">=", 1.0, Verdict.STOP_REVIEW, True, None)
            for i, e in enumerate(elements)
        ),
    )


RAIN_WIND = rule_set(Element.PRECIPITATION_MM_PER_H, Element.WIND_SPEED_MPS)
WIND_ONLY = rule_set(Element.WIND_SPEED_MPS)
SNOW = rule_set(Element.SNOWFALL_CM_PER_H)


@pytest.mark.parametrize(
    ("rules", "weather", "verdict"),
    [
        (RAIN_WIND, "흐리고 비", Verdict.CHECK),
        (RAIN_WIND, "구름많고 소나기", Verdict.CHECK),
        (RAIN_WIND, "흐리고 비/눈", Verdict.CHECK),
        (RAIN_WIND, "맑음", Verdict.UNAVAILABLE),  # 맑아도 풍속을 모르니 '진행'이 아니다
        (RAIN_WIND, "구름많고 눈", Verdict.UNAVAILABLE),  # 적설 기준이 없는 공종
        (WIND_ONLY, "흐리고 비", Verdict.UNAVAILABLE),  # 강우 기준이 없는 공종
        (SNOW, "구름많고 눈", Verdict.CHECK),
        (SNOW, "흐리고 비", Verdict.UNAVAILABLE),
    ],
)
def test_phenomenon_matching_rule_elements(rules: RuleSet, weather: str, verdict: Verdict) -> None:
    result, reason = mid_reference(
        rules, [MidPart("오후", 60, weather), MidPart("오전", 10, "맑음")]
    )

    assert result is verdict
    assert "오후 " + weather + " 60%" in reason


def test_high_probability_alone_is_not_a_threshold() -> None:
    # 강수확률에 임의 기준을 두지 않는다. 문구에 현상이 없으면 확인 필요로 올리지 않는다.
    result, _ = mid_reference(RAIN_WIND, [MidPart("오전", 90, "흐림")])

    assert result is Verdict.UNAVAILABLE


def test_missing_parts_are_unavailable() -> None:
    result, reason = mid_reference(RAIN_WIND, [])

    assert result is Verdict.UNAVAILABLE
    assert "중기예보 없음" in reason
