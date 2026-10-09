"""공온지수: 그날 작업이 기상 기준에 걸리지 않는 정도(0~100, D-050·D-052).

규칙 기반·결정적이며 판정을 대신하지 않는다(docs/brand.md §4).
기상청은 예보마다 신뢰도를 주지 않으므로, 받은 예보에서 근거를 댈 수 있는 것만 쓴다.

v2 계산(시각마다 점수 → 평균 → 그날 감점·상한):
- 시각 점수: 진행 100, 확인 필요 50, 중지 검토 0. 판정 불가 시각(예보 값 없음)은 넣지 않는다.
- 진행이어도 아슬아슬하면 낮춘다.
  · 기준 여유: 예보값이 기준까지 10% 이내면 70, 20% 이내면 85.
  · 강수확률(비 기준이 있는 작업만): 60% 이상이면 70, 30% 이상이면 85까지.
- 예보 안정성: 직전 발표 예보와 비교해 판정이 바뀐 작업이 있으면 그날 10점을 뺀다.
- 상한: 그날 나온 단계마다 상한을 두고 가장 낮은 것을 쓴다(확인 필요 70, 중지 검토 30).
  '판정 불가'가 '확인 필요'보다 높은 단계라도 확인 필요 상한은 그대로 적용된다.
비교한 시각이 하나도 없으면 점수를 내지 않는다.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from engine.judgment.types import Verdict

GONGON_INDEX_VERSION = "gongon-index-v2"

_HOUR_POINTS = {Verdict.GO: 100, Verdict.CHECK: 50, Verdict.STOP_REVIEW: 0}
_CAP_BY_VERDICT = {Verdict.STOP_REVIEW: 30, Verdict.CHECK: 70}
# (여유 % 미만, 그때 진행 시각 점수). 앞에서부터 처음 맞는 것을 쓴다.
_MARGIN_STEPS = ((10.0, 70), (20.0, 85))
# (강수확률 % 이상, 그때 진행 시각 점수 상한)
_RAIN_STEPS = ((60, 70), (30, 85))
CHANGED_PENALTY = 10


@dataclass(frozen=True, slots=True)
class HourInput:
    """한 작업의 한 시각."""

    verdict: Verdict
    margin_pct: float | None = None  # 가장 가까운 기준까지 남은 여유(기준 대비 %). 모르면 None
    rain_probability_pct: int | None = None  # 비 기준이 있는 작업만. 없으면 None


@dataclass(frozen=True, slots=True)
class GongonIndex:
    score: int  # 0~100
    compared_hours: int  # 점수에 넣은 시각 수(작업별 시각을 모두 센다)
    total_hours: int  # 판정 불가 시각을 포함한 전체 시각 수
    capped_by: Verdict | None  # 상한을 적용한 단계(없으면 None)
    near_threshold_hours: int = 0  # 기준 여유 20% 미만으로 낮춘 진행 시각
    rainy_hours: int = 0  # 강수확률 30% 이상으로 낮춘 진행 시각
    changed: bool = False  # 직전 예보와 판정이 바뀐 작업이 있어 감점했다
    version: str = GONGON_INDEX_VERSION

    @property
    def partial(self) -> bool:
        """일부 시각만 비교했다(3시간 간격 예보 등)."""
        return self.compared_hours < self.total_hours


def margin_pct(
    lower: float | None, upper: float | None, threshold: float, operator: str
) -> float | None:
    """예보값이 기준까지 얼마나 남았는지(기준 크기 대비 %). 넘었으면 0 이하. 계산할 수 없으면 None.

    '이상·초과' 기준은 값의 위쪽 끝, '이하·미만' 기준은 아래쪽 끝으로 본다(보수적으로).
    """
    if threshold == 0:
        return None
    if operator in (">=", ">"):
        return None if upper is None else (threshold - upper) / abs(threshold) * 100
    if operator in ("<=", "<"):
        return None if lower is None else (lower - threshold) / abs(threshold) * 100
    return None


def _hour_points(hour: HourInput) -> tuple[int, bool, bool]:
    """(점수, 기준 여유로 낮췄나, 강수확률로 낮췄나)."""
    points = _HOUR_POINTS[hour.verdict]
    if hour.verdict is not Verdict.GO:
        return points, False, False
    near = rainy = False
    if hour.margin_pct is not None:
        for limit, value in _MARGIN_STEPS:
            if hour.margin_pct < limit:
                points, near = value, True
                break
    if hour.rain_probability_pct is not None:
        for at_least, value in _RAIN_STEPS:
            if hour.rain_probability_pct >= at_least:
                if value < points:
                    points, rainy = value, True
                break
    return points, near, rainy


def gongon_index(
    hours: Sequence[HourInput], day_verdicts: Iterable[Verdict], changed: bool = False
) -> GongonIndex | None:
    """hours: 그날 판정한 작업들의 시각, day_verdicts: 그날 작업 칸들의 단계,
    changed: 직전 발표 예보로 낸 판정과 단계가 달라진 작업이 있는가."""
    scored = [_hour_points(h) for h in hours if h.verdict in _HOUR_POINTS]
    if not scored:
        return None
    points = [p for p, _, _ in scored]
    # 반올림 방향이 실행 환경에 따라 달라지지 않게 정수로 계산한다(0.5는 올림).
    score = (sum(points) * 2 + len(points)) // (len(points) * 2)
    if changed:
        score = max(0, score - CHANGED_PENALTY)
    caps = [(_CAP_BY_VERDICT[v], v) for v in set(day_verdicts) if v in _CAP_BY_VERDICT]
    capped_by = None
    if caps:
        cap, verdict = min(caps)
        if score > cap:
            score, capped_by = cap, verdict
    return GongonIndex(
        score=score,
        compared_hours=len(scored),
        total_hours=len(hours),
        capped_by=capped_by,
        near_threshold_hours=sum(1 for _, near, _ in scored if near),
        rainy_hours=sum(1 for _, _, rainy in scored if rainy),
        changed=changed,
    )
