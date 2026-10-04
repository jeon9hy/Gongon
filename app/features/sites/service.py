"""현장 등록·수정·조회. 다른 기능은 list_sites·get_site로 현장 정보를 읽는다."""

from datetime import time

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
) -> SitesView | None:
    """site_id가 없으면 새 현장 등록 화면. 없는 현장이면 None."""
    records = list_sites(session)
    selected = None
    if site_id is not None:
        selected = next((r for r in records if r.site_id == site_id), None)
        if selected is None:
            return None
    if form is None:
        form = SiteForm() if selected is None else _form_from(selected)
    items = tuple(
        SiteListItem(
            href=f"/sites?site_id={r.site_id}",
            name=r.name,
            summary=f"{_work_types_summary(r.work_types)} · {_hhmm(r.work_start_local)}–"
            f"{_hhmm(r.work_end_local)}",
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
    name = form.name.strip()
    if not name or len(name) > NAME_MAX:
        errors.append(f"현장 이름을 1~{NAME_MAX}자로 입력하세요.")
    address = form.address.strip()
    if len(address) > ADDRESS_MAX:
        errors.append(f"주소는 {ADDRESS_MAX}자 이하로 입력하세요.")

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

    unknown = [w for w in form.work_types if w not in WORK_TYPE_LABELS]
    if unknown:
        errors.append(f"알 수 없는 공종: {', '.join(unknown)}")
    if not form.work_types:
        errors.append("공종을 하나 이상 고르세요.")

    if errors or grid is None or start is None or end is None:
        return None, tuple(errors)
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


def _hhmm(value: time) -> str:
    return value.strftime("%H:%M")


def _work_types_summary(work_types: tuple[str, ...]) -> str:
    if len(work_types) <= 1:
        return work_types[0] if work_types else "공종 없음"
    return f"{work_types[0]} 외 {len(work_types) - 1}개"


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
    )
