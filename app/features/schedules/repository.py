from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.features.schedules.models import WorkItem


def list_between(session: Session, site_ids: list[int], start: date, end: date) -> list[WorkItem]:
    """현장들의 [start, end] 작업을 날짜·시작 시각 순으로(현장마다 따로 조회하지 않음)."""
    if not site_ids:
        return []
    return list(
        session.scalars(
            select(WorkItem)
            .where(
                WorkItem.site_id.in_(site_ids),
                WorkItem.work_date >= start,
                WorkItem.work_date <= end,
            )
            .order_by(WorkItem.work_date, WorkItem.start_local, WorkItem.id)
        )
    )


def add_all(session: Session, items: list[WorkItem]) -> None:
    """여러 날 작업을 한 번에 저장한다(모두 저장하거나 하나도 저장하지 않음)."""
    session.add_all(items)
    session.commit()


def delete_item(session: Session, site_id: int, item_id: int) -> bool:
    """다른 현장의 작업은 지우지 않는다(현장 범위 확인)."""
    deleted = session.scalars(
        delete(WorkItem)
        .where(WorkItem.id == item_id, WorkItem.site_id == site_id)
        .returning(WorkItem.id)
    ).first()
    session.commit()
    return deleted is not None
