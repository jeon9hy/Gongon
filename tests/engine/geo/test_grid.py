import json
import math
from pathlib import Path
from typing import Any

import pytest

from engine.geo import GridConversionError, KmaGrid, latlon_to_kma_grid


def test_projection_origin_maps_to_origin_grid() -> None:
    # 기준점(위도 38°, 경도 126°)은 정의상 격자 (43, 136)이다.
    assert latlon_to_kma_grid(38.0, 126.0) == KmaGrid(nx=43, ny=136)


_PUBLISHED_POINTS: list[dict[str, Any]] = json.loads(
    (Path(__file__).parent / "data/kma_grid_20260701.json").read_text(encoding="utf-8")
)["points"]


@pytest.mark.parametrize("point", _PUBLISHED_POINTS, ids=lambda p: str(p["administrative_code"]))
def test_coordinates_match_official_grid_table(point: dict[str, Any]) -> None:
    # 공식 2607 격자표의 F/G 기대값과 N/O 입력 좌표. 파일·해시·원본 행은 fixture에 기록.
    assert latlon_to_kma_grid(point["latitude_deg"], point["longitude_deg"]) == KmaGrid(
        nx=point["nx"], ny=point["ny"]
    )


@pytest.mark.parametrize(
    ("latitude_deg", "longitude_deg"),
    [
        (35.68, 139.69),  # 도쿄: 동쪽으로 격자 범위(nx ≤ 149) 밖
        (0.0, 126.0),  # 적도: 남쪽으로 ny 범위 밖
        (60.0, 126.0),  # 북쪽으로 ny 범위 밖
        (91.0, 126.0),  # 위도 범위 밖
        (37.5, 181.0),  # 경도 범위 밖
    ],
)
def test_out_of_range_coordinates_are_rejected(latitude_deg: float, longitude_deg: float) -> None:
    with pytest.raises(GridConversionError):
        latlon_to_kma_grid(latitude_deg, longitude_deg)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_coordinates_are_rejected(bad: float) -> None:
    with pytest.raises(GridConversionError):
        latlon_to_kma_grid(bad, 126.0)
    with pytest.raises(GridConversionError):
        latlon_to_kma_grid(37.5, bad)
