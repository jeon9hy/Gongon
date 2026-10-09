"""공온지수 v2(D-052): 시각 점수 평균, 기준 여유·강수확률로 낮춤, 예보 변경 감점, 단계 상한."""

import pytest

from engine.judgment.index import HourInput, gongon_index, margin_pct
from engine.judgment.types import Verdict

GO, CHECK, STOP, NA = Verdict.GO, Verdict.CHECK, Verdict.STOP_REVIEW, Verdict.UNAVAILABLE


def hours(*verdicts: Verdict) -> list[HourInput]:
    return [HourInput(v) for v in verdicts]


def test_all_go_with_room_is_100() -> None:
    index = gongon_index([HourInput(GO, margin_pct=50, rain_probability_pct=0)] * 10, [GO])

    assert index is not None and index.score == 100 and not index.partial


def test_unavailable_hours_are_left_out_not_counted_as_go() -> None:
    index = gongon_index(hours(NA, NA, GO, NA, NA, GO, NA, NA, CHECK, NA), [CHECK, NA])

    assert index is not None
    assert (index.compared_hours, index.total_hours) == (3, 10) and index.partial
    assert index.score == 70  # (100+100+50)/3 = 83.3 → '확인 필요' 상한 70


def test_no_comparable_hour_gives_no_score() -> None:
    assert gongon_index(hours(NA, NA), [NA]) is None
    assert gongon_index([], [CHECK]) is None  # 기준 미확인 공종만 있는 날


@pytest.mark.parametrize(
    ("margin", "points"),
    [(9.9, 70), (10.0, 85), (19.9, 85), (20.0, 100), (None, 100)],  # 미만 경계
)
def test_go_hour_near_the_threshold_is_lowered(margin: float | None, points: int) -> None:
    index = gongon_index([HourInput(GO, margin_pct=margin)], [GO])

    assert index is not None and index.score == points
    assert index.near_threshold_hours == (1 if points < 100 else 0)


@pytest.mark.parametrize(
    ("pop", "points"),
    [(29, 100), (30, 85), (59, 85), (60, 70), (None, 100)],  # 이상 경계
)
def test_rain_probability_lowers_go_hours_of_rain_sensitive_work(
    pop: int | None, points: int
) -> None:
    index = gongon_index([HourInput(GO, rain_probability_pct=pop)], [GO])

    assert index is not None and index.score == points


def test_lowest_of_margin_and_rain_applies_once() -> None:
    # 기준 여유 15%(85)와 강수확률 70%(70) → 70. 둘을 곱하거나 두 번 빼지 않는다.
    index = gongon_index([HourInput(GO, margin_pct=15, rain_probability_pct=70)], [GO])

    assert index is not None and index.score == 70
    assert (index.near_threshold_hours, index.rainy_hours) == (1, 1)


def test_margin_and_rain_do_not_touch_check_or_stop_hours() -> None:
    index = gongon_index([HourInput(CHECK, margin_pct=1, rain_probability_pct=90)], [CHECK])

    assert index is not None and index.score == 50


def test_changed_forecast_takes_ten_points_before_caps() -> None:
    plain = gongon_index(hours(GO, GO), [GO], changed=True)
    assert plain is not None and plain.score == 90
    # 95 → 변경 감점 85 → 확인 필요 상한 70
    index = gongon_index(hours(*[GO] * 9, CHECK), [CHECK], changed=True)
    assert index is not None and index.score == 70 and index.changed


@pytest.mark.parametrize(
    ("hour_list", "day", "score", "capped"),
    [
        (hours(*[GO] * 9, CHECK), [CHECK], 70, True),  # 95 → 상한 70
        (hours(*[GO] * 2, *[CHECK] * 8), [CHECK], 60, False),  # 상한 아래는 그대로
        (hours(*[GO] * 9, STOP), [STOP, CHECK], 30, True),  # 가장 낮은 상한
        (hours(*[STOP] * 10), [STOP], 0, False),
        (hours(*[GO] * 10), [CHECK], 70, True),  # 기준 미확인 작업이 있으면 상한
    ],
)
def test_score_never_contradicts_the_verdicts(
    hour_list: list[HourInput], day: list[Verdict], score: int, capped: bool
) -> None:
    index = gongon_index(hour_list, day)

    assert index is not None and index.score == score
    assert (index.capped_by is not None) is capped


def test_check_cap_applies_even_when_unavailable_is_the_highest_verdict() -> None:
    # 2026-10-08 개발 화면: 확인 필요 + 판정 불가 작업이 있는 날이 75점으로 나왔다(상한 누락).
    index = gongon_index(hours(GO, GO, CHECK, NA, NA), [CHECK, NA, GO])

    assert index is not None and index.score == 70 and index.capped_by == CHECK


def test_half_points_round_up_deterministically() -> None:
    index = gongon_index(hours(GO, CHECK, CHECK, CHECK), [GO])  # 62.5 → 63

    assert index is not None and index.score == 63


@pytest.mark.parametrize(
    ("lower", "upper", "threshold", "operator", "expected"),
    [
        (8.0, 9.0, 10.0, ">=", 10.0),  # 풍속 위쪽 끝 9 → 기준 10까지 10%
        (8.0, 10.0, 10.0, ">=", 0.0),  # 기준과 같음
        (8.0, 12.0, 10.0, ">", -20.0),  # 넘음
        (7.0, 9.0, 5.0, "<=", 40.0),  # 저온 기준 5 이하: 아래쪽 끝 7 → 40%
        (None, 9.0, 5.0, "<=", None),
        (1.0, 2.0, 0.0, ">=", None),  # 기준 0은 비율을 낼 수 없음
    ],
)
def test_margin_uses_the_conservative_end(
    lower: float | None, upper: float | None, threshold: float, operator: str,
    expected: float | None,
) -> None:  # fmt: skip
    assert margin_pct(lower, upper, threshold, operator) == expected
