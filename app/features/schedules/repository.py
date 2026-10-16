from datetime import date, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.features.schedules.models import WorkItem


def list_between(session: Session, site_ids: list[int], start: date, end: date) -> list[WorkItem]:
    """현장들의 [start, end] 작업을 날짜·시작 시각 순으로(현장마다 한 번에). 지운 작업은 뺀다."""
    if not site_ids:
        return []
    return list(
        session.scalars(
            select(WorkItem)
            .where(
                WorkItem.site_id.in_(site_ids),
                WorkItem.work_date >= start,
                WorkItem.work_date <= end,
                WorkItem.deleted_at.is_(None),
            )
            .order_by(WorkItem.work_date, WorkItem.start_local, WorkItem.id)
        )
    )


def add_all(session: Session, items: list[WorkItem]) -> None:
    """여러 날 작업을 한 번에 저장한다(모두 저장하거나 하나도 저장하지 않음)."""
    session.add_all(items)
    session.commit()


def delete_item(session: Session, site_id: int, item_id: int, deleted_at: datetime) -> bool:
    """숨김 처리한다. 다른 현장의 작업·이미 지운 작업은 건드리지 않는다(False)."""
    deleted = session.scalars(
        update(WorkItem)
        .where(WorkItem.id == item_id, WorkItem.site_id == site_id, WorkItem.deleted_at.is_(None))
        .values(deleted_at=deleted_at)
        .returning(WorkItem.id)
    ).first()
    session.commit()
    return deleted is not None
