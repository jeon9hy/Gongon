"""현장 게시 화면(C11, D-067).

- 휴게실 TV·태블릿용. 그 현장의 오늘·내일 작업(시간·공종·위치·업체), 오늘 확정된 변경,
  내일 날씨 한 줄, '작업 여부는 반장·소장 지시를 따릅니다'만 보인다.
- 연락처·메모·조치 내용·다른 현장은 보이지 않는다. 게시·조정자·담당자·열람자가 열 수 있다.
"""

from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.formats import day_text
from app.features.auth.schemas import CurrentUser
from app.features.board.schemas import BoardItem, BoardView
from app.features.changes import service as changes_service
from app.features.judgments import service as judgments_service
from app.features.schedules import service as schedules_service
from app.features.sites import service as sites_service
from app.features.teams import service as teams_service
from app.features.teams.schemas import BOARD_ROLES
from engine.kst import KST


def build_board(session: Session, user: CurrentUser, site_id: int, now: datetime) -> BoardView:
    teams_service.require_role(session, user, site_id, BOARD_ROLES)
    site = sites_service.get_site(session, site_id, None)
    if site is None:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다")
    local = now.astimezone(KST)
    today = local.date()
    tomorrow = today + timedelta(days=1)
    items = schedules_service.items_between_for_sites(session, [site_id], today, tomorrow)
    companies = teams_service.company_names(session, [site_id])

    def rows(day: date) -> tuple[BoardItem, ...]:
        on_day = sorted((i for i in items if i.work_date == day), key=lambda i: i.start_local)
        return tuple(
            BoardItem(
                time_text=f"{i.start_local:%H:%M}–{i.end_local:%H:%M}",
                work_type=i.work_type,
                location=i.location,
                company=companies.get(i.performing_participant_id or -1, ""),
                phase=_phase(local.time(), i.start_local, i.end_local) if day == today else "",
            )
            for i in on_day
        )

    start = datetime.combine(today, time(0), KST)
    home = judgments_service.build_home(session, frozenset({site_id}), now)
    summary = next((s for s in home.sites if s.site_id == site_id), None)
    weather = None
    if summary is not None and summary.working:
        weather = (
            f"내일 공온 판정 · {summary.verdict}"
            if summary.verdict
            else "내일 공온 판정 · 아직 판정 전"
        )
    return BoardView(
        site_id=site_id,
        site_name=site.name,
        today_text=day_text(today),
        tomorrow_text=day_text(tomorrow),
        today=rows(today),
        tomorrow=rows(tomorrow),
        changes=changes_service.confirmed_between(
            session, site_id, start, start + timedelta(days=1)
        ),
        weather_text=weather,
        updated_text=f"{local:%H:%M} 기준",
    )


def _phase(now: time, start: time, end: time) -> str:
    if now >= end:
        return "끝남"
    if now >= start:
        return "진행 중"
    return "예정"
