"""위경도 → 기상청 단기예보 격자(nx, ny) 변환.

기상청 동네예보 격자는 Lambert 정각원추도법(LCC) 5 km 격자다. 상수와 계산식은
기상청 동네예보 격자 변환 공식(DFS_XY_CONV)을 따른다.
"""

import math
from dataclasses import dataclass

# 지구 반경(km), 격자 간격(km), 표준 위도 2개(도), 기준점 경도·위도(도), 기준점의 격자 좌표
_EARTH_RADIUS_KM = 6371.00877
_GRID_KM = 5.0
_STANDARD_LAT1_DEG = 30.0
_STANDARD_LAT2_DEG = 60.0
_ORIGIN_LON_DEG = 126.0
_ORIGIN_LAT_DEG = 38.0
_ORIGIN_NX = 43
_ORIGIN_NY = 136

# 기상청 단기예보가 제공하는 격자 범위. 이 밖은 예보가 없으므로 거부한다.
NX_RANGE = (1, 149)
NY_RANGE = (1, 253)


@dataclass(frozen=True, slots=True)
class KmaGrid:
    nx: int
    ny: int


class GridConversionError(ValueError):
    """좌표가 올바르지 않거나 기상청 격자 범위 밖이다."""


def _build_projection() -> tuple[float, float, float]:
    re = _EARTH_RADIUS_KM / _GRID_KM
    slat1 = math.radians(_STANDARD_LAT1_DEG)
    slat2 = math.radians(_STANDARD_LAT2_DEG)
    olat = math.radians(_ORIGIN_LAT_DEG)

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = math.pow(sf, sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / math.pow(ro, sn)
    return sn, sf, ro


_SN, _SF, _RO = _build_projection()


def latlon_to_kma_grid(latitude_deg: float, longitude_deg: float) -> KmaGrid:
    """위도·경도(도, WGS84)를 기상청 격자로 바꾼다. 범위 밖·비정상 좌표는 GridConversionError."""
    if not (math.isfinite(latitude_deg) and math.isfinite(longitude_deg)):
        raise GridConversionError("위도·경도는 유한한 숫자여야 한다")
    if not (-90.0 < latitude_deg < 90.0 and -180.0 <= longitude_deg <= 180.0):
        raise GridConversionError(f"위도·경도 범위를 벗어났다: ({latitude_deg}, {longitude_deg})")

    re = _EARTH_RADIUS_KM / _GRID_KM
    ra = math.tan(math.pi * 0.25 + math.radians(latitude_deg) * 0.5)
    ra = re * _SF / math.pow(ra, _SN)

    theta = math.radians(longitude_deg - _ORIGIN_LON_DEG)
    # 경도 차이를 [-180, 180]로 맞춰 날짜 변경선 근처에서도 같은 식을 쓴다
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= _SN

    nx = math.floor(ra * math.sin(theta) + _ORIGIN_NX + 0.5)
    ny = math.floor(_RO - ra * math.cos(theta) + _ORIGIN_NY + 0.5)

    if not (NX_RANGE[0] <= nx <= NX_RANGE[1] and NY_RANGE[0] <= ny <= NY_RANGE[1]):
        raise GridConversionError(
            f"기상청 격자 범위 밖이다: ({latitude_deg}, {longitude_deg}) → ({nx}, {ny})"
        )
    return KmaGrid(nx=nx, ny=ny)
