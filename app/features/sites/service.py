"""현장 등록·수정·조회. 다른 기능은 list_sites·get_site로 현장 정보를 읽는다."""

from datetime import date, time, timedelta

from sqlalchemy.orm import Session

from app.core.rules import WORK_TYPE_LABELS, rule_sets_by_label
from app.features.sites import repository
from app.features.sites.models import Site
from app.features.sites.schemas import (
    BasisStatus,
    SiteForm,
    SiteInput,
    SiteListItem,
    SiteRecord,
    SitesView,
    WorkTypeOption,
)
from engine.geo import GridConversionError, latlon_to_kma_grid

NAME_MAX = 60
ADDRESS_MAX = 200


def list_sites(session: Session) -> tuple[SiteRecord, ...]:
    return tuple(_record(s) for s in repository.list_sites(session))


def get_site(session: Session, site_id: int) -> SiteRecord | None:
    site = repository.get_site(session, site_id)
    return None if site is None else _record(site)


def build_sites_view(
    session: Session,
    site_id: int | None,
    form: SiteForm | None = None,
    errors: tuple[str, ...] = (),
    saved: bool = False,
    today: date | None = None,
) -> SitesView | None:
    """site_id가 없으면 새 현장 등록 화면, 없는 현장이면 None. today는 새 현장 기본 작업 기간용."""
    records = list_sites(session)
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
            hours=f"{_hhmm(r.work_start_local)}–{_hhmm(r.work_end_local)}",
            period=_short_period(r),
            work_types=r.work_types,
            selected=r.site_id == site_id,
        )
        for r in records
    )
    options = tuple(
        WorkTypeOption(label, basis_status(label), label in form.work_types)
        for label in WORK_TYPE_LABELS
    )
    return SitesView(
        items=items,
        site_id=site_id,
        form=form,
        grid_text=None if selected is None else f"({selected.grid_nx}, {selected.grid_ny})",
        work_type_options=options,
        errors=errors,
        saved=saved,
    )


def create_site(session: Session, form: SiteForm) -> tuple[int | None, tuple[str, ...]]:
    data, errors = validate(form)
    if data is None:
        return None, errors
    site = repository.add_site(session, data)
    session.commit()
    return site.id, ()


def update_site(session: Session, site_id: int, form: SiteForm) -> tuple[bool, tuple[str, ...]]:
    """(현장 존재 여부, 검증 오류)."""
    site = repository.get_site(session, site_id)
    if site is None:
        return False, ()
    data, errors = validate(form)
    if data is None:
        return True, errors
    repository.update_site(site, data)
    session.commit()
    return True, ()


def basis_status(label: str) -> BasisStatus:
    rule_set = rule_sets_by_label().get(label)
    if rule_set is None:
        return "기준 미확인"
    return "판정 · 원문 확인됨" if rule_set.source_verified else "판정 · 원문 대조 필요"


def validate(form: SiteForm) -> tuple[SiteInput | None, tuple[str, ...]]:
    errors: list[str] = []
    address = form.address.strip()
    if not address or len(address) > ADDRESS_MAX:
        errors.append(
            f"주소를 1~{ADDRESS_MAX}자로 입력하세요. 주소 칸에서 장소를 찾아 고를 수 있습니다."
        )
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

    start = _time(form.work_start)
    end = _time(form.work_end)
    if start is None or end is None:
        errors.append("작업 시간을 00:00 형식으로 입력하세요.")
    elif start >= end:
        errors.append("작업 종료는 시작보다 늦어야 합니다(같은 날 안에서).")

    start_date = _date(form.work_start_date)
    end_date = _date(form.work_end_date)
    if start_date is None or end_date is None:
        errors.append("작업 기간(시작일·종료일)을 입력하세요.")
    elif start_date > end_date:
        errors.append("작업 기간의 종료일은 시작일과 같거나 늦어야 합니다.")

    unknown = [w for w in form.work_types if w not in WORK_TYPE_LABELS]
    if unknown:
        errors.append(f"알 수 없는 공종: {', '.join(unknown)}")
    if not form.work_types:
        errors.append("공종을 하나 이상 고르세요.")

    if errors or grid is None or start is None or end is None:
        return None, tuple(errors)
    assert start_date is not None and end_date is not None
    assert latitude is not None and longitude is not None
    return (
        SiteInput(
            name=name,
            address=address,
            latitude_deg=latitude,
            longitude_deg=longitude,
            grid_nx=grid.nx,
            grid_ny=grid.ny,
            work_start_local=start,
            work_end_local=end,
            work_types=tuple(w for w in WORK_TYPE_LABELS if w in form.work_types),
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


def _time(raw: str) -> time | None:
    try:
        return time.fromisoformat(raw.strip())
    except ValueError:
        return None


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


def _hhmm(value: time) -> str:
    return value.strftime("%H:%M")


def _record(site: Site) -> SiteRecord:
    return SiteRecord(
        site_id=site.id,
        name=site.name,
        address=site.address,
        latitude_deg=site.latitude_deg,
        longitude_deg=site.longitude_deg,
        grid_nx=site.grid_nx,
        grid_ny=site.grid_ny,
        work_start_local=site.work_start_local,
        work_end_local=site.work_end_local,
        work_types=tuple(site.work_types),
        work_start_date=site.work_start_date,
        work_end_date=site.work_end_date,
    )


def _form_from(record: SiteRecord) -> SiteForm:
    return SiteForm(
        name=record.name,
        address=record.address,
        latitude=f"{record.latitude_deg:.6g}",
        longitude=f"{record.longitude_deg:.7g}",
        work_start=_hhmm(record.work_start_local),
        work_end=_hhmm(record.work_end_local),
        work_types=record.work_types,
        work_start_date=""
        if record.work_start_date is None
        else record.work_start_date.isoformat(),
        work_end_date="" if record.work_end_date is None else record.work_end_date.isoformat(),
    )
