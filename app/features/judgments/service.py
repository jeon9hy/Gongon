"""판정 실행·저장과 화면 모델 만들기. 판정 계산은 engine/judgment.judge만 한다."""

import logging
from bisect import bisect_left
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.core.rules import COMMON_LABELS, judged_labels, rule_sets_by_label
from app.features.auth.schemas import CurrentUser
from app.features.changes import service as changes_service
from app.features.forecasts import service as forecasts_service
from app.features.judgments import repository
from app.features.judgments.models import Judgment, JudgmentRun
from app.features.judgments.schemas import (
    Bar,
    BoardItem,
    Cell,
    Chart,
    CheckIssue,
    CountTile,
    CriterionCard,
    DashboardView,
    DayBoard,
    DayPanel,
    DayTypeRow,
    DetailView,
    ElementKey,
    FilterLink,
    HistoryDay,
    HistoryRow,
    HistorySite,
    HistoryView,
    HomeDay,
    HomeIndexDay,
    HomeView,
    HourRow,
    Notice,
    NoticeItem,
    PageLink,
    PrimaryJudgment,
    RunResult,
    SiteOption,
    SiteSummary,
    SiteTab,
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
from app.features.sites.schemas import SiteRecord, SiteScope
from app.features.teams import service as teams_service
from app.features.teams.schemas import MANAGE_ROLES
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
    ESTIMATED_NOTE,
    OPERATOR_TEXT,
    Element,
    JudgmentResult,
    MidPart,
    RuleSet,
    Verdict,
    judge,
    mid_reference,
)
from engine.judgment.index import (
    GongonIndex,
    HourInput,
    MidWorkInput,
    gongon_index,
    margin_pct,
    mid_gongon_index,
)
from engine.kst import KST

logger = logging.getLogger(__name__)

VERDICT_FILTERS: tuple[VerdictFilter, ...] = ("전체", "진행", "확인 필요", "중지 검토", "판정 불가")
HISTORY_PAGE_SIZES = (30, 50, 100)  # 판정 내역 한 쪽에 보이는 판정 수(고를 수 있는 값)
HISTORY_VISIBLE_ROWS = 5  # 판정 내역에서 현장 묶음마다 바로 보이는 줄 수(나머지는 더보기)
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
    Element.MIN_TEMPERATURE_NEXT_24H_C: "thermometer",
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
    return f"다음 예보 {nxt:%H:%M} 발표({ready:%H:%M} 반영)"


# 판정 실행 결과 코드 → 대시보드 문구. URL에는 코드만 싣는다(임의 문구 표시 방지).
RUN_MESSAGES: dict[RunResult, str] = {
    "done": "판정했습니다.",
    "failed": "예보를 받지 못해 ‘판정 불가’로 기록했습니다. 데이터 상태에서 원인을 확인하세요.",
    "no_rules": (
        "등록한 작업 중 판정 기준이 있는 공종이 없습니다. "
        "기준 미확인 공종은 현장에서 직접 판단하세요."
    ),
    "no_work": (
        "앞으로 7일 동안 등록한 작업이 없어 판정하지 않았습니다. 작업 일정에서 작업을 추가하세요."
    ),
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
    site = sites_service.get_site(session, site_id, None)
    if site is None:
        return None
    rule_sets = rule_sets_by_label()
    dates = horizon_dates(now)
    working = [d for d in dates if site.works_on(d)]
    if not working:
        return "out_of_period"  # 작업하지 않는 날은 예보도 받지 않는다
    items_by_day = schedules_service.items_between(session, site.site_id, working[0], working[-1])
    # 등록한 작업만 판정한다(현장 기본 공종 대체 없음, D-059). 작업이 없으면 예보도 받지 않는다.
    working = [d for d in working if d in items_by_day]
    if not working:
        return "no_work"
    if not any(_targets_for(items_by_day[d], rule_sets) for d in working):
        return "no_rules"
    snapshot = forecasts_service.get_forecast(
        session, site.grid_nx, site.grid_ny, now, auth, http_get
    )
    if snapshot.weather is None:
        # 실패는 가장 가까운 작업일에만 남긴다(같은 원인을 날짜마다 반복 기록하지 않음).
        day = working[0]
        for target in _targets_for(items_by_day.get(day, ()), rule_sets):
            start_at, end_at = _work_range(day, target)
            session.add(
                _failed_judgment(site, rule_sets[target.work_type], day, start_at, end_at,
                                 snapshot.run_id, f"예보 수집 실패: {snapshot.failure_reason}",
                                 target.item_id)
            )  # fmt: skip
        _record_run(session, site.site_id, now, None, "failed", 0)
        session.commit()
        return "failed"

    forecast_times = sorted(h.valid_at for h in snapshot.weather.hours)
    judged_days: list[date] = []
    stored = 0  # 새로 저장한 판정 수. 0이면 같은 예보로 이미 판정한 결과와 같다
    for day in working:
        for target in _targets_for(items_by_day[day], rule_sets):
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
    outcome: RunResult = "beyond_forecast" if not judged_days else "done" if stored else "unchanged"
    _record_run(session, site.site_id, now, snapshot.weather.forecast_issued_at, outcome, stored)
    session.commit()
    logger.info("판정 site_id=%s dates=%s base_at=%s", site.site_id, judged_days, snapshot.base_at)
    return outcome


def _record_run(
    session: Session,
    site_id: int,
    now: datetime,
    issued_at: datetime | None,
    result: RunResult,
    stored: int,
) -> None:
    """예보를 확인한 실행만 남긴다(기간 밖·기준 없음처럼 예보를 보지 않은 실행은 제외)."""
    session.add(JudgmentRun(site_id=site_id, ran_at=now, forecast_issued_at=issued_at,
                            result=result, stored_count=stored))  # fmt: skip


def checked_short_text(run: JudgmentRun | None, now: datetime) -> str | None:
    """홈 카드용 짧은 확인 시각. 오늘이면 '22:45 확인', 다른 날이면 '10/7 22:45 확인'."""
    if run is None:
        return None
    ran = run.ran_at.astimezone(KST)
    if ran.date() == now.astimezone(KST).date():
        return f"{ran:%H:%M} 확인"
    return f"{ran.month}/{ran.day} {ran:%H:%M} 확인"


def checked_text(run: JudgmentRun | None) -> str | None:
    """'10월 8일 18:15 확인 · 17:00 발표 예보'. 실행 기록이 없으면 None."""
    if run is None:
        return None
    if run.forecast_issued_at is None:
        return f"{_kst_text(run.ran_at)} 확인 · 예보 수집 실패"
    return (
        f"{_kst_text(run.ran_at)} 확인 · {run.forecast_issued_at.astimezone(KST):%H:%M} 발표 예보"
    )


def _has_forecast(times: list[datetime], start_at: datetime, end_at: datetime) -> bool:
    """작업 날(현지 날짜)에 예보 시각이 하나라도 있는가(times는 정렬됨).

    작업 시간에 값이 없어도 같은 날 값으로 추정해 판정한다(D-053, engine judge).
    """
    day_start = start_at.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    index = bisect_left(times, day_start)
    return index < len(times) and times[index] < day_start + timedelta(days=1)


def _targets_for(
    items: tuple[WorkItemRecord, ...], rule_sets: Mapping[str, RuleSet]
) -> list["_Target"]:
    """판정할 수 있는(기준이 있는) 대상만."""
    return [t for t in _targets(items) if t.work_type in rule_sets]


def _work_range(day: date, target: "_Target") -> tuple[datetime, datetime]:
    return (
        datetime.combine(day, target.start_local, KST),
        datetime.combine(day, target.end_local, KST),
    )


def run_for_user_site(
    session: Session,
    user: CurrentUser,
    site_id: int,
    now: datetime,
    auth: KmaAuth,
    http_get: HttpGet,
    mid_service_key: str = "",
) -> RunResult | None:
    """화면의 "지금 판정하기". 비참여 현장은 404, 조정자가 아니면 403(teams)."""
    teams_service.require_role(session, user, site_id, MANAGE_ROLES)
    return run_for_site(session, site_id, now, auth, http_get, mid_service_key)


def run_all(
    session: Session,
    scope: SiteScope,
    now: datetime,
    auth: KmaAuth,
    http_get: HttpGet,
    mid_service_key: str = "",
) -> RunResult:
    """범위 안 모든 현장의 7일 판정. 같은 격자는 예보를 한 번만 받는다(forecasts 재사용).

    scope None은 매시 자동 판정(시스템 작업)의 전체 현장이다."""
    results = [
        run_for_site(session, s.site_id, now, auth, http_get, mid_service_key)
        for s in sites_service.list_sites(session, scope)
    ]
    if not results:
        return "no_sites"
    if "failed" in results:
        return "failed"
    if "done" in results:
        return "all_done"
    if "unchanged" in results:
        return "unchanged"
    for code in ("beyond_forecast", "out_of_period", "no_work"):
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
    scope: SiteScope,
    site_id: int | None,
    element_key: ElementKey | None,
    hour: int | None,
    now: datetime,
    ran: RunResult | None = None,
    work: str | None = None,
) -> DashboardView | None:
    """현장이 없으면 빈 대시보드, 없는 site_id면 None."""
    message = None if ran is None else run_message(ran, now)
    sites = sites_service.list_sites(session, scope)
    target_date = target_date_for(now)
    if not sites:
        # 없거나 참여하지 않은 현장을 직접 열면 빈 화면이 아니라 404(D-057)
        return None if site_id is not None else _empty_dashboard(target_date)
    site = sites[0] if site_id is None else next((s for s in sites if s.site_id == site_id), None)
    if site is None:
        return None

    latest: dict[str, Judgment] = {}
    for j in repository.latest_for_site_date(session, site.site_id, target_date):
        latest.setdefault(_key(j), j)
    rule_sets = rule_sets_by_label()
    items = schedules_service.items_on(session, site.site_id, target_date)
    triples = _current_pairs(site, _targets(items), target_date, latest, rule_sets)
    folded = _folded(triples, rule_sets)
    cards = tuple(
        card if backing is None
        else replace(card, open_href=dashboard_href(site.site_id, work=t.key))
        for t, card, backing in folded
    )  # fmt: skip
    # 작업 하나에 카드 하나. 상세는 그 카드의 단계를 정한 판정(작업 또는 폭염)을 보인다.
    judged = [(t, backing) for t, _, backing in folded if backing is not None]
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
        work_hours=_items_span(items),
        cards=cards,
        detail_open=work is not None or element_key is not None or hour is not None,
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
        notice=_notice(site, target_date, cards, tuple(b for _, _, b in folded)),
        message=message,
        message_is_error=ran not in (None, "done", "unchanged"),
        off_period_note=None
        if site.works_on(target_date)
        else (
            f"내일({_date_text(target_date)})은 작업 기간({site.period_text()})이 아니라 "
            "판정하지 않습니다."
        ),
        week=_week(session, site, rule_sets, now),
        checked=checked_text(repository.latest_runs(session, [site.site_id]).get(site.site_id)),
        next_forecast=next_forecast_text(now),
        can_run=any(site.works_on(d) for d in horizon_dates(now)),
    )


def build_home(
    session: Session,
    scope: SiteScope,
    now: datetime,
    ran: RunResult | None = None,
    site_id: int | None = None,
) -> HomeView:
    """홈: 오늘·내일 공온 점검판(D-065) → 내일 날씨 개요. 판정 조회는 현장 수와 관계없이 한 번.

    site_id를 주면(내 현장일 때) 그 현장만 보인다. 위 현장 칸은 늘 전체 범위로 만든다.
    """
    target_date = target_date_for(now)
    all_sites = sites_service.list_sites(session, scope)
    selected = site_id if site_id in {s.site_id for s in all_sites} else None
    tabs = _site_tabs(session, all_sites, selected, now)
    sites = [s for s in all_sites if selected is None or s.site_id == selected]
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
    runs = repository.latest_runs(session, site_ids)
    summaries = tuple(
        replace(s, checked=checked_text(run), checked_short=checked_short_text(run, now))
        for s in summaries
        for run in [runs.get(s.site_id)]
    )

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

    run = forecasts_service.latest_run(session)
    if run is None:
        forecast_status = "아직 수집하지 않음"
    elif run.succeeded:
        forecast_status = f"성공 · {_kst_text(run.requested_at)}"
    else:
        forecast_status = f"실패 · {run.failure_reason}"
    primary_rules = next(iter(rule_sets.values()), None)
    index_days, day_panels = _week_overview(session, sites, rule_sets, now)
    boards, week = _check_boards(session, sites, by_site, rule_sets, now)
    return HomeView(
        tabs=tabs,
        selected_site_id=selected,
        boards=boards,
        week=week,
        index_days=index_days,
        day_panels=day_panels,
        checked_short=checked_short_text(
            max(runs.values(), key=lambda r: r.ran_at, default=None), now
        ),
        target_date=_date_text(target_date),
        today_date=_date_text(now.astimezone(KST).date()),
        sites=summaries,
        tiles=tiles,
        forecast_status=forecast_status,
        forecast_issued=None if run is None or not run.succeeded else _kst_text(run.base_at),
        rule_version=None if primary_rules is None else primary_rules.rule_version,
        rule_verified=primary_rules is not None and primary_rules.source_verified,
        message=None if ran is None else run_message(ran, now),
        next_forecast=next_forecast_text(now),
        message_is_error=ran
        in ("failed", "no_rules", "no_sites", "out_of_period", "beyond_forecast"),
    )


_PHASE_LABELS = {"now": "진행 중", "before": "예정", "done": "끝남"}

# 공온 점검 항목(D-065). 날씨는 그중 하나다. 작업 위치는 선택 입력이라 점검하지 않는다(D-077).
# 모두 등록한 자료로만 확인하는 규칙이며 기준 수치를 새로 정하지 않는다.
CHECK_LABELS = {
    "weather": "날씨",
    "company": "실행 업체",
    "overlap": "시간·위치 겹침",
    "change": "변경 검토 중",
}
WEEK_DAYS_HOME = 7
_WEATHER_OK = {Verdict.GO.value}


_NO_SCORE = {"낮음": "예보 전", "높음": "점수 없음", "보통": "점수 없음"}


def _site_tabs(
    session: Session, sites: Sequence[SiteRecord], selected: int | None, now: datetime
) -> tuple[SiteTab, ...]:
    """현장이 둘 이상이면 전체 + 현장마다 오늘 작업 수(쿼리 1회)."""
    if len(sites) < 2:
        return ()
    today = now.astimezone(KST).date()
    items = schedules_service.items_on_for_sites(session, [s.site_id for s in sites], today)
    counts = {sid: len(rows) for sid, rows in items.items()}
    return (
        SiteTab(None, "전체", sum(counts.values()), selected is None, "/"),
        *(
            SiteTab(
                s.site_id,
                s.name,
                counts.get(s.site_id, 0),
                s.site_id == selected,
                f"/?site_id={s.site_id}",
            )
            for s in sites
        ),
    )


_VERDICT_RANK = {"중지 검토": 0, "확인 필요": 1, "판정 불가": 2, "진행": 3}


def _week_overview(
    session: Session, sites: Sequence[SiteRecord], rule_sets: Mapping[str, RuleSet], now: datetime
) -> tuple[tuple[HomeIndexDay, ...], tuple[DayPanel, ...]]:
    """7일 공온지수와 날마다의 공종별 요약(주간 계산은 현장당 한 번, 작업 조회 한 번)."""
    weeks = [(s, _week(session, s, rule_sets, now)) for s in sites]
    index_days = _index_days(weeks)
    if not weeks:
        return index_days, ()
    days = [d.day for d in weeks[0][1].days]
    site_ids = [s.site_id for s in sites]
    items = schedules_service.items_between_for_sites(session, site_ids, days[0], days[-1])
    companies = teams_service.company_names(session, site_ids)
    verdicts: dict[tuple[int, str], list[str]] = {}
    for _, week in weeks:
        for row in week.rows:
            for n, cell in enumerate(row.cells):
                if cell.verdict:
                    verdicts.setdefault((n, row.work_type), []).append(cell.verdict)
    single = len(sites) == 1
    panels: list[DayPanel] = []
    for n, day in enumerate(days):
        on_day = [i for i in items if i.work_date == day]
        rows: list[DayTypeRow] = []
        for work_type in sorted({i.work_type for i in on_day}):
            group = [i for i in on_day if i.work_type == work_type]
            names = list(dict.fromkeys(
                companies[i.performing_participant_id] for i in group
                if i.performing_participant_id in companies
            ))  # fmt: skip
            found = verdicts.get((n, work_type), [])
            worst = min(found, key=lambda v: _VERDICT_RANK.get(v, 9)) if found else None
            prefix = f"/schedule?site_id={site_ids[0]}&" if single else "/schedule?"
            rows.append(
                DayTypeRow(
                    work_type=work_type,
                    time_text=f"{min(i.start_local for i in group):%H:%M}–"
                    f"{max(i.end_local for i in group):%H:%M}",
                    companies_text="업체 미정"
                    if not names
                    else names[0] + (f" 외 {len(names) - 1}" if len(names) > 1 else ""),
                    count=len(group),
                    verdict=worst,
                    href=f"{prefix}month={day:%Y-%m}&day={day.isoformat()}",
                )
            )
        rows.sort(key=lambda r: (_VERDICT_RANK.get(r.verdict or "", 2.5), r.work_type))
        tally = {v: sum(r.count for r in rows if r.verdict == v) for v in _VERDICT_RANK}
        panels.append(
            DayPanel(
                label="내일" if n == 0 else index_days[n].label,
                total=len(on_day),
                go=tally["진행"],
                check=tally["확인 필요"],
                stop=tally["중지 검토"],
                rows=tuple(rows),
                href=index_days[n].href,
            )
        )
    return index_days, tuple(panels)


def _index_days(
    weeks: list[tuple[SiteRecord, WeekView]],
) -> tuple[HomeIndexDay, ...]:
    """내일부터 7일 공온지수. 현장이 여럿이면 점수가 있는 현장의 평균(D-078)."""
    if not weeks:
        return ()
    days: list[HomeIndexDay] = []
    for n, first in enumerate(weeks[0][1].days):
        scored = [(index, s) for s, w in weeks if (index := w.days[n].index) is not None]
        if scored:
            # 현장이 여럿이면 점수가 있는 현장의 평균(개발자 요청 2026-10-17, D-078)
            several = len(weeks) > 1
            score = round(sum(i.score for i, _ in scored) / len(scored))
            days.append(
                HomeIndexDay(
                    label=first.label,
                    short=f"{_WEEKDAYS[first.day.weekday()]} {first.day.day}",
                    is_tomorrow=first.is_tomorrow,
                    score=score,
                    sub=f"현장 {len(scored)}곳" if several else "",
                    href="/dashboard" if several else dashboard_href(scored[0][1].site_id),
                    reference=any(i.mid_reference for i, _ in scored),
                )
            )
        else:
            confidence = next((w.days[n].confidence for _, w in weeks if w.days[n].in_period),
                              first.confidence)  # fmt: skip
            days.append(HomeIndexDay(
                label=first.label, short=f"{_WEEKDAYS[first.day.weekday()]} {first.day.day}",
                is_tomorrow=first.is_tomorrow, score=None,
                sub=_NO_SCORE.get(confidence, confidence),
                href=dashboard_href(weeks[0][0].site_id),
            ))  # fmt: skip
    return tuple(days)


def _check_boards(
    session: Session,
    sites: Sequence[SiteRecord],
    latest_by_site: dict[int, dict[str, Judgment]],
    rule_sets: Mapping[str, RuleSet],
    now: datetime,
) -> tuple[tuple[DayBoard, ...], tuple[HomeDay, ...]]:
    """오늘·내일 점검판과 오늘부터 7일 미리보기(작업 1회·변경 1회·업체 2회 조회).

    날씨는 내일만 본다(판정 범위 D-041·D-061). 오늘·그 뒤 날은 날씨를 빼고 나머지 항목만 확인한다.
    """
    local = now.astimezone(KST)
    today = local.date()
    tomorrow = today + timedelta(days=1)
    last = today + timedelta(days=WEEK_DAYS_HOME - 1)
    names = {s.site_id: s.name for s in sites}
    site_by_id = {s.site_id: s for s in sites}
    items = schedules_service.items_between_for_sites(session, list(names), today, last)
    open_changes = changes_service.open_change_item_ids(session, [i.item_id for i in items])
    companies = teams_service.company_names(session, list({i.site_id for i in items}))
    weather: dict[int, str | None] = {}
    for site_id in {i.site_id for i in items if i.work_date == tomorrow}:
        day_items = tuple(i for i in items if i.site_id == site_id and i.work_date == tomorrow)
        triples = _current_pairs(site_by_id[site_id], _targets(day_items), tomorrow,
                                 latest_by_site.get(site_id, {}), rule_sets)  # fmt: skip
        for target, card, _ in _folded(triples, rule_sets):
            if target.item_id is not None:
                weather[target.item_id] = card.verdict

    def issues(i: WorkItemRecord) -> tuple[CheckIssue, ...]:
        found: list[CheckIssue] = []
        if i.work_date == tomorrow:
            verdict = weather.get(i.item_id)
            if verdict is None:
                found.append(CheckIssue("weather", "날씨 판정 전"))
            elif verdict not in _WEATHER_OK:
                found.append(CheckIssue("weather", f"날씨 {verdict}"))
        if i.performing_participant_id is None:
            found.append(CheckIssue("company", "실행 업체 미지정"))
        clash = next(
            (o for o in items
             if o.item_id != i.item_id and o.site_id == i.site_id and o.work_date == i.work_date
             and o.location and o.location == i.location
             and o.start_local < i.end_local and i.start_local < o.end_local),
            None,
        )  # fmt: skip
        if clash is not None:
            found.append(CheckIssue("overlap", f"{clash.work_type}와 같은 곳·같은 시간"))
        if i.item_id in open_changes:
            found.append(CheckIssue("change", "변경 검토 중"))
        return tuple(found)

    checked = {i.item_id: issues(i) for i in items}

    def board_item(i: WorkItemRecord) -> BoardItem:
        phase: Literal["before", "now", "done"] | None = None
        if i.work_date == today:
            phase = (
                "before" if local.time() < i.start_local
                else "done" if local.time() >= i.end_local
                else "now"
            )  # fmt: skip
        return BoardItem(
            item_id=i.item_id,
            site_name=names[i.site_id],
            work_type=i.work_type,
            time_text=f"{i.start_local:%H:%M}–{i.end_local:%H:%M}",
            location=i.location,
            company=""
            if i.performing_participant_id is None
            else companies.get(i.performing_participant_id, ""),
            href=f"/schedule?site_id={i.site_id}&day={i.work_date.isoformat()}",
            issues=checked[i.item_id],
            phase=phase,
            phase_label="" if phase is None else _PHASE_LABELS[phase],
            progress_pct=0
            if phase is None
            else _progress(local.time(), i.start_local, i.end_local),
            weather=weather.get(i.item_id) if i.work_date == tomorrow else None,
        )

    def board(key: Literal["today", "tomorrow"], title: str, day: date) -> DayBoard:
        day_items = [i for i in items if i.work_date == day]
        rows = tuple(board_item(i) for i in day_items)
        criteria = tuple(
            (label, n)
            for k, label in CHECK_LABELS.items()
            if (n := sum(1 for r in rows if any(x.key == k for x in r.issues)))
        )
        return DayBoard(key, title, _date_text(day), rows, criteria)

    week = tuple(
        HomeDay(
            date_text=f"{d.month}/{d.day}({_WEEKDAYS[d.weekday()]})",
            short=f"{_WEEKDAYS[d.weekday()]} {d.day}",
            href=f"/schedule?day={d.isoformat()}",
            works=sum(1 for i in items if i.work_date == d),
            issues=sum(1 for i in items if i.work_date == d and checked[i.item_id]),
            is_today=d == today,
            is_weekend=d.weekday() >= 5,
        )
        for d in (today + timedelta(days=n) for n in range(WEEK_DAYS_HOME))
    )
    return (board("today", "오늘", today), board("tomorrow", "내일", tomorrow)), week


def _progress(now: time, start: time, end: time) -> int:
    span = _minutes(end) - _minutes(start)
    passed = _minutes(now) - _minutes(start)
    return 0 if span <= 0 else max(0, min(100, round(passed * 100 / span)))


def _minutes(at: time) -> int:
    return at.hour * 60 + at.minute


def _site_summary(
    site: SiteRecord,
    latest: dict[str, Judgment],
    rule_sets: Mapping[str, RuleSet],
    target_date: date,
    items: tuple[WorkItemRecord, ...],
) -> SiteSummary:
    in_period = site.works_on(target_date)
    working = in_period and bool(items)

    def summary(
        verdict: str | None, reason: str, judged_at: str | None, cards: tuple[WorkCard, ...] = ()
    ) -> SiteSummary:
        return SiteSummary(
            site_id=site.site_id,
            name=site.name,
            work_hours=_items_span(items),
            work_types=tuple(dict.fromkeys(i.work_type for i in items)),
            verdict=verdict,
            reason=reason,
            detail_href=dashboard_href(site.site_id),
            judged_at=judged_at,
            working=working,
            cards=cards,
        )

    if not in_period:
        return summary(None, f"작업 기간이 아닙니다 · {site.period_text()}", None)
    if not items:
        return summary(
            None, "내일 등록한 작업이 없습니다 · 작업 일정에서 추가하면 판정합니다", None
        )
    triples = _current_pairs(site, _targets(items), target_date, latest, rule_sets)
    cards = tuple(card for _, card, _ in _folded(triples, rule_sets))
    current = [j for _, j, _ in triples if j is not None]
    if not current:
        stale_reason = next((stale for _, _, stale in triples if stale), None)
        return summary(None, stale_reason or "아직 판정하지 않았습니다", None, cards)
    # 현장의 단계는 작업 카드 중 가장 높은 단계(폭염을 합친 단계, 기준 미확인 공종 포함).
    worst = max(
        (c for c in cards if c.verdict is not None), key=lambda c: Verdict(str(c.verdict)).severity
    )
    judged_at = max(j.judged_at for j in current)
    return summary(
        worst.verdict, f"{worst.work_type} · {worst.reason}", _kst_text(judged_at), cards
    )


@dataclass(frozen=True, slots=True)
class _Target:
    """판정 단위 하나: 등록한 작업(S08-1)의 공종, 또는 그 작업 시간의 공통 기준(폭염)."""

    key: str  # 최신 판정을 묶는 키. 작업 "item:<id>", 그 작업의 공통 기준 "item:<id>:<기준>"
    label: str
    work_type: str
    start_local: time
    end_local: time
    item_id: int | None
    companion_of: str | None = None  # 공통 기준이면 합쳐 보일 작업의 key


def _targets(items: tuple[WorkItemRecord, ...]) -> list[_Target]:
    """그날 작업마다 공종 판정과, 같은 시간의 공통 기준(폭염) 판정. 작업이 없으면 판정하지 않는다.

    공통 기준은 따로 보이지 않고 그 작업 카드에 합친다(D-059).
    """
    targets: list[_Target] = []
    for i in items:
        key = f"item:{i.item_id}"
        targets.append(_Target(key, i.label, i.work_type, i.start_local, i.end_local, i.item_id))
        targets += [
            _Target(f"{key}:{c}", i.label, c, i.start_local, i.end_local, i.item_id, key)
            for c in judged_labels(())
        ]
    return targets


def _folded(
    triples: list[tuple[_Target, Judgment | None, str | None]],
    rule_sets: Mapping[str, RuleSet],
) -> list[tuple[_Target, WorkCard, Judgment | None]]:
    """작업마다 (작업 대상, 공통 기준을 합친 카드, 카드 단계를 정한 판정).

    작업 판정이 아직 없거나 재판정이 필요하면 그 상태를 그대로 보인다. 공통 기준이 더 높은 단계면
    그 단계와 사유('폭염 · …')로 바꾼다. 같은 단계면 작업 쪽을 보인다.
    """
    folded: list[tuple[_Target, WorkCard, Judgment | None]] = []
    for target, judgment, stale in triples:
        if target.companion_of is not None:
            continue
        card = _card_for(target, judgment, stale, rule_sets)
        backing = judgment
        if card.verdict is not None:
            for companion, extra, extra_stale in triples:
                if companion.companion_of != target.key or extra is None:
                    continue
                extra_card = _card_for(companion, extra, extra_stale, rule_sets)
                if extra_card.verdict is not None and Verdict(extra_card.verdict).severity > (
                    Verdict(card.verdict).severity
                ):
                    name = companion.work_type.removesuffix("(공통)")
                    card = replace(
                        card,
                        verdict=extra_card.verdict,
                        reason=f"{name} · {extra_card.reason}",
                        detail_href=extra_card.detail_href,
                    )
                    backing = extra
        if backing is None and card.verdict is not None:
            # 기준 미확인 공종은 그 작업의 판정이 폭염뿐이다. 상세는 폭염 판정을 연다.
            backing = next(
                (e for c, e, _ in triples if c.companion_of == target.key and e is not None), None
            )
        folded.append((target, card, backing))
    return folded


def _items_span(items: tuple[WorkItemRecord, ...]) -> str:
    """그날 작업 시간 범위(첫 작업 시작-마지막 작업 끝). 작업이 없으면 빈 문자열."""
    if not items:
        return ""
    start = min(i.start_local for i in items)
    end = max(i.end_local for i in items)
    return f"{start:%H:%M}–{end:%H:%M} · 작업 {len(items)}건"


_CONFIDENCE_NOTE = {
    "높음": "1시간 간격 예보로 작업 시간 전체를 직접 비교",
    # D-053: 성긴 날은 같은 날 가까운 예보값으로 추정하고, 추정 시각은 '확인 필요'까지만 낸다.
    "보통": (
        "예보 간격이 성겨 일부 시각은 같은 날 가까운 예보값으로 추정 · 추정 시각은 확인 필요까지만"
    ),
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
    previous: dict[
        tuple[date, str], Judgment
    ] = {}  # 직전 발표 예보로 낸 판정(공온지수 예보 안정성)
    for j in repository.latest_for_site_between(session, site.site_id, dates[0], dates[-1]):
        key = (j.target_date, _key(j))
        if key not in latest:
            latest[key] = j
        elif key not in previous and j.forecast_issued_at != latest[key].forecast_issued_at:
            previous[key] = j
    pops = forecasts_service.rain_probability_by_run(
        session, [j.forecast_run_id for j in latest.values() if j.forecast_run_id is not None]
    )
    items_by_day = schedules_service.items_between(session, site.site_id, dates[0], dates[-1])
    times = forecasts_service.latest_forecast_times(session, site.grid_nx, site.grid_ny)
    region_id = land_region_for(site.address)
    mid = None if region_id is None else forecasts_service.latest_mid_forecast(session, region_id)

    days: list[WeekDay] = []
    by_type: dict[str, dict[date, WeekCell]] = {}
    for day in dates:
        in_period = site.works_on(day)
        # 등록한 작업만 보여 준다(현장 기본 공종 대체 없음, D-059).
        has_work = day in items_by_day
        day_latest = {key: j for (d, key), j in latest.items() if d == day}
        triples = (
            _current_pairs(site, _targets(items_by_day.get(day, ())), day, day_latest, rule_sets)
            if in_period and has_work else []
        )  # fmt: skip
        pairs = [(t, j) for t, j, _ in triples]
        folded = _folded(triples, rule_sets)
        judged = [j for _, j in pairs if j is not None]
        covered = any(_has_forecast(times, *_work_range(day, t)) for t, _ in pairs)
        confidence = (
            _confidence(in_period, judged, covered) if not in_period or has_work else "작업 없음"
        )
        mid_parts = None if mid is None else mid.days.get(day)
        if confidence == "예보 없음" and mid_parts:
            confidence = "낮음"
        day_cells: list[WeekCell] = []
        mid_works: list[MidWorkInput] = []
        for target, card, _ in folded:
            if confidence == "낮음" and mid_parts:
                cell = _mid_cell(target, rule_sets, mid_parts)
                mid_works.append(_mid_work(target, rule_sets, mid_parts, cell))
            else:
                state: Literal["none", "pending"] = (
                    "pending" if confidence in ("예보 없음", "판정 전") else "none"
                )
                cell = _week_cell(card, state)
            day_cells.append(cell)
            current = by_type.setdefault(target.work_type, {}).get(day)
            if current is None or _rank(cell) > _rank(current):
                by_type[target.work_type][day] = cell
        # 공온지수(D-052). 중기예보 참고 날은 하루 강수확률·날씨로 낸 참고 점수(D-069).
        changed = any(
            (old := previous.get((day, t.key))) is not None
            and j is not None
            and old.verdict != j.verdict
            for t, j in pairs
        )
        index = (
            mid_gongon_index(mid_works)
            if confidence == "낮음"
            else _day_index(judged, day_cells, changed, pops)
        )
        days.append(WeekDay(day, f"{day:%m/%d}({_WEEKDAYS[day.weekday()]})", day == dates[0],
                            in_period, confidence, _CONFIDENCE_NOTE[confidence],
                            index, _index_note(index, confidence)))  # fmt: skip

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


def _mid_work(
    target: "_Target",
    rule_sets: Mapping[str, RuleSet],
    parts: tuple[MidHalfDay, ...],
    cell: WeekCell,
) -> MidWorkInput:
    """중기 참고 칸 → 공온지수 입력. 비·눈 기준이 있는 작업만 그날 가장 높은 강수확률을 쓴다."""
    rule_set = rule_sets.get(target.work_type)
    elements = set() if rule_set is None else {c.element for c in rule_set.conditions}
    pops = [p.rain_probability_pct for p in parts if p.rain_probability_pct is not None]
    rain_sensitive = bool(elements & {Element.PRECIPITATION_MM_PER_H, Element.SNOWFALL_CM_PER_H})
    return MidWorkInput(
        verdict=Verdict(cell.verdict) if cell.verdict is not None else Verdict.UNAVAILABLE,
        rain_probability_pct=max(pops) if rain_sensitive and pops else None,
    )


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
    # 추정 시각은 값(가까운 시각의 값)이 있어도 직접 비교가 아니다(C04-1, D-053).
    estimated = any(ESTIMATED_NOTE in c["reason"] for h in hours for c in h["conditions"])
    return "높음" if all(has_value) and not estimated else "보통"


def _week_cell(card: WorkCard, empty_state: Literal["none", "pending"]) -> WeekCell:
    if card.verdict is None:
        return WeekCell(None, empty_state, None, card.reason)
    return WeekCell(card.verdict, "verdict", card.detail_href, f"{card.work_type} · {card.reason}")


def _day_index(
    judged: list[Judgment],
    cells: list[WeekCell],
    changed: bool,
    pops: Mapping[int, Mapping[datetime, int]],
) -> GongonIndex | None:
    """그날 판정한 작업의 시각별 단계·기준 여유·강수확률과 칸들의 단계로 공온지수(D-052)."""
    hours = [
        _hour_input(h, pops.get(j.forecast_run_id or -1, {}))
        for j in judged
        if not j.failure_reason
        for h in j.hours
    ]
    day_verdicts = [Verdict(c.verdict) for c in cells if c.verdict is not None]
    return gongon_index(hours, day_verdicts, changed)


def _hour_input(hour: Mapping[str, Any], pop_by_time: Mapping[datetime, int]) -> HourInput:
    """저장된 시각 기록 → 공온지수 입력. 기준 여유는 비교한 조건 중 가장 작은 값."""
    margins = [
        m
        for c in hour["conditions"]
        if c.get("threshold") is not None
        and (m := margin_pct(c.get("lower"), c.get("upper"), c["threshold"], c["operator"]))
        is not None
    ]
    rain_sensitive = any(
        c["element"] == Element.PRECIPITATION_MM_PER_H.value for c in hour["conditions"]
    )
    return HourInput(
        verdict=Verdict(hour["verdict"]),
        margin_pct=min(margins) if margins else None,
        rain_probability_pct=pop_by_time.get(_dt(hour["valid_at"])) if rain_sensitive else None,
    )


def _index_note(index: GongonIndex | None, confidence: str) -> str:
    detail = _CONFIDENCE_NOTE[confidence]
    if index is None:
        return detail
    if index.mid_reference:
        parts = [
            f"공온지수 {index.score}(먼 날 예보)",
            "하루 강수확률·날씨만 봄, 먼 예보 10점 감점",
        ]
        if index.rainy_hours:
            parts.append(f"강수확률 30% 이상 작업 {index.rainy_hours}")
        if index.capped_by is not None:
            parts.append(f"'{index.capped_by.value}' 작업이 있어 상한 적용")
        parts.append("단기예보가 나오면 다시 계산")
        return " · ".join(parts)
    parts = [f"공온지수 {index.score}"]
    if index.partial:
        parts.append(f"예보 값이 있는 {index.compared_hours}/{index.total_hours}시각 기준")
    if index.near_threshold_hours:
        parts.append(f"기준에 가까운 시각 {index.near_threshold_hours}")
    if index.rainy_hours:
        parts.append(f"강수확률 30% 이상 시각 {index.rainy_hours}")
    if index.changed:
        parts.append("직전 예보와 판정이 바뀌어 10점 감점")
    if index.capped_by is not None:
        parts.append(f"'{index.capped_by.value}' 작업이 있어 상한 적용")
    parts.append(f"예보 상세도: {detail}")
    return " · ".join(parts)


def _rank(cell: WeekCell) -> int:
    return -1 if cell.verdict is None else Verdict(cell.verdict).severity


def _key(judgment: Judgment) -> str:
    if judgment.work_item_id is not None:
        if judgment.work_type in COMMON_LABELS:
            return f"item:{judgment.work_item_id}:{judgment.work_type}"
        return f"item:{judgment.work_item_id}"
    return judgment.work_type


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


def _current_pairs(
    site: SiteRecord,
    targets: list["_Target"],
    day: date,
    latest: Mapping[str, Judgment],
    rule_sets: Mapping[str, RuleSet],
) -> list[tuple["_Target", Judgment | None, str | None]]:
    """(대상, 현재 판정, 재판정 필요 사유). 입력이 바뀐 판정은 현재 판정으로 쓰지 않는다(C04-1)."""
    triples: list[tuple[_Target, Judgment | None, str | None]] = []
    for target in targets:
        judgment = latest.get(target.key)
        stale = None if judgment is None else _stale_reason(site, target, day, judgment, rule_sets)
        triples.append((target, None if stale else judgment, stale))
    return triples


def _stale_reason(
    site: SiteRecord,
    target: "_Target",
    day: date,
    judgment: Judgment,
    rule_sets: Mapping[str, RuleSet],
) -> str | None:
    """저장된 판정의 입력(격자·작업 시각·기준 버전)이 지금 현장·작업·기준과 다르면 그 사유.

    판정 4단계와 별개 표시다(새 단계 아님). 예전 판정은 기록에 남고 상세 주소로 볼 수 있다.
    """
    changed: list[str] = []
    if (judgment.grid_nx, judgment.grid_ny) != (site.grid_nx, site.grid_ny):
        changed.append("현장 위치")
    if (judgment.work_start_at, judgment.work_end_at) != _work_range(day, target):
        changed.append("작업 시간")
    rule_set = rule_sets.get(target.work_type)
    if rule_set is not None and judgment.rule_version != rule_set.rule_version:
        changed.append("판정 기준")
    if not changed:
        return None
    return f"재판정 필요 · {'·'.join(changed)} 변경 후 아직 판정하지 않음"


def _card_for(
    target: "_Target",
    judgment: Judgment | None,
    stale: str | None,
    rule_sets: Mapping[str, RuleSet],
) -> WorkCard:
    if stale is None or target.work_type not in rule_sets:
        return _card(target.label, judgment, target.work_type in rule_sets)
    time_range = f"{target.start_local:%H:%M}–{target.end_local:%H:%M}"
    return WorkCard(target.label, time_range, None, stale, None)


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
        if judgment is None or judgment.verdict != card.verdict:
            # 기준 없는 작업에는 폭염 판정이 근거로 붙어도 작업의 '확인 필요'가 남는다.
            items.append(NoticeItem(card.work_type, card.verdict, card.reason))
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
        "schema_version": "1.3",
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


def get_detail(session: Session, scope: SiteScope, judgment_id: int) -> DetailView | None:
    """참여하지 않은 현장의 판정은 없는 것과 같다. 삭제한 현장의 판정은 참여자에게 보인다(D-054)."""
    judgment = repository.get(session, judgment_id)
    if judgment is None or (scope is not None and judgment.site_id not in scope):
        return None
    site = sites_service.get_site(session, judgment.site_id, scope)
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


def _history_days(rows: Sequence[Judgment], names: Mapping[int, str]) -> tuple[HistoryDay, ...]:
    """이 쪽의 판정을 대상 날짜 → 현장으로 묶는다.

    rows는 작업별 최신 판정, 날짜·현장·최근 순(repository.page)."""
    days: dict[date, dict[int, list[HistoryRow]]] = {}
    for j in rows:
        row = HistoryRow(
            judgment_id=j.id,
            target_date=f"{j.target_date:%m/%d}({_WEEKDAYS[j.target_date.weekday()]})",
            site_name=names.get(j.site_id, "삭제된 현장"),
            work_type=j.work_type,
            time_range=_range_text(j.work_start_at, j.work_end_at),
            verdict=j.verdict,
            issued="—"
            if j.forecast_issued_at is None
            else f"{j.forecast_issued_at.astimezone(KST):%m/%d %H:%M}",
            rule_version=j.rule_version,
            note=j.failure_reason,
        )
        days.setdefault(j.target_date, {}).setdefault(j.site_id, []).append(row)
    return tuple(
        HistoryDay(
            label=f"{day.month}월 {day.day}일({_WEEKDAYS[day.weekday()]})",
            count=sum(len(site_rows) for site_rows in by_site.values()),
            sites=tuple(
                HistorySite(site_rows[0].site_name, tuple(site_rows))
                for site_rows in by_site.values()
            ),
        )
        for day, by_site in days.items()
    )


def build_history(
    session: Session,
    scope: SiteScope,
    verdict: VerdictFilter,
    site_id: int | None,
    page: int,
    size: int,
) -> HistoryView:
    """size는 HISTORY_PAGE_SIZES 중 하나(라우터가 검증). 범위 밖 site_id는 빈 목록이다."""
    sites = sites_service.list_sites(session, scope)
    names = {s.site_id: s.name for s in sites}
    # 삭제한 현장의 판정은 기록으로 남기되 내역 목록에는 내지 않는다(D-054).
    # 상세 주소로는 열 수 있다.
    active = [s.site_id for s in sites]
    counts = repository.verdict_counts(session, site_id, active)
    verdict_value = None if verdict == "전체" else verdict
    total = sum(counts.values()) if verdict_value is None else counts.get(verdict_value, 0)
    last_page = max(1, -(-total // size))
    shown = repository.page(
        session, site_id, verdict_value, (page - 1) * size, size, site_ids=active
    )

    def href(v: str, p: int) -> str:
        params: dict[str, str | int] = {"verdict": v, "page": p}
        if site_id is not None:
            params["site_id"] = site_id
        if size != HISTORY_PAGE_SIZES[0]:
            params["size"] = size
        return "/judgments?" + urlencode(params)

    return HistoryView(
        days=_history_days(shown, names),
        count=len(shown),
        total=total,
        first_index=(page - 1) * size + 1 if shown else 0,
        size=size,
        size_options=HISTORY_PAGE_SIZES,
        pages=tuple(
            PageLink("…", None) if p is None else PageLink(str(p), href(verdict, p), p == page)
            for p in page_window(page, last_page)
        ),
        visible_rows=HISTORY_VISIBLE_ROWS,
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
        next_href=href(verdict, page + 1) if page < last_page else None,
    )


def page_window(page: int, last: int, around: int = 2) -> list[int | None]:
    """쪽 번호 목록: 처음·끝과 현재 앞뒤 around쪽.

    두 쪽 이상 비면 None('…'), 한 쪽만 비면 그 쪽을 그대로 보인다.
    """
    shown = sorted({1, last, *range(max(1, page - around), min(last, page + around) + 1)})
    out: list[int | None] = []
    for p in shown:
        previous = out[-1] if out else None
        if previous is not None and p - previous == 2:
            out.append(previous + 1)
        elif previous is not None and p - previous > 2:
            out.append(None)
        out.append(p)
    return out


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
