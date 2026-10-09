from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.sites.models import Site
from app.features.sites.schemas import SiteInput

MAX_SITES = 200  # 1인 사용 범위의 상한. 넘으면 페이지 처리를 추가한다.


def list_sites(session: Session) -> list[Site]:
    query = select(Site).where(Site.deleted_at.is_(None)).order_by(Site.id).limit(MAX_SITES)
    return list(session.scalars(query))


def get_site(session: Session, site_id: int) -> Site | None:
    """삭제한 현장은 없는 현장과 같게 본다."""
    site = session.get(Site, site_id)
    return None if site is None or site.deleted_at is not None else site


def mark_deleted(site: Site, deleted_at: datetime) -> None:
    site.deleted_at = deleted_at


def add_site(session: Session, data: SiteInput) -> Site:
    site = Site(**_columns(data))
    session.add(site)
    session.flush()
    return site


def update_site(site: Site, data: SiteInput) -> None:
    for key, value in _columns(data).items():
        setattr(site, key, value)


def _columns(data: SiteInput) -> dict[str, object]:
    return {
        "name": data.name,
        "address": data.address,
        "road_address": data.road_address,
        "lot_address": data.lot_address,
        "latitude_deg": data.latitude_deg,
        "longitude_deg": data.longitude_deg,
        "grid_nx": data.grid_nx,
        "grid_ny": data.grid_ny,
        "work_start_local": data.work_start_local,
        "work_end_local": data.work_end_local,
        "work_types": list(data.work_types),
        "work_start_date": data.work_start_date,
        "work_end_date": data.work_end_date,
    }
