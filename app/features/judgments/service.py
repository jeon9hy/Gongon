"""판정 실행·저장과 화면 모델 만들기. 판정 계산은 engine/judgment.judge만 한다."""

import logging
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.core.rules import rule_sets_by_label
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
    RecentJudgment,
    RunResult,
    SiteOption,
    SiteSummary,
    Tab,
    Tile,
    VerdictFilter,
    WorkCard,
    WorkWindow,
)
from app.features.sites import service as sites_service
from app.features.sites.schemas import SiteRecord
from engine.forecast import HttpGet, KmaAuth
from engine.judgment import (
    ELEMENT_LABEL,
    ELEMENT_UNIT,
    OPERATOR_TEXT,
    Element,
    JudgmentResult,
    RuleSet,
    Verdict,
    judge,
)
from engine.kst import KST

logger = logging.getLogger(__name__)

VERDICT_FILTERS: tuple[VerdictFilter, ...] = ("전체", "진행", "확인 필요", "중지 검토", "판정 불가")
HISTORY_PAGE_SIZE = 30
_WEEKDAYS = "월화수목금토일"
_PLOT_HEIGHT_PX = 200
_MIN_BAR_PX = 6
ELEMENT_KEYS: dict[ElementKey, Element] = {
    "rain": Element.PRECIPITATION_MM_PER_H,
    "wind": Element.WIND_SPEED_MPS,
    "snow": Element.SNOWFALL_CM_PER_H,
}
_KEY_OF = {element: key for key, element in ELEMENT_KEYS.items()}
_ICON = {
    Element.PRECIPITATION_MM_PER_H: "rain",
    Element.WIND_SPEED_MPS: "wind",
    Element.SNOWFALL_CM_PER_H: "snow",
}


# ---------- 실행 ----------


def target_date_for(now: datetime) -> date:
    """판정 대상은 내일(KST)."""
    return now.astimezone(KST).date() + timedelta(days=1)


# 판정 실행 결과 코드 → 대시보드 문구. URL에는 코드만 싣는다(임의 문구 표시 방지).
RUN_MESSAGES: dict[RunResult, str] = {
    "done": "판정했습니다.",
    "failed": "예보를 받지 못해 ‘판정 불가’로 기록했습니다. 데이터 상태에서 원인을 확인하세요.",
    "no_rules": "판정 기준이 있는 공종이 없습니다. 현장 설정에서 철골 작업을 고르세요.",
    "all_done": "전체 현장을 판정했습니다.",
    "no_sites": "등록된 현장이 없습니다. 먼저 현장을 등록하세요.",
}


def run_for_site(
    session: Session, site_id: int, now: datetime, auth: KmaAuth, http_get: HttpGet
) -> RunResult | None:
    """현장의 내일 판정을 내고 저장한다. 없는 현장이면 None."""
    site = sites_service.get_site(session, site_id)
    if site is None:
        return None
    rule_sets = rule_sets_by_label()
    targets = [rule_sets[w] for w in site.work_types if w in rule_sets]
    if not targets:
        return "no_rules"

    target_date = target_date_for(now)
    start_at = datetime.combine(target_date, site.work_start_local, KST)
    end_at = datetime.combine(target_date, site.work_end_local, KST)
    snapshot = forecasts_service.get_forecast(
        session, site.grid_nx, site.grid_ny, now, auth, http_get
    )
    for rule_set in targets:
        if snapshot.weather is None:
            session.add(
                _failed_judgment(site, rule_set, target_date, start_at, end_at, snapshot.run_id,
                                 f"예보 수집 실패: {snapshot.failure_reason}")
            )  # fmt: skip
            continue
        result = judge(snapshot.weather, rule_set, start_at, end_at)
        same = repository.find_same(
            session,
            site_id=site.site_id,
            target_date=target_date,
            work_type=rule_set.work_type_label,
            forecast_issued_at=result.forecast_issued_at,
            rule_version=rule_set.rule_version,
            grid_nx=site.grid_nx,
            grid_ny=site.grid_ny,
            work_start_at=start_at,
            work_end_at=end_at,
        )
        if same is None:
            session.add(_judgment(site, rule_set, target_date, start_at, end_at,
                                  snapshot.run_id, result))  # fmt: skip
    session.commit()
    logger.info("판정 site_id=%s target=%s base_at=%s", site.site_id, target_date, snapshot.base_at)

    return "failed" if snapshot.weather is None else "done"


def run_all(session: Session, now: datetime, auth: KmaAuth, http_get: HttpGet) -> RunResult:
    """모든 현장의 내일 판정. 같은 격자는 예보를 한 번만 받는다(forecasts 재사용)."""
    results = [
        run_for_site(session, s.site_id, now, auth, http_get)
        for s in sites_service.list_sites(session)
    ]
    if not results:
        return "no_sites"
    if "failed" in results:
        return "failed"
    if all(r == "no_rules" for r in results):
        return "no_rules"
    return "all_done"


def _judgment(
    site: SiteRecord,
    rule_set: RuleSet,
    target_date: date,
    start_at: datetime,
    end_at: datetime,
    run_id: int,
    result: JudgmentResult,
) -> Judgment:
    thresholds = {c.id: (c.threshold, c.operator) for c in rule_set.conditions}
    return Judgment(
        site_id=site.site_id,
        target_date=target_date,
        work_type=rule_set.work_type_label,
        work_start_at=start_at,
        work_end_at=end_at,
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
) -> Judgment:
    return Judgment(
        site_id=site.site_id,
        target_date=target_date,
        work_type=rule_set.work_type_label,
        work_start_at=start_at,
        work_end_at=end_at,
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
) -> DashboardView | None:
    """현장이 없으면 빈 대시보드, 없는 site_id면 None."""
    message = None if ran is None else RUN_MESSAGES[ran]
    sites = sites_service.list_sites(session)
    target_date = target_date_for(now)
    if not sites:
        return _empty_dashboard(target_date)
    site = sites[0] if site_id is None else next((s for s in sites if s.site_id == site_id), None)
    if site is None:
        return None

    latest: dict[str, Judgment] = {}
    for j in repository.latest_for_site_date(session, site.site_id, target_date):
        latest.setdefault(j.work_type, j)
    rule_sets = rule_sets_by_label()
    cards = tuple(_card(w, latest.get(w), w in rule_sets) for w in site.work_types)
    primary_j = next((latest[w] for w in site.work_types if w in latest), None)

    return DashboardView(
        sites=tuple(SiteOption(s.site_id, s.name, s.site_id == site.site_id) for s in sites),
        site_id=site.site_id,
        site_name=site.name,
        target_date=_date_text(target_date),
        work_hours=f"{site.work_start_local:%H:%M}–{site.work_end_local:%H:%M}",
        cards=cards,
        primary=None if primary_j is None else _primary(primary_j, site.site_id, element_key, hour),
        forecast_issued=None
        if primary_j is None or primary_j.forecast_issued_at is None
        else _kst_text(primary_j.forecast_issued_at),
        rule_version=None if primary_j is None else primary_j.rule_version,
        rule_verified=primary_j is not None and primary_j.rule_source_verified,
        collection_status=_collection_status(primary_j),
        judged_at=None if primary_j is None else _kst_text(primary_j.judged_at),
        grid=f"({site.grid_nx}, {site.grid_ny})",
        notice=_notice(site, target_date, cards, latest),
        message=message,
        message_is_error=ran not in (None, "done"),
    )


def build_home(session: Session, now: datetime, ran: RunResult | None = None) -> HomeView:
    """전체 현장의 내일 판정 개요. 현장 수와 관계없이 판정 조회는 한 번만 한다."""
    target_date = target_date_for(now)
    sites = sites_service.list_sites(session)
    by_site: dict[int, dict[str, Judgment]] = {}
    for j in repository.latest_for_sites_date(session, [s.site_id for s in sites], target_date):
        by_site.setdefault(j.site_id, {}).setdefault(j.work_type, j)
    rule_sets = rule_sets_by_label()
    summaries = tuple(_site_summary(s, by_site.get(s.site_id, {}), rule_sets) for s in sites)

    counts = {v.value: 0 for v in (Verdict.STOP_REVIEW, Verdict.CHECK, Verdict.UNAVAILABLE,
                                   Verdict.GO)}  # fmt: skip
    not_judged = 0
    for summary in summaries:
        if summary.verdict is None:
            not_judged += 1
        else:
            counts[summary.verdict] += 1
    tiles = (
        *(CountTile(v, n, v) for v, n in counts.items()),
        CountTile("판정 전", not_judged, None),
    )

    names = {s.site_id: s.name for s in sites}
    recent = tuple(
        RecentJudgment(
            href=f"/judgments/{j.id}",
            site_name=names.get(j.site_id, "삭제된 현장"),
            work=f"{j.work_type} {_range_text(j.work_start_at, j.work_end_at)}",
            verdict=j.verdict,
            when=f"{j.target_date:%m/%d} 대상 · {_kst_text(j.judged_at)} 판정",
        )
        for j in repository.page(session, None, None, 0, 5)
    )
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
        message=None if ran is None else RUN_MESSAGES[ran],
        message_is_error=ran in ("failed", "no_rules", "no_sites"),
    )


def _site_summary(
    site: SiteRecord, latest: dict[str, Judgment], rule_sets: Mapping[str, RuleSet]
) -> SiteSummary:
    def summary(verdict: str | None, reason: str, judged_at: str | None) -> SiteSummary:
        return SiteSummary(
            site_id=site.site_id,
            name=site.name,
            work_hours=f"{site.work_start_local:%H:%M}–{site.work_end_local:%H:%M}",
            work_types=" · ".join(site.work_types),
            verdict=verdict,
            reason=reason,
            detail_href=dashboard_href(site.site_id),
            judged_at=judged_at,
        )

    if not any(w in latest for w in site.work_types):
        return summary(None, "아직 판정하지 않았습니다", None)
    # 현장의 단계는 공종 카드 중 가장 높은 단계(기준 미확인 공종의 '확인 필요' 포함).
    cards = [_card(w, latest.get(w), w in rule_sets) for w in site.work_types]
    worst = max(
        (c for c in cards if c.verdict is not None), key=lambda c: Verdict(str(c.verdict)).severity
    )
    judged_at = max(j.judged_at for j in latest.values())
    return summary(worst.verdict, f"{worst.work_type} · {worst.reason}", _kst_text(judged_at))


def dashboard_href(site_id: int, **params: str | int) -> str:
    """현장별 대시보드 주소. 홈(/)과 별도 화면이다."""
    return "/dashboard?" + urlencode({"site_id": site_id, **params})


def _empty_dashboard(target_date: date) -> DashboardView:
    return DashboardView(
        sites=(), site_id=None, site_name="", target_date=_date_text(target_date), work_hours="",
        cards=(), primary=None, forecast_issued=None, rule_version=None, rule_verified=False,
        collection_status="현장 등록 전", judged_at=None, grid="—", notice=None, message=None,
        message_is_error=False,
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
        return WorkCard(work_type, time_range, judgment.verdict, "모든 시간 기준 미만", href)
    worst = max(flagged, key=lambda w: Verdict(w["verdict"]).severity)
    reason = _window_reason(judgment.hours, worst)
    window_text = _range_text(_dt(worst["start_at"]), _dt(worst["end_at"]))
    return WorkCard(work_type, time_range, judgment.verdict, f"{window_text} · {reason}", href)


def _primary(
    judgment: Judgment, site_id: int, element_key: ElementKey | None, hour: int | None
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
        chart=_chart(judgment, site_id, element_key, hour),
        failure_reason=judgment.failure_reason,
    )


def _chart(
    judgment: Judgment, site_id: int, element_key: ElementKey | None, hour: int | None
) -> Chart | None:
    if not judgment.hours:
        return None
    elements = [Element(c["element"]) for c in judgment.hours[0]["conditions"]]
    element = ELEMENT_KEYS.get(element_key) if element_key else None
    if element not in elements:
        element = _deciding_element(judgment.hours, elements)
    entries = [(_dt(h["valid_at"]), _entry(h, element)) for h in judgment.hours]
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
        over = e is not None and e["verdict"] == Verdict.STOP_REVIEW.value
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
                href=href_for(site_id, key, t.hour),
            )
        )
    threshold_text = f"{threshold:g} {unit} {OPERATOR_TEXT[operator]}"
    return Chart(
        title=f"시간대별 예보 · {judgment.work_type} 기준",
        tabs=tuple(
            Tab(ELEMENT_LABEL[e], href_for(site_id, _KEY_OF[e], selected_hour), e == element)
            for e in elements
        ),
        bars=tuple(bars),
        selected_value=selected_text,
        selected_caption=(
            f"{selected_hour:02d}:00 {label} 예보 · 기준 {threshold_text}이면 중지 검토"
        ),
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


def href_for(site_id: int, key: ElementKey, hour: int) -> str:
    # #chart: 스크립트 없이 새로 불러와도 그래프 위치로 이동한다(스크립트가 있으면 카드만 교체).
    return dashboard_href(site_id, element=key, hour=hour) + "#chart"


def _entry(hour_json: dict[str, Any], element: Element) -> dict[str, Any] | None:
    return next((c for c in hour_json["conditions"] if c["element"] == element.value), None)


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
    site: SiteRecord, target_date: date, cards: tuple[WorkCard, ...], latest: dict[str, Judgment]
) -> Notice | None:
    """알림 문구 미리보기. 실제 발송은 사업자 등록 후(D-015)."""
    if not latest:
        return None
    items = []
    for card in cards:
        if card.verdict is None or card.verdict == Verdict.GO.value:
            continue
        judgment = latest.get(card.work_type)
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
    first = next(iter(latest.values()))
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


def get_detail(session: Session, judgment_id: int) -> DetailView | None:
    judgment = repository.get(session, judgment_id)
    if judgment is None:
        return None
    site = sites_service.get_site(session, judgment.site_id)
    elements = (
        [Element(c["element"]) for c in judgment.hours[0]["conditions"]] if judgment.hours else []
    )
    chips = ["자료 유형: 예보 (현장 관측 아님)"]
    if judgment.forecast_issued_at is not None:
        chips.append(f"예보 발표 {_iso_kst(judgment.forecast_issued_at)}")
    chips += [
        f"판정 시각 {_iso_kst(judgment.judged_at)}",
        f"기준 버전 {judgment.rule_version}",
        f"기상청 격자 ({judgment.grid_nx}, {judgment.grid_ny})",
    ]
    return DetailView(
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
    first = present[0][1]
    return CriterionCard(
        label=ELEMENT_LABEL[element],
        icon=_ICON[element],
        verdict=verdict.value,
        peak_value="없음" if peak is None else _value_text(peak[1], unit).removesuffix(f" {unit}"),
        unit=unit,
        peak_time=None if peak is None else f"{peak[0]:%H:%M}",
        rule_text=f"기준: {float(first['threshold']):g} {unit} "
        f"{OPERATOR_TEXT[first['operator']]} → 중지 검토",
        source=judgment.rule_source,
        source_verified=judgment.rule_source_verified,
    )


def _hour_row(hour_json: dict[str, Any], elements: list[Element]) -> HourRow:
    cells = []
    for element in elements:
        e = _entry(hour_json, element)
        text = "없음" if e is None or e["lower"] is None else _value_text(e, "").strip()
        cells.append(Cell(text, e is not None and e["verdict"] == Verdict.STOP_REVIEW.value))
    verdict = hour_json["verdict"]
    if verdict == Verdict.GO.value:
        calculation = "모든 요소 기준 미만"
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
