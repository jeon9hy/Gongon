"""현장 설정 화면용 조회. 지금은 예시 현장을 읽고, S04-3에서 DB 조회·저장으로 바꾼다."""

from app.features.sites import sample
from app.features.sites.schemas import SiteListItem, SitesView
from engine.geo import latlon_to_kma_grid


def build_sites_view(site_id: int) -> SitesView | None:
    selected = next((s for s in sample.SITES if s.site_id == site_id), None)
    if selected is None:
        return None
    items = tuple(
        SiteListItem(
            href=f"/sites?site_id={s.site_id}",
            name=s.name,
            summary=f"철골 작업 · {s.work_start}–{s.work_end}",
            selected=s.site_id == site_id,
        )
        for s in sample.SITES
    )
    grid = latlon_to_kma_grid(selected.latitude_deg, selected.longitude_deg)
    return SitesView(items=items, site=selected, grid_text=f"({grid.nx}, {grid.ny})")


def first_site_id() -> int:
    return sample.SITES[0].site_id
