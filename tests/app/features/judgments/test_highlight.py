"""상세 표·그래프의 '기준 해당 값' 강조가 높은 쪽·낮은 쪽 기준을 모두 맞게 판단하는지."""

from typing import Any

import pytest

from app.features.judgments.service import _element_meets
from engine.judgment import Element

MEAN = Element.DAILY_MEAN_TEMPERATURE_C


def hour(value: float, *conditions: tuple[str, float]) -> dict[str, Any]:
    return {
        "conditions": [
            {"element": MEAN.value, "operator": op, "threshold": t, "lower": value, "upper": value}
            for op, t in conditions
        ]
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [(18.6, False), (25.0, False), (25.1, True), (4.0, True), (4.1, False)],
)
def test_high_and_low_thresholds_on_same_element(value: float, expected: bool) -> None:
    # 콘크리트 일평균기온: 25 초과(서중) / 4 이하(한중)
    assert _element_meets(hour(value, (">", 25.0), ("<=", 4.0)), MEAN) is expected


def test_strictly_below_does_not_highlight_equal_value() -> None:
    assert _element_meets(hour(5.0, ("<", 5.0)), MEAN) is False
    assert _element_meets(hour(4.9, ("<", 5.0)), MEAN) is True
