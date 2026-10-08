"""판정 실행·저장과 화면 모델 만들기. 판정 계산은 engine/judgment.judge만 한다."""

import logging
from bisect import bisect_left
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.core.rules import judged_labels, rule_sets_by_label
from app.features.forecasts import service as forecasts_service
from app.features.judgments import repository
from app.features.judgments.models import Judgment
from app.features.judgments.schemas import (
    Bar,
    Cell,
    Chart,
    CountTile,
    CriterionCard,
    DashboardView,
    DetailView,
    ElementKey,
    FilterLink,
    HistoryRow,
    HistoryView,
    HomeView,
    HourRow,
    Notice,
    NoticeItem,
    PrimaryJudgment,
    RecentItem,
    RecentRun,
    RunResult,
    SiteOption,
    SiteSummary,
    Tab,
    Tile,
    VerdictFilter,
    WeekCell,
    WeekDay,
    WeekRow,
    WeekView,
    WorkCard,
    WorkOption,
    WorkWindow,
)
from app.features.schedules import service as schedules_service
from app.features.schedules.schemas import WorkItemRecord
from app.features.sites import service as sites_service
from app.features.sites.schemas import SiteRecord
from engine.forecast import (
    HttpGet,
    KmaAuth,
    MidHalfDay,
    land_region_for,
    next_base_at,
    with_daily_temperatures,
)
from engine.judgment import (
    ELEMENT_LABEL,
    ELEMENT_UNIT,
    OPERATOR_TEXT,
    Element,
    JudgmentResult,
    MidPart,
    RuleSet,
    Verdict,
    judge,
    mid_reference,
)
from engine.kst import KST

logger = logging.getLogger(__name__)

VERDICT_FILTERS: tuple[VerdictFilter, ...] = ("전체", "진행", "확인 필요", "중지 검토", "판정 불가")
HISTORY_PAGE_SIZE = 30
WEEK_DAYS = 7  # 주간 보기 범위(D-041). 예보가 없는 날은 판정하지 않는다
_WEEKDAYS = "월화수목금토일"
_PLOT_HEIGHT_PX = 200
_MIN_BAR_PX = 6
ELEMENT_KEYS: dict[ElementKey, Element] = {
    "rain": Element.PRECIPITATION_MM_PER_H,
    "wind": Element.WIND_SPEED_MPS,
    "snow": Element.SNOWFALL_CM_PER_H,
    "heat": Element.SENSIBLE_TEMPERATURE_C,
}
_KEY_OF = {element: key for key, element in ELEMENT_KEYS.items()}
_ICON = {
    Element.PRECIPITATION_MM_PER_H: "rain",
    Element.WIND_SPEED_MPS: "wind",
    Element.SNOWFALL_CM_PER_H: "snow",
    Element.SENSIBLE_TEMPERATURE_C: "thermometer",
    Element.DAILY_MEAN_TEMPERATURE_C: "thermometer",
    Element.MAX_TEMPERATURE_NEXT_24H_C: "thermometer",
}


# ---------- 실행 ----------


def target_date_for(now: datetime) -> date:
    """판정 대상은 내일(KST)."""
    return now.astimezone(KST).date() + timedelta(days=1)


def run_message(ran: RunResult, now: datetime) -> str:
    """결과 문구. 판정이 그대로면 다음 예보가 언제 반영되는지 덧붙인다."""
    if ran == "unchanged":
        return f"{RUN_MESSAGES[ran]} {next_forecast_text(now)}"
    return RUN_MESSAGES[ran]


def next_forecast_text(now: datetime) -> str:
    """예보는 3시간마다 발표되고 10분 뒤 제공된다. 같은 예보로 다시 판정하면 결과가 같다."""
    nxt = next_base_at(now)
    ready = nxt + timedelta(minutes=10)
    return f"다음 예보 {nxt:%H:%M} 발표 · {ready:%H:%M} 이후 반영"


# 판정 실행 결과 코드 → 대시보드 문구. URL에는 코드만 싣는다(임의 문구 표시 방지).
RUN_MESSAGES: dict[RunResult, str] = {
    "done": "판정했습니다.",
    "failed": "예보를 받지 못해 ‘판정 불가’로 기록했습니다. 데이터 상태에서 원인을 확인하세요.",
    "no_rules": "판정 기준이 있는 공종이 없습니다. 현장 설정에서 철골 작업을 고르세요.",
    "all_done": (
        "전체 현장을 판정했습니다. 작업 기간이 아니거나 판정 기준이 없는 현장은 건너뜁니다."
    ),
    "no_sites": "등록된 현장이 없습니다. 먼저 현장을 등록하세요.",
    "out_of_period": (
        "앞으로 7일은 작업 기간이 아니라 판정하지 않았습니다. 현장 설정에서 작업 기간을 확인하세요."
    ),
    "unchanged": "새로 발표된 예보가 없어 판정이 그대로입니다.",
    "beyond_forecast": (
        "앞으로 작업일이 아직 예보 범위 밖이라 판정하지 않았습니다. 예보가 나오면 판정하세요."
    ),
}


def horizon_dates(now: datetime) -> tuple[date, ...]:
    """주간 보기 날짜: 내일부터 WEEK_DAYS일(D-041)."""
    tomorrow = target_date_for(now)
    return tuple(tomorrow + timedelta(days=offset) for offset in range(WEEK_DAYS))


def run_for_site(
    session: Session,
    site_id: int,
    now: datetime,
    auth: KmaAuth,
    http_get: HttpGet,
    mid_service_key: str = "",
) -> RunResult | None:
    """현장의 내일부터 7일 판정을 내고 저장한다(D-041). 없는 현장이면 None.

    예보를 한 번 받아 그 예보에 값이 있는 날만 판정한다. 예보 범위 밖인 날은 저장하지 않는다.
    """
    site = sites_service.get_site(session, site_id)
    if site is None:
        return None
    rule_sets = rule_sets_by_label()
    dates = horizon_dates(now)
    if not any(_targets_for(site, (), rule_sets)):
        return "no_rules"
    working = [d for d in dates if site.works_on(d)]
    if not working:
        return "out_of_period"  # 작업하지 않는 날은 예보도 받지 않는다
    items_by_day = schedules_service.items_between(session, site.site_id, working[0], working[-1])
    snapshot = forecasts_service.get_forecast(
        session, site.grid_nx, site.grid_ny, now, auth, http_get
    )
    if snapshot.weather is None:
        # 실패는 가장 가까운 작업일에만 남긴다(같은 원인을 날짜마다 반복 기록하지 않음).
        day = working[0]
        for target in _targets_for(site, items_by_day.get(day, ()), rule_sets):
            start_at, end_at = _work_range(day, target)
            session.add(
                _failed_judgment(site, rule_sets[target.work_type], day, start_at, end_at,
                                 snapshot.run_id, f"예보 수집 실패: {snapshot.failure_reason}",
                                 target.item_id)
            )  # fmt: skip
        session.commit()
        return "failed"

    forecast_times = sorted(h.valid_at for h in snapshot.weather.hours)
    judged_days: list[date] = []
    stored = 0  # 새로 저장한 판정 수. 0이면 같은 예보로 이미 판정한 결과와 같다
    for day in working:
        if day != dates[0] and day not in items_by_day:
            continue  # 모레부터는 등록한 작업만 판정한다(현장 기본 공종 대체는 내일만, D-023)
        for target in _targets_for(site, items_by_day.get(day, ()), rule_sets):
            rule_set = rule_sets[target.work_type]
            start_at, end_at = _work_range(day, target)
            if not _has_forecast(forecast_times, start_at, end_at):
                continue  # 작업 시간에 예보 값이 하나도 없으면 판정하지 않는다(예보 범위 밖)
            if day not in judged_days:
                judged_days.append(day)
            # 일평균·종료 후 24시간 최고기온은 작업 시간마다 다르다(콘크리트, D-033).
            weather = with_daily_temperatures(snapshot.weather, start_at, end_at)
            result = judge(weather, rule_set, start_at, end_at)
            same = repository.find_same(
                session,
                site_id=site.site_id,
                target_date=day,
                work_type=rule_set.work_type_label,
                forecast_issued_at=result.forecast_issued_at,
                rule_version=rule_set.rule_version,
                grid_nx=site.grid_nx,
                grid_ny=site.grid_ny,
                work_start_at=start_at,
                work_end_at=end_at,
                work_item_id=target.item_id,
            )
            if same is None:
                stored += 1
                session.add(_judgment(site, rule_set, day, start_at, end_at,
                                      snapshot.run_id, result, target.item_id))  # fmt: skip
    region_id = land_region_for(site.address)
    if region_id is not None and any(d not in judged_days for d in working):
        # 단기예보 밖의 작업일은 중기예보를 참고로 보여 준다(D-042). 판정 내역에는 저장하지 않는다.
        forecasts_service.get_mid_forecast(session, region_id, now, mid_service_key, http_get)
    session.commit()
    if not judged_days:
        return "beyond_forecast"
    logger.info("판정 site_id=%s dates=%s base_at=%s", site.site_id, judged_days, snapshot.base_at)
    return "done" if stored else "unchanged"


def _has_forecast(times: list[datetime], start_at: datetime, end_at: datetime) -> bool:
    """작업 시간에 걸친 정시 예보가 하나라도 있는가(times는 정렬됨)."""
    first_slot = start_at.replace(minute=0, second=0, microsecond=0)
    index = bisect_left(times, first_slot)
    return index < len(times) and times[index] < end_at


def _targets_for(
    site: SiteRecord, items: tuple[WorkItemRecord, ...], rule_sets: Mapping[str, RuleSet]
) -> list["_Target"]:
    """판정할 수 있는(기준이 있는) 대상만."""
    return [t for t in _targets(site, items) if t.work_type in rule_sets]


def _work_range(day: date, target: "_Target") -> tuple[datetime, datetime]:
    return (
        datetime.combine(day, target.start_local, KST),
        datetime.combine(day, target.end_local, KST),
    )


def run_all(
    session: Session, now: datetime, auth: KmaAuth, http_get: HttpGet, mid_service_key: str = ""
) -> RunResult:
    """모든 현장의 7일 판정. 같은 격자는 예보를 한 번만 받는다(forecasts 재사용)."""
    results = [
        run_for_site(session, s.site_id, now, auth, http_get, mid_service_key)
        for s in sites_service.list_sites(session)
    ]
    if not results:
        return "no_sites"
    if "failed" in results:
        return "failed"
    if "done" in results:
        return "all_done"
    if "unchanged" in results:
        return "unchanged"
    for code in ("beyond_forecast", "out_of_period"):
        if code in results:
            return code
    return "no_rules"


def _judgment(
    site: SiteRecord,
    rule_set: RuleSet,
    target_date: date,
    start_at: datetime,
    end_at: datetime,
    run_id: int,
    result: JudgmentResult,
    work_item_id: int | None,
) -> Judgment:
    thresholds = {c.id: (c.threshold, c.operator) for c in rule_set.conditions}
    return Judgment(
        site_id=site.site_id,
        target_date=target_date,
        work_type=rule_set.work_type_label,
        work_start_at=start_at,
        work_end_at=end_at,
        work_item_id=work_item_id,
        verdict=result.verdict.value,
        rule_version=rule_set.rule_version,
        rule_source=rule_set.source,
        rule_source_verified=rule_set.source_verified,
        grid_nx=site.grid_nx,
        grid_ny=site.grid_ny,
        forecast_run_id=run_id,
        forecast_issued_at=result.forecast_issued_at,
        failure_reason=None,
        hours=[
            {
                "valid_at": h.valid_at.isoformat(),
                "verdict": h.verdict.value,
                "conditions": [
                    {
                        "condition_id": c.condition_id,
                        "element": c.element.value,
                        "verdict": c.verdict.value,
                        "raw": None if c.value is None else c.value.raw,
                        "lower": None if c.value is None else c.value.lower,
                        "upper": None if c.value is None else c.value.upper,
                        "threshold": thresholds[c.condition_id][0],
                        "operator": thresholds[c.condition_id][1],
                        "reason": c.reason,
                    }
                    for c in h.conditions
                ],
            }
            for h in result.hours
        ],
        windows=[
            {
                "start_at": w.start_at.isoformat(),
                "end_at": w.end_at.isoformat(),
                "verdict": w.verdict.value,
            }
            for w in result.windows
        ],
    )


def _failed_judgment(
    site: SiteRecord,
    rule_set: RuleSet,
    target_date: date,
    start_at: datetime,
    end_at: datetime,
    run_id: int,
    reason: str,
    work_item_id: int | None,
) -> Judgment:
    return Judgment(
        site_id=site.site_id,
        target_date=target_date,
        work_type=rule_set.work_type_label,
        work_start_at=start_at,
        work_end_at=end_at,
        work_item_id=work_item_id,
        verdict=Verdict.UNAVAILABLE.value,
        rule_version=rule_set.rule_version,
        rule_source=rule_set.source,
        rule_source_verified=rule_set.source_verified,
        grid_nx=site.grid_nx,
        grid_ny=site.grid_ny,
        forecast_run_id=run_id,
        forecast_issued_at=None,
        failure_reason=reason,
        hours=[],
        windows=[
            {
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "verdict": Verdict.UNAVAILABLE.value,
            }
        ],
    )


# ---------- 대시보드 ----------


def build_dashboard(
    session: Session,
    site_id: int | None,
    element_key: ElementKey | None,
    hour: int | None,
    now: datetime,
    ran: RunResult | None = None,
    work: str | None = None,
) -> DashboardView | None:
    """현장이 없으면 빈 대시보드, 없는 site_id면 None."""
    message = None if ran is None else run_message(ran, now)
    sites = sites_service.list_sites(session)
    target_date = target_date_for(now)
    if not sites:
        return _empty_dashboard(target_date)
    site = sites[0] if site_id is None else next((s for s in sites if s.site_id == site_id), None)
    if site is None:
        return None

    latest: dict[str, Judgment] = {}
    for j in repository.latest_for_site_date(session, site.site_id, target_date):
        latest.setdefault(_key(j), j)
    rule_sets = rule_sets_by_label()
    targets = _targets(site, schedules_service.items_on(session, site.site_id, target_date))
    paired = tuple((t, latest.get(t.key)) for t in targets)
    cards = tuple(_card(t.label, j, t.work_type in rule_sets) for t, j in paired)
    judged = [(t, j) for t, j in paired if j is not None]
    # 상세 카드: 고른 작업, 없으면 가장 높은 단계(같으면 앞쪽) 작업(D-041 후속).
    chosen = next(((t, j) for t, j in judged if t.key == work), None) or max(
        judged, key=lambda p: (Verdict(p[1].verdict).severity, -judged.index(p)), default=None
    )
    primary_j = None if chosen is None else chosen[1]
    chosen_key = None if chosen is None else chosen[0].key
    work_options = tuple(
        WorkOption(t.label, j.verdict, dashboard_href(site.site_id, work=t.key) + "#primary",
                   t.key == chosen_key)
        for t, j in judged
    ) if len(judged) > 1 else ()  # fmt: skip

    return DashboardView(
        sites=tuple(SiteOption(s.site_id, s.name, s.site_id == site.site_id) for s in sites),
        site_id=site.site_id,
        site_name=site.name,
        target_date=_date_text(target_date),
        work_hours=f"{site.work_start_local:%H:%M}–{site.work_end_local:%H:%M}",
        cards=cards,
        primary=None
        if primary_j is None
        else _primary(primary_j, site.site_id, element_key, hour, chosen_key),
        work_options=work_options,
        forecast_issued=None
        if primary_j is None or primary_j.forecast_issued_at is None
        else _kst_text(primary_j.forecast_issued_at),
        rule_version=None if primary_j is None else primary_j.rule_version,
        rule_verified=primary_j is not None and primary_j.rule_source_verified,
        collection_status=_collection_status(primary_j),
        judged_at=None if primary_j is None else _kst_text(primary_j.judged_at),
        grid=f"({site.grid_nx}, {site.grid_ny})",
        notice=_notice(site, target_date, cards, tuple(j for _, j in paired)),
        message=message,
        message_is_error=ran not in (None, "done", "unchanged"),
        off_period_note=None
        if site.works_on(target_date)
        else (
            f"내일({_date_text(target_date)})은 작업 기간({site.period_text()})이 아니라 "
            "판정하지 않습니다."
        ),
        week=_week(session, site, rule_sets, now),
        next_forecast=next_forecast_text(now),
        can_run=any(site.works_on(d) for d in horizon_dates(now)),
    )


def build_home(session: Session, now: datetime, ran: RunResult | None = None) -> HomeView:
    """전체 현장의 내일 판정 개요. 현장 수와 관계없이 판정 조회는 한 번만 한다."""
    target_date = target_date_for(now)
    sites = sites_service.list_sites(session)
    site_ids = [s.site_id for s in sites]
    by_site: dict[int, dict[str, Judgment]] = {}
    for j in repository.latest_for_sites_date(session, site_ids, target_date):
        by_site.setdefault(j.site_id, {}).setdefault(_key(j), j)
    items_by_site = schedules_service.items_on_for_sites(session, site_ids, target_date)
    rule_sets = rule_sets_by_label()
    summaries = tuple(
        _site_summary(s, by_site.get(s.site_id, {}), rule_sets, target_date,
                      items_by_site.get(s.site_id, ()))
        for s in sites
    )  # fmt: skip

    # 개발자 지정 순서: 판정 전 → 판정 불가 → 중지 검토 → 확인 필요 → 진행 (작업 없음은 맨 뒤).
    counts = {v.value: 0 for v in (Verdict.UNAVAILABLE, Verdict.STOP_REVIEW, Verdict.CHECK,
                                   Verdict.GO)}  # fmt: skip
    not_judged = off_period = 0
    for summary in summaries:
        if not summary.working:
            off_period += 1
        elif summary.verdict is None:
            not_judged += 1
        else:
            counts[summary.verdict] += 1
    tiles = (
        CountTile("판정 전", not_judged, None),
        *(CountTile(v, n, v) for v, n in counts.items()),
    )
    if off_period:
        tiles = (*tiles, CountTile("작업 없음", off_period, None))

    names = {s.site_id: s.name for s in sites}
    recent_rows = repository.page(
        session, None, None, 0, RECENT_ROWS, site_ids=site_ids, until=target_date
    )
    recent = _recent_runs(recent_rows, names)
    run = forecasts_service.latest_run(session)
    if run is None:
        forecast_status = "아직 수집하지 않음"
    elif run.succeeded:
        forecast_status = f"성공 · {_kst_text(run.requested_at)}"
    else:
        forecast_status = f"실패 · {run.failure_reason}"
    primary_rules = next(iter(rule_sets.values()), None)
    return HomeView(
        target_date=_date_text(target_date),
        sites=summaries,
        tiles=tiles,
        recent=recent,
        forecast_status=forecast_status,
        forecast_issued=None if run is None or not run.succeeded else _kst_text(run.base_at),
        rule_version=None if primary_rules is None else primary_rules.rule_version,
        rule_verified=primary_rules is not None and primary_rules.source_verified,
        message=None if ran is None else run_message(ran, now),
        next_forecast=next_forecast_text(now),
        message_is_error=ran
        in ("failed", "no_rules", "no_sites", "out_of_period", "beyond_forecast"),
    )


def _site_summary(
    site: SiteRecord,
    latest: dict[str, Judgment],
    rule_sets: Mapping[str, RuleSet],
    target_date: date,
    items: tuple[WorkItemRecord, ...],
) -> SiteSummary:
    working = site.works_on(target_date)

    def summary(
        verdict: str | None, reason: str, judged_at: str | None, cards: tuple[WorkCard, ...] = ()
    ) -> SiteSummary:
        return SiteSummary(
            site_id=site.site_id,
            name=site.name,
            work_hours=f"{site.work_start_local:%H:%M}–{site.work_end_local:%H:%M}",
            work_types=tuple(site.work_types),
            verdict=verdict,
            reason=reason,
            detail_href=dashboard_href(site.site_id),
            judged_at=judged_at,
            working=working,
            cards=cards,
        )

    if not working:
        return summary(None, f"작업 기간이 아닙니다 · {site.period_text()}", None)
    targets = _targets(site, items)
    cards = tuple(_card(t.label, latest.get(t.key), t.work_type in rule_sets) for t in targets)
    if not any(t.key in latest for t in targets):
        return summary(None, "아직 판정하지 않았습니다", None, cards)
    # 현장의 단계는 작업·공통 카드 중 가장 높은 단계(기준 미확인 공종의 '확인 필요' 포함).
    worst = max(
        (c for c in cards if c.verdict is not None), key=lambda c: Verdict(str(c.verdict)).severity
    )
    judged_at = max(j.judged_at for j in latest.values())
    return summary(
        worst.verdict, f"{worst.work_type} · {worst.reason}", _kst_text(judged_at), cards
    )


@dataclass(frozen=True, slots=True)
class _Target:
    """판정·표시 단위 하나: 등록한 작업(S08-1) 또는 현장 기본 시간의 공종·공통 기준."""

    key: str  # 최신 판정을 묶는 키(작업이면 "item:<id>", 아니면 공종 이름)
    label: str
    work_type: str
    start_local: time
    end_local: time
    item_id: int | None


def _targets(site: SiteRecord, items: tuple[WorkItemRecord, ...]) -> list[_Target]:
    """그날 작업이 있으면 작업마다, 없으면 현장 공종마다. 공통 기준(폭염)은 현장 기본 시간으로."""
    if items:
        main = [
            _Target(
                f"item:{i.item_id}", i.label, i.work_type, i.start_local, i.end_local, i.item_id
            )
            for i in items
        ]
    else:
        main = [
            _Target(w, w, w, site.work_start_local, site.work_end_local, None)
            for w in site.work_types
        ]
    common = [
        _Target(w, w, w, site.work_start_local, site.work_end_local, None)
        for w in judged_labels(())
    ]
    return main + common


_CONFIDENCE_NOTE = {
    "높음": "1시간 간격 예보로 작업 시간 전체를 판정",
    "보통": "3시간 간격 예보라 일부 시각만 판정 · 나머지는 판정 불가",
    "낮음": "중기예보 참고(오전·오후 강수확률·날씨만) · 기준과 직접 비교 불가 · 저장하지 않음",
    "예보 없음": "단기·중기예보 모두 없음 · 예보가 나오면 판정",
    "판정 전": "예보는 있으나 아직 판정하지 않음",
    "수집 실패": "예보를 받지 못함",
    "기간 밖": "현장 작업 기간이 아님",
    "작업 없음": "이날 등록한 작업 없음 · 작업 일정에서 추가하면 판정",
}


def _week(
    session: Session, site: SiteRecord, rule_sets: Mapping[str, RuleSet], now: datetime
) -> WeekView:
    """작업(공종)별 7일. 칸은 그날 그 공종 대상들 중 가장 높은 단계(쿼리: 판정·작업·예보 각 1회)."""
    dates = horizon_dates(now)
    latest: dict[tuple[date, str], Judgment] = {}
    for j in repository.latest_for_site_between(session, site.site_id, dates[0], dates[-1]):
        latest.setdefault((j.target_date, _key(j)), j)
    items_by_day = schedules_service.items_between(session, site.site_id, dates[0], dates[-1])
    times = forecasts_service.latest_forecast_times(session, site.grid_nx, site.grid_ny)
    region_id = land_region_for(site.address)
    mid = None if region_id is None else forecasts_service.latest_mid_forecast(session, region_id)

    days: list[WeekDay] = []
    by_type: dict[str, dict[date, WeekCell]] = {}
    for day in dates:
        in_period = site.works_on(day)
        # 등록한 작업만 보여 준다. 작업이 없는 내일만 현장 기본 공종으로 대체한다(D-023).
        has_work = day in items_by_day or day == dates[0]
        pairs = [
            (t, latest.get((day, t.key))) for t in _targets(site, items_by_day.get(day, ()))
        ] if in_period and has_work else []  # fmt: skip
        judged = [j for _, j in pairs if j is not None]
        covered = any(_has_forecast(times, *_work_range(day, t)) for t, _ in pairs)
        confidence = (
            _confidence(in_period, judged, covered) if not in_period or has_work else "작업 없음"
        )
        mid_parts = None if mid is None else mid.days.get(day)
        if confidence == "예보 없음" and mid_parts:
            confidence = "낮음"
        days.append(WeekDay(day, f"{day:%m/%d}({_WEEKDAYS[day.weekday()]})", day == dates[0],
                            in_period, confidence, _CONFIDENCE_NOTE[confidence]))  # fmt: skip
        for target, judgment in pairs:
            if confidence == "낮음" and mid_parts:
                cell = _mid_cell(target, rule_sets, mid_parts)
            else:
                card = _card(target.label, judgment, target.work_type in rule_sets)
                state: Literal["none", "pending"] = (
                    "pending" if confidence in ("예보 없음", "판정 전") else "none"
                )
                cell = _week_cell(card, state)
            current = by_type.setdefault(target.work_type, {}).get(day)
            if current is None or _rank(cell) > _rank(current):
                by_type[target.work_type][day] = cell

    def cell_for(work_type: str, day: WeekDay) -> WeekCell:
        if not day.in_period:
            return WeekCell(None, "off", None, "작업 기간 아님")
        if day.confidence == "작업 없음":
            return WeekCell(None, "off", None, "이날 등록한 작업 없음")
        found = by_type[work_type].get(day.day)
        return found or WeekCell(None, "none", None, "그날 이 공종 작업 없음")

    rows = tuple(
        WeekRow(work_type, tuple(cell_for(work_type, d) for d in days)) for work_type in by_type
    )
    return WeekView(days=tuple(days), rows=rows)


def _mid_cell(
    target: "_Target", rule_sets: Mapping[str, RuleSet], parts: tuple[MidHalfDay, ...]
) -> WeekCell:
    rule_set = rule_sets.get(target.work_type)
    if rule_set is None:
        return WeekCell(Verdict.CHECK.value, "reference", None,
                        f"{target.label} · 판정 기준 확인 전 · 현장에서 직접 판단")  # fmt: skip
    verdict, reason = mid_reference(
        rule_set, [MidPart(p.part, p.rain_probability_pct, p.weather) for p in parts]
    )
    return WeekCell(verdict.value, "reference", None, f"{target.label} · {reason}")


def _confidence(
    in_period: bool, judged: list[Judgment], covered: bool
) -> Literal["높음", "보통", "낮음", "예보 없음", "판정 전", "수집 실패", "기간 밖"]:
    """그날 판정에 쓴 예보 자료의 촘촘함. 저장된 시간별 값이 있는지로만 정한다(추정 없음)."""
    if not in_period:
        return "기간 밖"
    if not judged:
        return "판정 전" if covered else "예보 없음"
    if all(j.failure_reason for j in judged):
        return "수집 실패"
    hours = [h for j in judged if not j.failure_reason for h in j.hours]
    has_value = [any(c["raw"] is not None for c in h["conditions"]) for h in hours]
    if not any(has_value):
        return "예보 없음"
    return "높음" if all(has_value) else "보통"


def _week_cell(card: WorkCard, empty_state: Literal["none", "pending"]) -> WeekCell:
    if card.verdict is None:
        return WeekCell(None, empty_state, None, card.reason)
    return WeekCell(card.verdict, "verdict", card.detail_href, f"{card.work_type} · {card.reason}")


def _rank(cell: WeekCell) -> int:
    return -1 if cell.verdict is None else Verdict(cell.verdict).severity


def _key(judgment: Judgment) -> str:
    if judgment.work_item_id is not None:
        return f"item:{judgment.work_item_id}"
    return judgment.work_type


RECENT_RUNS = 5
# 한 번 판정에 공종 수 + 공통 기준만큼 행이 생긴다. 넉넉히 읽어 묶음 5개를 채운다(쿼리 1회).
RECENT_ROWS = RECENT_RUNS * 10


def _recent_runs(rows: list[Judgment], names: Mapping[int, str]) -> tuple[RecentRun, ...]:
    """현장·대상 날짜마다 작업별 최신 판정만 묶는다(지난 판정은 판정 내역에 남는다). rows는 최신순.

    같은 예보로 다시 판정하면 새 행을 만들지 않으므로, 판정 시각이 아니라 작업 키로 갱신을 판단한다.
    """
    groups: dict[tuple[int, date], dict[str, Judgment]] = {}
    for j in rows:
        groups.setdefault((j.site_id, j.target_date), {}).setdefault(_key(j), j)
    ordered = sorted(
        groups.items(),
        key=lambda g: (g[0][1], max(j.judged_at for j in g[1].values())),
        reverse=True,
    )
    runs = []
    for (site_id, target_date), latest in ordered[:RECENT_RUNS]:
        items = list(latest.values())
        judged_at = max(j.judged_at for j in items)
        runs.append(
            RecentRun(
                target_label=_date_text(target_date),
                site_name=names.get(site_id, "삭제된 현장"),
                verdict=max((Verdict(j.verdict) for j in items), key=lambda v: v.severity).value,
                when=f"{_kst_text(judged_at)} 판정",
                items=tuple(
                    RecentItem(j.work_type, j.verdict, f"/judgments/{j.id}") for j in items
                ),
                more_href=f"/judgments?site_id={site_id}",
            )
        )
    return tuple(runs)


def dashboard_href(site_id: int, **params: str | int) -> str:
    """현장별 대시보드 주소. 홈(/)과 별도 화면이다."""
    return "/dashboard?" + urlencode({"site_id": site_id, **params})


def _empty_dashboard(target_date: date) -> DashboardView:
    return DashboardView(
        sites=(), site_id=None, site_name="", target_date=_date_text(target_date), work_hours="",
        cards=(), primary=None, forecast_issued=None, rule_version=None, rule_verified=False,
        collection_status="현장 등록 전", judged_at=None, grid="—", notice=None, message=None,
        message_is_error=False, off_period_note=None,
    )  # fmt: skip


def _card(work_type: str, judgment: Judgment | None, has_rules: bool) -> WorkCard:
    if not has_rules:
        return WorkCard(work_type, "", Verdict.CHECK.value,
                        "판정 기준 확인 전 · 현장에서 직접 판단", None)  # fmt: skip
    if judgment is None:
        return WorkCard(work_type, "", None, "아직 판정하지 않았습니다", None)
    time_range = _range_text(judgment.work_start_at, judgment.work_end_at)
    href = f"/judgments/{judgment.id}"
    if judgment.failure_reason:
        return WorkCard(work_type, time_range, judgment.verdict, judgment.failure_reason, href)
    flagged = [w for w in judgment.windows if w["verdict"] != Verdict.GO.value]
    if not flagged:
        return WorkCard(
            work_type, time_range, judgment.verdict, "모든 시간 기준에 해당하지 않음", href
        )
    worst = max(flagged, key=lambda w: Verdict(w["verdict"]).severity)
    reason = _window_reason(judgment.hours, worst)
    window_text = _range_text(_dt(worst["start_at"]), _dt(worst["end_at"]))
    return WorkCard(work_type, time_range, judgment.verdict, f"{window_text} · {reason}", href)


def _primary(
    judgment: Judgment,
    site_id: int,
    element_key: ElementKey | None,
    hour: int | None,
    work: str | None = None,
) -> PrimaryJudgment:
    windows = tuple(
        WorkWindow(
            _range_text(_dt(w["start_at"]), _dt(w["end_at"])),
            w["verdict"],
            None
            if w["verdict"] == Verdict.GO.value
            else (judgment.failure_reason or _window_reason(judgment.hours, w)),
        )
        for w in judgment.windows
    )
    counts = {v.value: 0 for v in (Verdict.GO, Verdict.CHECK, Verdict.STOP_REVIEW,
                                   Verdict.UNAVAILABLE)}  # fmt: skip
    for h in judgment.hours:
        counts[h["verdict"]] += 1
    return PrimaryJudgment(
        judgment_id=judgment.id,
        work_type=judgment.work_type,
        verdict=judgment.verdict,
        windows=windows,
        tiles=tuple(Tile(v, n) for v, n in counts.items()),
        chart=_chart(judgment, site_id, element_key, hour, work),
        failure_reason=judgment.failure_reason,
    )


def _chart(
    judgment: Judgment,
    site_id: int,
    element_key: ElementKey | None,
    hour: int | None,
    work: str | None = None,
) -> Chart | None:
    if not judgment.hours:
        return None
    # 그래프는 시간별로 달라지는 요소만 그린다. 하루 단위 값(일평균기온 등)은 상세 표에서 본다.
    elements = [e for e in _elements(judgment) if e in _KEY_OF]
    if not elements:
        return None
    element = ELEMENT_KEYS.get(element_key) if element_key else None
    if element not in elements:
        element = _deciding_element(judgment.hours, elements)
    # 같은 요소에 기준이 여럿이면(폭염 31·33도) 가장 먼저 해당하는 낮은 기준선을 그린다.
    entries = [(_dt(h["valid_at"]), _entry(h, element, lowest=True)) for h in judgment.hours]
    known = [(t, e) for t, e in entries if e is not None and e["lower"] is not None]
    threshold = float(next(e for _, e in entries if e is not None)["threshold"])
    operator = str(next(e for _, e in entries if e is not None)["operator"])
    peak = max((e["lower"] for _, e in known), default=0.0)
    axis_max = max(threshold * 1.25, peak * 1.1, 0.1)
    hours = [t.hour for t, _ in entries]
    if hour is not None and hour in hours:
        selected_hour = hour
    else:  # 지정이 없거나 범위 밖이면 가장 큰 예보값의 시각
        selected_hour = max(known, key=lambda te: te[1]["lower"])[0].hour if known else hours[0]
    unit = ELEMENT_UNIT[element]
    label = ELEMENT_LABEL[element]
    key = _KEY_OF[element]

    bars = []
    selected_text = "예보값 없음"
    for t, e in entries:
        text = "없음" if e is None or e["lower"] is None else _value_text(e, unit)
        over = e is not None and _meets(e)
        lower = 0.0 if e is None or e["lower"] is None else float(e["lower"])
        if t.hour == selected_hour:
            selected_text = text
        bars.append(
            Bar(
                hour_label=f"{t.hour:02d}",
                height_px=max(_MIN_BAR_PX, round(lower / axis_max * _PLOT_HEIGHT_PX)),
                tip=text,
                aria_label=f"{t.hour:02d}:00 {label} {text}" + (", 기준 해당" if over else ""),
                over=over,
                selected=t.hour == selected_hour,
                href=href_for(site_id, key, t.hour, work),
            )
        )
    threshold_text = f"{threshold:g} {unit} {OPERATOR_TEXT[operator]}"
    return Chart(
        title=f"시간대별 예보 · {judgment.work_type} 기준",
        tabs=tuple(
            Tab(ELEMENT_LABEL[e], href_for(site_id, _KEY_OF[e], selected_hour, work), e == element)
            for e in elements
        ),
        bars=tuple(bars),
        selected_value=selected_text,
        selected_caption=(f"{selected_hour:02d}:00 {label} 예보 · 기준 {threshold_text}"),
        threshold_bottom_px=round(threshold / axis_max * _PLOT_HEIGHT_PX),
        threshold_text=threshold_text,
    )


def _deciding_element(hours: list[dict[str, Any]], elements: list[Element]) -> Element:
    """판정 단계를 가장 높게 만든 요소(같으면 기준표 순서). 그래프를 그 요소로 연다."""

    def severity(element: Element) -> int:
        return max(
            (Verdict(c["verdict"]).severity for h in hours for c in h["conditions"]
             if c["element"] == element.value),
            default=-1,
        )  # fmt: skip

    return max(elements, key=lambda e: (severity(e), -elements.index(e)))


def href_for(site_id: int, key: ElementKey, hour: int, work: str | None = None) -> str:
    # #chart: 스크립트 없이 새로 불러와도 그래프 위치로 이동한다(스크립트가 있으면 카드만 교체).
    extra: dict[str, str | int] = {} if work is None else {"work": work}
    return dashboard_href(site_id, element=key, hour=hour, **extra) + "#chart"


def _elements(judgment: Judgment) -> list[Element]:
    """판정에 쓴 요소(기준표 순서, 중복 없음). 한 요소에 조건이 여럿일 수 있다."""
    if not judgment.hours:
        return []
    return list(dict.fromkeys(Element(c["element"]) for c in judgment.hours[0]["conditions"]))


def _entry(
    hour_json: dict[str, Any], element: Element, lowest: bool = False
) -> dict[str, Any] | None:
    entries: list[dict[str, Any]] = [
        c for c in hour_json["conditions"] if c["element"] == element.value
    ]
    if not entries:
        return None
    return min(entries, key=lambda c: float(c["threshold"])) if lowest else entries[0]


def _meets(entry: dict[str, Any]) -> bool:
    """예보값 구간 전체가 기준에 해당하는지(그래프·표 강조용). 판정 단계는 저장된 verdict를 쓴다.

    낮은 쪽 기준(이하·미만)은 상한으로 본다. 범주 예보의 상한 포함 여부는 저장하지 않으므로
    '미만'에서 상한이 기준과 같으면 강조하지 않는다(강조를 과장하지 않는 쪽).
    """
    if entry["lower"] is None:
        return False
    lower, threshold, operator = float(entry["lower"]), float(entry["threshold"]), entry["operator"]
    upper = None if entry["upper"] is None else float(entry["upper"])
    if operator == ">=":
        return lower >= threshold
    if operator == ">":
        return lower > threshold
    if operator == "<=":
        return upper is not None and upper <= threshold
    return upper is not None and upper < threshold  # "<"


def _element_meets(hour_json: dict[str, Any], element: Element) -> bool:
    """그 시각에 이 요소의 조건 중 하나라도 기준에 해당하는가.

    같은 요소에 높은 쪽·낮은 쪽 기준이 함께 있을 수 있다(콘크리트 일평균기온 25 초과·4 이하).
    """
    return any(_meets(c) for c in hour_json["conditions"] if c["element"] == element.value)


def _value_text(entry: dict[str, Any], unit: str) -> str:
    if entry["lower"] is None:
        return "없음"
    if entry["upper"] is not None and entry["lower"] == entry["upper"]:
        return f"{float(entry['lower']):.1f} {unit}"
    return str(entry["raw"])  # 범주 예보는 원문 그대로("1mm 미만")


def _window_reason(hours: list[dict[str, Any]], window: dict[str, Any]) -> str:
    """구간 판정을 만든 조건 요약. 예: '강우 최대 2.0 mm/h (15:00) · 기준 1 mm/h 이상'."""
    start, end, verdict = _dt(window["start_at"]), _dt(window["end_at"]), window["verdict"]
    hits: dict[str, tuple[datetime, dict[str, Any]]] = {}
    for h in hours:
        t = _dt(h["valid_at"])
        if not (start <= t < end or (t < start < t + timedelta(hours=1))):
            continue
        for c in h["conditions"]:
            if c["verdict"] != verdict:
                continue
            best = hits.get(c["element"])
            if best is None or (c["lower"] or 0) > (best[1]["lower"] or 0):
                hits[c["element"]] = (t, c)
    if not hits:
        return str(verdict)
    if verdict != Verdict.STOP_REVIEW.value:
        return str(next(iter(hits.values()))[1]["reason"])
    parts = []
    for element_value, (t, c) in hits.items():
        element = Element(element_value)
        unit = ELEMENT_UNIT[element]
        parts.append(
            f"{ELEMENT_LABEL[element]} 최대 {_value_text(c, unit)} ({t:%H:%M}) · "
            f"기준 {float(c['threshold']):g} {unit} {OPERATOR_TEXT[c['operator']]}"
        )
    return " / ".join(parts)


def _collection_status(judgment: Judgment | None) -> str:
    if judgment is None:
        return "아직 판정하지 않음"
    if judgment.failure_reason:
        return f"실패 · {judgment.failure_reason}"
    return f"성공 · 판정 {_kst_text(judgment.judged_at)}"


def _notice(
    site: SiteRecord,
    target_date: date,
    cards: tuple[WorkCard, ...],
    judgments: tuple[Judgment | None, ...],
) -> Notice | None:
    """알림 문구 미리보기. 실제 발송은 사업자 등록 후(D-015). judgments는 cards와 같은 순서."""
    judged = [j for j in judgments if j is not None]
    if not judged:
        return None
    items = []
    for card, judgment in zip(cards, judgments, strict=True):
        if card.verdict is None or card.verdict == Verdict.GO.value:
            continue
        if judgment is None:
            items.append(NoticeItem(card.work_type, card.verdict, "기준 확인 전"))
            continue
        for w in judgment.windows:
            if w["verdict"] == Verdict.GO.value:
                continue
            reason = "예보 수집 실패" if judgment.failure_reason else _notice_reason(judgment, w)
            items.append(
                NoticeItem(
                    f"{card.work_type} {_range_text(_dt(w['start_at']), _dt(w['end_at']))}",
                    w["verdict"],
                    reason,
                )
            )
    first = judged[0]
    return Notice(
        title=f"[공온] 내일({target_date.month}/{target_date.day}) {site.name}",
        items=tuple(items),
        detail_href=f"/judgments/{first.id}",
    )


def _notice_reason(judgment: Judgment, window: dict[str, Any]) -> str:
    start, end = _dt(window["start_at"]), _dt(window["end_at"])
    labels = []
    for h in judgment.hours:
        t = _dt(h["valid_at"])
        if t + timedelta(hours=1) <= start or t >= end:
            continue
        for c in h["conditions"]:
            label = ELEMENT_LABEL[Element(c["element"])]
            if c["verdict"] == window["verdict"] and label not in labels:
                labels.append(label)
    return "·".join(labels) or window["verdict"]


# ---------- 상세 ----------


def serialize_judgment(judgment: Judgment) -> dict[str, Any]:
    """저장된 판정의 JSON 계약(docs/schema.json). 재계산하거나 원문 검증 상태를 보정하지 않는다."""

    def timestamp(value: datetime) -> str:
        if value.utcoffset() is None:
            raise ValueError("판정 기록의 시각에 시간대가 없음")
        return value.astimezone(KST).isoformat()

    return {
        "schema_version": "1.2",
        "data_type": "forecast",
        "judgment_id": judgment.id,
        "site_id": judgment.site_id,
        "target_date": judgment.target_date.isoformat(),
        "work_type": judgment.work_type,
        "work_start_at": timestamp(judgment.work_start_at),
        "work_end_at": timestamp(judgment.work_end_at),
        "verdict": judgment.verdict,
        "rule_version": judgment.rule_version,
        "rule_source": judgment.rule_source,
        "rule_source_verified": judgment.rule_source_verified,
        "grid_nx": judgment.grid_nx,
        "grid_ny": judgment.grid_ny,
        "forecast_run_id": judgment.forecast_run_id,
        "forecast_issued_at": (
            None if judgment.forecast_issued_at is None else timestamp(judgment.forecast_issued_at)
        ),
        "failure_reason": judgment.failure_reason,
        "element_units": {element.value: unit for element, unit in ELEMENT_UNIT.items()},
        "hours": deepcopy(judgment.hours),
        "windows": deepcopy(judgment.windows),
        "judged_at": timestamp(judgment.judged_at),
    }


def get_detail(session: Session, judgment_id: int) -> DetailView | None:
    judgment = repository.get(session, judgment_id)
    if judgment is None:
        return None
    site = sites_service.get_site(session, judgment.site_id)
    elements = _elements(judgment)
    chips = ["자료 유형: 예보 (현장 관측 아님)"]
    if judgment.forecast_issued_at is not None:
        chips.append(f"예보 발표 {_iso_kst(judgment.forecast_issued_at)}")
    chips += [
        f"판정 시각 {_iso_kst(judgment.judged_at)}",
        f"기준 버전 {judgment.rule_version}",
        f"기상청 격자 ({judgment.grid_nx}, {judgment.grid_ny})",
    ]
    return DetailView(
        site_id=None if site is None else site.site_id,
        site_name="삭제된 현장" if site is None else site.name,
        target_date=_date_text(judgment.target_date),
        work_type=judgment.work_type,
        work_range=_range_text(judgment.work_start_at, judgment.work_end_at),
        verdict=judgment.verdict,
        chips=tuple(chips),
        criteria=tuple(_criterion(judgment, e) for e in elements),
        columns=tuple(f"{ELEMENT_LABEL[e]} ({ELEMENT_UNIT[e]})" for e in elements),
        rows=tuple(_hour_row(h, elements) for h in judgment.hours),
        failure_reason=judgment.failure_reason,
    )


def _criterion(judgment: Judgment, element: Element) -> CriterionCard:
    entries = [(_dt(h["valid_at"]), _entry(h, element)) for h in judgment.hours]
    present = [(t, e) for t, e in entries if e is not None]
    verdict = max((Verdict(e["verdict"]) for _, e in present), key=lambda v: v.severity)
    known = [(t, e) for t, e in present if e["lower"] is not None]
    unit = ELEMENT_UNIT[element]
    peak = max(known, key=lambda te: te[1]["lower"]) if known else None
    rules = {
        c["condition_id"]: c
        for h in judgment.hours
        for c in h["conditions"]
        if c["element"] == element.value
    }
    return CriterionCard(
        label=ELEMENT_LABEL[element],
        icon=_ICON[element],
        verdict=verdict.value,
        peak_value="없음" if peak is None else _value_text(peak[1], unit).removesuffix(f" {unit}"),
        unit=unit,
        peak_time=None if peak is None else f"{peak[0]:%H:%M}",
        rule_text="기준: "
        + " / ".join(
            f"{float(c['threshold']):g} {unit} {OPERATOR_TEXT[c['operator']]}"
            for c in rules.values()
        ),
        source=judgment.rule_source,
        source_verified=judgment.rule_source_verified,
    )


def _hour_row(hour_json: dict[str, Any], elements: list[Element]) -> HourRow:
    cells = []
    for element in elements:
        e = _entry(hour_json, element, lowest=True)
        text = "없음" if e is None or e["lower"] is None else _value_text(e, "").strip()
        cells.append(Cell(text, _element_meets(hour_json, element)))
    verdict = hour_json["verdict"]
    if verdict == Verdict.GO.value:
        calculation = "기준에 해당하는 요소 없음"
    else:
        calculation = " / ".join(
            c["reason"] for c in hour_json["conditions"] if c["verdict"] == verdict
        )
    return HourRow(f"{_dt(hour_json['valid_at']):%H:%M}", tuple(cells), verdict, calculation)


# ---------- 내역 ----------


def build_history(
    session: Session, verdict: VerdictFilter, site_id: int | None, page: int
) -> HistoryView:
    sites = sites_service.list_sites(session)
    names = {s.site_id: s.name for s in sites}
    counts = repository.verdict_counts(session, site_id)
    verdict_value = None if verdict == "전체" else verdict
    # 다음 페이지가 있는지 알기 위해 한 건 더 읽는다.
    rows = repository.page(session, site_id, verdict_value, (page - 1) * HISTORY_PAGE_SIZE,
                           HISTORY_PAGE_SIZE + 1)  # fmt: skip
    has_next = len(rows) > HISTORY_PAGE_SIZE

    def href(v: str, p: int) -> str:
        params: dict[str, str | int] = {"verdict": v, "page": p}
        if site_id is not None:
            params["site_id"] = site_id
        return "/judgments?" + urlencode(params)

    return HistoryView(
        rows=tuple(
            HistoryRow(
                judgment_id=j.id,
                target_date=f"{j.target_date:%m/%d}({_WEEKDAYS[j.target_date.weekday()]})",
                site_name=names.get(j.site_id, "삭제된 현장"),
                work=f"{j.work_type} {_range_text(j.work_start_at, j.work_end_at)}",
                verdict=j.verdict,
                issued="—"
                if j.forecast_issued_at is None
                else f"{j.forecast_issued_at.astimezone(KST):%m/%d %H:%M}",
                rule_version=j.rule_version,
                note=j.failure_reason,
            )
            for j in rows[:HISTORY_PAGE_SIZE]
        ),
        filters=tuple(
            FilterLink(
                label=label,
                count=sum(counts.values()) if label == "전체" else counts.get(label, 0),
                href=href(label, 1),
                selected=label == verdict,
            )
            for label in VERDICT_FILTERS
        ),
        site_options=tuple(SiteOption(s.site_id, s.name, s.site_id == site_id) for s in sites),
        selected_site_id=site_id,
        selected_verdict=verdict,
        page=page,
        prev_href=href(verdict, page - 1) if page > 1 else None,
        next_href=href(verdict, page + 1) if has_next else None,
    )


# ---------- 표시 형식 ----------


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(KST)


def _date_text(value: date) -> str:
    return f"{value.month}월 {value.day}일({_WEEKDAYS[value.weekday()]})"


def _range_text(start_at: datetime, end_at: datetime) -> str:
    return f"{start_at.astimezone(KST):%H:%M}–{end_at.astimezone(KST):%H:%M}"


def _kst_text(value: datetime) -> str:
    local = value.astimezone(KST)
    return f"{local.month}월 {local.day}일 {local:%H:%M}"


def _iso_kst(value: datetime) -> str:
    return f"{value.astimezone(KST):%Y-%m-%d %H:%M} KST"
