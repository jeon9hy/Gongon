"""기상청 체감온도 산출식 구현이 공식 발췌와 공개 검증값에 맞는지 검사한다."""

import json
import re
from pathlib import Path

import pytest

from engine.forecast.sensible import SENSIBLE, STULL, sensible_temperature_c, wet_bulb_c

SNAPSHOT = (
    Path(__file__).resolve().parents[3] / "rules" / "sources" / "kma_sensible_temperature.json"
)


def formula_numbers(prefix: str) -> list[float]:
    """발췌 원문에서 산출식 한 줄의 계수를 순서대로 꺼낸다(지수 ^2·^1/2·^3/2 제외)."""
    text = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["text"]
    line = next(t for t in text if t.startswith(prefix))
    line = re.sub(r"\^[\d/]+", "", line.split("=", 1)[1]).replace("–", "-")
    numbers = re.findall(r"(-?)\s*(\d+\.\d+)", line)
    return [float(sign + value) for sign, value in numbers]


def test_coefficients_match_official_formula() -> None:
    # 부호까지 비교한다. 코드는 빼는 항의 계수를 양수로 두고 식에서 뺀다(-0.0022Tw², ATAN(RH-c)).
    assert formula_numbers("- 체감온도") == [SENSIBLE[0], SENSIBLE[1], SENSIBLE[2], -SENSIBLE[3],
                                         SENSIBLE[4], SENSIBLE[5]]  # fmt: skip
    a, b, c, d, e, f = STULL
    assert formula_numbers("** Tw") == [a, b, -c, d, e, -f]  # ATAN(RH-c), 끝의 -f


def test_wet_bulb_matches_stull_published_example() -> None:
    # Stull(2011, J. Appl. Meteor. Climatol. 50:2267) 본문 예: 20°C·50% → 13.7°C.
    assert wet_bulb_c(20.0, 50.0) == pytest.approx(13.7, abs=0.05)


def test_more_humidity_feels_hotter_and_value_has_one_decimal() -> None:
    values = [sensible_temperature_c(33.0, rh) for rh in (40, 50, 60, 70)]

    assert values == sorted(values) and len(set(values)) == 4
    assert all(round(v, 1) == v for v in values)


@pytest.mark.parametrize("humidity", [-0.1, 100.1])
def test_humidity_out_of_range_is_rejected(humidity: float) -> None:
    with pytest.raises(ValueError):
        sensible_temperature_c(30.0, humidity)
