"""판정 화면용 조회. 지금은 예시 데이터를 읽고, S04-4에서 저장된 판정 내역 조회로 바꾼다."""

from urllib.parse import urlencode

from app.features.judgments import sample
from app.features.judgments.schemas import (
    Bar,
    DashboardView,
    DetailView,
    Element,
    FilterLink,
    HistoryView,
    Tab,
    VerdictFilter,
)
from engine.geo import latlon_to_kma_grid

_PLOT_HEIGHT_PX = 200
_MIN_BAR_PX = 6
_SAMPLE_SITE_LATITUDE_DEG = 37.5665  # 예시 현장(○○현장) 위치
_SAMPLE_SITE_LONGITUDE_DEG = 126.9780

VERDICT_FILTERS: tuple[VerdictFilter, ...] = ("전체", "진행", "확인 필요", "중지 검토", "판정 불가")
ALL_SITES = "전체"


def _sample_grid_text() -> str:
    grid = latlon_to_kma_grid(_SAMPLE_SITE_LATITUDE_DEG, _SAMPLE_SITE_LONGITUDE_DEG)
    return f"({grid.nx}, {grid.ny})"


def _dashboard_href(element: Element, hour: int) -> str:
    return "/?" + urlencode({"element": element, "hour": hour})


def build_dashboard(element: Element, selected_hour: int) -> DashboardView:
    series = sample.SERIES[element]
    values = dict(zip(sample.HOURS, series.hourly_values, strict=True))
    if selected_hour not in values:
        raise ValueError(f"예시 데이터에 없는 시각: {selected_hour}")

    bars = tuple(
        Bar(
            hour_label=f"{hour:02d}",
            height_px=max(_MIN_BAR_PX, round(values[hour] / series.axis_max * _PLOT_HEIGHT_PX)),
            tip=f"{values[hour]:.1f} {series.unit}",
            aria_label=(
                f"{hour:02d}:00 {series.label} {values[hour]:.1f} {series.unit}"
                + (", 기준 이상" if hour in series.over_hours else "")
            ),
            over=hour in series.over_hours,
            selected=hour == selected_hour,
            href=_dashboard_href(element, hour),
        )
        for hour in sample.HOURS
    )
    tabs = tuple(
        Tab(s.label, _dashboard_href(key, selected_hour), key == element)
        for key, s in sample.SERIES.items()
    )
    threshold_text = f"{series.threshold:.1f} {series.unit}"
    return DashboardView(
        site_name=sample.SITE_NAME,
        target_date=sample.TARGET_DATE,
        work_hours=sample.WORK_HOURS,
        forecast_issued=sample.FORECAST_ISSUED,
        rule_version=sample.RULE_VERSION,
        work_verdicts=sample.WORK_VERDICTS,
        windows=sample.WINDOWS,
        tiles=sample.TILES,
        tabs=tabs,
        bars=bars,
        selected_value=f"{values[selected_hour]:.1f} {series.unit}",
        selected_caption=(
            f"{selected_hour:02d}:00 {series.label} 예보 · 기준 {threshold_text} 이상이면 중지 검토"
        ),
        threshold_bottom_px=round(series.threshold / series.axis_max * _PLOT_HEIGHT_PX),
        threshold_text=threshold_text,
        collection_status="성공 · 10/4 14:12",
        judged_at="10/4 14:13",
        grid=_sample_grid_text(),
        notice_title=sample.NOTICE_TITLE,
        notice_items=sample.NOTICE_ITEMS,
        notice_disclaimer=sample.NOTICE_DISCLAIMER,
    )


def get_detail(judgment_id: int) -> DetailView | None:
    if judgment_id != sample.DETAIL_JUDGMENT_ID:
        return None
    grid = _sample_grid_text()
    return DetailView(
        site_name=sample.SITE_NAME,
        target_date="10월 5일(월)",
        work_range="13:00–17:00",
        verdict="중지 검토",
        chips=tuple(chip.format(grid=grid) for chip in sample.DETAIL_CHIPS),
        criteria=sample.CRITERIA,
        rows=sample.HOUR_ROWS,
    )


def build_history(verdict: VerdictFilter, site_name: str) -> HistoryView:
    in_site = [r for r in sample.HISTORY if site_name == ALL_SITES or r.site_name == site_name]
    rows = tuple(r for r in in_site if verdict == "전체" or r.verdict == verdict)
    filters = tuple(
        FilterLink(
            label=label,
            count=sum(1 for r in in_site if label == "전체" or r.verdict == label),
            href="/judgments?" + urlencode({"verdict": label, "site": site_name}),
            selected=label == verdict,
        )
        for label in VERDICT_FILTERS
    )
    site_options = (ALL_SITES, *dict.fromkeys(r.site_name for r in sample.HISTORY))
    return HistoryView(
        rows=rows,
        filters=filters,
        site_options=site_options,
        selected_site=site_name,
        selected_verdict=verdict,
    )
