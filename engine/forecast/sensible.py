"""기온·상대습도 → 기상청 여름철 체감온도.

산출식 출처: 기상청 기상자료개방포털 '체감온도' 자료설명(2022.6.2. 변경 산출식),
발췌 rules/sources/kma_sensible_temperature.json. 습구온도는 Stull(2011) 추정식.
안전보건규칙 별표 13의2 제2호는 측정이 곤란하면 기상청장이 발표하는 체감온도로 정할 수 있게 한다.
"""

from math import atan, sqrt

# 산출식의 계수(발췌 원문과 같은지 tests/engine/forecast/test_sensible.py가 검사한다).
STULL = (0.151977, 8.313659, 1.67633, 0.00391838, 0.023101, 4.686035)
SENSIBLE = (-0.2442, 0.55399, 0.45535, 0.0022, 0.00278, 3.0)


def wet_bulb_c(temperature_c: float, humidity_pct: float) -> float:
    ta, rh = temperature_c, humidity_pct
    a, b, c, d, e, f = STULL
    return (
        ta * atan(a * sqrt(rh + b))
        + atan(ta + rh)
        - atan(rh - c)
        + d * rh * sqrt(rh) * atan(e * rh)
        - f
    )


def sensible_temperature_c(temperature_c: float, humidity_pct: float) -> float:
    """소수 첫째 자리로 반올림한다. 화면에 보이는 값과 기준 비교에 쓰는 값을 같게 하기 위해서다."""
    if not 0 <= humidity_pct <= 100:
        raise ValueError(f"상대습도 범위 밖: {humidity_pct}")
    ta, tw = temperature_c, wet_bulb_c(temperature_c, humidity_pct)
    k0, k1, k2, k3, k4, k5 = SENSIBLE
    return round(k0 + k1 * tw + k2 * ta - k3 * tw**2 + k4 * tw * ta + k5, 1)
