"""현장 등록·수정·삭제·조회. 다른 기능은 list_sites·get_site로 읽는다(삭제한 현장은 빠진다).

조회는 항상 SiteScope(참여 현장)로 제한하고, 수정·삭제는 조정자만 한다(teams, D-057).
"""

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.features.auth.schemas import CurrentUser
from app.features.sites import repository
from app.features.sites.models import Site
from app.features.sites.schemas import (
    SiteForm,
    SiteInput,
    SiteListItem,
    SiteRecord,
    SiteScope,
    SitesView,
)
from app.features.teams import service as teams_service
from app.features.teams.schemas import MANAGE_ROLES
from engine.geo import GridConversionError, latlon_to_kma_grid

NAME_MAX = 60
ADDRESS_MAX = 200


def list_sites(session: Session, scope: SiteScope) -> tuple[SiteRecord, ...]:
    return tuple(_record(s) for s in repository.list_sites(session, scope))


def get_site(session: Session, site_id: int, scope: SiteScope) -> SiteRecord | None:
    site = repository.get_site(session, site_id, scope)
    return None if site is None else _record(site)


def build_sites_view(
    session: Session,
    user: CurrentUser,
    site_id: int | None,
    form: SiteForm | None = None,
    errors: tuple[str, ...] = (),
    saved: bool = False,
    today: date | None = None,
    deleted: bool = False,
) -> SitesView | None:
    """site_id가 없으면 새 현장 등록 화면, 없는 현장이면 None. today는 새 현장 기본 작업 기간용."""
    records = list_sites(session, teams_service.site_ids_for(session, user.user_id))
    selected = None
    if site_id is not None:
        selected = next((r for r in records if r.site_id == site_id), None)
        if selected is None:
            return None
    if form is None:
        form = _new_form(today) if selected is None else _form_from(selected)
    items = tuple(
        SiteListItem(
            href=f"/sites?site_id={r.site_id}",
            name=r.name,
            address=r.address,
            period=_short_period(r),
            selected=r.site_id == site_id,
        )
        for r in records
    )
    return SitesView(
        items=items,
        site_id=site_id,
        form=form,
        grid_text=None if selected is None else f"({selected.grid_nx}, {selected.grid_ny})",
        errors=errors,
        saved=saved,
        deleted=deleted,
        can_edit=selected is None
        or teams_service.role_on(session, user.user_id, selected.site_id) in MANAGE_ROLES,
    )


def create_site(
    session: Session, form: SiteForm, founder: CurrentUser, now: datetime
) -> tuple[int | None, tuple[str, ...]]:
    """만든 사람의 회사가 원청, 본인이 조정자가 된다. 현장과 참여 기록은 한 번에 저장한다."""
    data, errors = validate(form)
    if data is None:
        return None, errors
    site = repository.add_site(session, data)
    teams_service.add_founder(session, site.id, founder, now)
    session.commit()
    return site.id, ()


def update_site(
    session: Session, user: CurrentUser, site_id: int, form: SiteForm
) -> tuple[bool, tuple[str, ...]]:
    """(현장 존재 여부, 검증 오류). 비참여는 404, 조정자가 아니면 403(teams)."""
    teams_service.require_role(session, user, site_id, MANAGE_ROLES)
    site = repository.get_site(session, site_id, None)
    if site is None:
        return False, ()
    data, errors = validate(form)
    if data is None:
        return True, errors
    repository.update_site(site, data)
    session.commit()
    return True, ()


def delete_site(session: Session, user: CurrentUser, site_id: int, now: datetime) -> bool:
    """현장을 목록·판정 대상에서 뺀다. 판정 내역·작업 일정 행은 기록으로 남긴다(D-040).
    없거나 이미 삭제한 현장이면 False. 조정자만 삭제한다."""
    teams_service.require_role(session, user, site_id, MANAGE_ROLES)
    site = repository.get_site(session, site_id, None)
    if site is None:
        return False
    repository.mark_deleted(site, now)
    session.commit()
    return True


def validate(form: SiteForm) -> tuple[SiteInput | None, tuple[str, ...]]:
    errors: list[str] = []
    road_address = form.road_address.strip()
    lot_address = form.lot_address.strip()
    address = road_address or lot_address
    if not address:
        errors.append(
            "도로명 주소나 지번 주소 중 하나는 입력하세요. [주소 찾기]로 고를 수 있습니다."
        )
    elif max(len(road_address), len(lot_address)) > ADDRESS_MAX:
        errors.append(f"주소는 {ADDRESS_MAX}자 이하로 입력하세요.")
    # 현장 이름은 선택이다. 비우면 주소를 이름으로 쓴다(목록·알림에 표시할 이름이 필요).
    name = form.name.strip() or address[:NAME_MAX]
    if len(name) > NAME_MAX:
        errors.append(f"현장 이름은 {NAME_MAX}자 이하로 입력하세요.")

    latitude = _float(form.latitude)
    longitude = _float(form.longitude)
    grid = None
    if latitude is None or longitude is None:
        errors.append("위도·경도를 숫자로 입력하세요. 예: 37.5665, 126.9780")
    else:
        try:
            grid = latlon_to_kma_grid(latitude, longitude)
        except GridConversionError:
            errors.append("이 위치는 기상청 단기예보 범위 밖입니다. 위도·경도를 확인하세요.")

    start_date = _date(form.work_start_date)
    end_date = _date(form.work_end_date)
    if start_date is None or end_date is None:
        errors.append("작업 기간(시작일·종료일)을 입력하세요.")
    elif start_date > end_date:
        errors.append("작업 기간의 종료일은 시작일과 같거나 늦어야 합니다.")

    if errors or grid is None:
        return None, tuple(errors)
    assert start_date is not None and end_date is not None
    assert latitude is not None and longitude is not None
    return (
        SiteInput(
            name=name,
            address=address,
            road_address=road_address,
            lot_address=lot_address,
            latitude_deg=latitude,
            longitude_deg=longitude,
            grid_nx=grid.nx,
            grid_ny=grid.ny,
            work_start_date=start_date,
            work_end_date=end_date,
        ),
        (),
    )


def _float(raw: str) -> float | None:
    try:
        value = float(raw.strip())
    except ValueError:
        return None
    return value if value == value else None  # NaN 거부


def _date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def _new_form(today: date | None) -> SiteForm:
    if today is None:
        return SiteForm()
    # 새 현장은 오늘부터 30일을 기본 작업 기간으로 채워 둔다(바꿀 수 있음).
    return SiteForm(
        work_start_date=today.isoformat(),
        work_end_date=(today + timedelta(days=30)).isoformat(),
    )


def _short_period(record: SiteRecord) -> str | None:
    """목록용 짧은 기간. 끝 날짜는 시작과 같은 해면 연도를 뺀다."""
    start, end = record.work_start_date, record.work_end_date
    if start is None and end is None:
        return None
    start_text = "" if start is None else f"{start:%y.%m.%d}"
    if end is None:
        end_text = ""
    elif start is not None and end.year == start.year:
        end_text = f"{end:%m.%d}"
    else:
        end_text = f"{end:%y.%m.%d}"
    return f"{start_text} – {end_text}"


def _record(site: Site) -> SiteRecord:
    return SiteRecord(
        site_id=site.id,
        name=site.name,
        address=site.address,
        road_address=site.road_address,
        lot_address=site.lot_address,
        latitude_deg=site.latitude_deg,
        longitude_deg=site.longitude_deg,
        grid_nx=site.grid_nx,
        grid_ny=site.grid_ny,
        work_start_date=site.work_start_date,
        work_end_date=site.work_end_date,
    )


def _form_from(record: SiteRecord) -> SiteForm:
    return SiteForm(
        name=record.name,
        road_address=record.road_address,
        lot_address=record.lot_address,
        latitude=f"{record.latitude_deg:.6g}",
        longitude=f"{record.longitude_deg:.7g}",
        work_start_date=""
        if record.work_start_date is None
        else record.work_start_date.isoformat(),
        work_end_date="" if record.work_end_date is None else record.work_end_date.isoformat(),
    )
