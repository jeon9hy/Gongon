"""현장 설정 화면용 조회. 지금은 예시 현장을 읽고, S04-3에서 DB 조회·저장으로 바꾼다."""

from app.features.sites import sample
from app.features.sites.schemas import SiteListItem, SitesView, WorkTypeOption
from engine.geo import latlon_to_kma_grid


def build_sites_view(site_id: int) -> SitesView | None:
    selected = next((s for s in sample.SITES if s.site_id == site_id), None)
    if selected is None:
        return None
    items = tuple(
        SiteListItem(
            href=f"/sites?site_id={s.site_id}",
            name=s.name,
            summary=f"{_work_types_summary(s.work_types)} · {s.work_start}–{s.work_end}",
            selected=s.site_id == site_id,
        )
        for s in sample.SITES
    )
    grid = latlon_to_kma_grid(selected.latitude_deg, selected.longitude_deg)
    options = tuple(
        WorkTypeOption(w.label, w.basis, w.label in selected.work_types) for w in sample.WORK_TYPES
    )
    return SitesView(
        items=items,
        site=selected,
        grid_text=f"({grid.nx}, {grid.ny})",
        work_type_options=options,
        unconfirmed_labels=tuple(w.label for w in sample.WORK_TYPES if w.basis == "기준 미확인"),
    )


def _work_types_summary(work_types: tuple[str, ...]) -> str:
    if not work_types:
        return "공종 없음"
    if len(work_types) == 1:
        return work_types[0]
    return f"{work_types[0]} 외 {len(work_types) - 1}개"


def first_site_id() -> int:
    return sample.SITES[0].site_id
