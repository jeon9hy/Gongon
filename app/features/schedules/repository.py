from datetime import date, datetime, time

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.features.schedules.models import WorkItem, WorkItemRevision
from app.features.schedules.schemas import PlanValues


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


def get_active(session: Session, site_id: int, item_id: int) -> WorkItem | None:
    item = session.get(WorkItem, item_id)
    if item is None or item.site_id != site_id or item.deleted_at is not None:
        return None
    return item


def update_plan_if_version(
    session: Session, item: WorkItem, expected_version: int, values: PlanValues
) -> bool:
    """제출한 버전이 아직 현재 버전일 때만 계획을 바꾸고 버전을 올린다(낙관적 잠금).

    조건부 UPDATE 한 번이라 두 사람이 같은 버전으로 동시에 저장해도 한 사람만 성공한다.
    """
    updated = session.scalars(
        update(WorkItem)
        .where(
            WorkItem.id == item.id,
            WorkItem.plan_version == expected_version,
            WorkItem.deleted_at.is_(None),
        )
        .values(
            work_date=values.work_date,
            start_local=values.start_local,
            end_local=values.end_local,
            location=values.location,
            memo=values.memo,
            performing_participant_id=values.performing_participant_id,
            plan_version=WorkItem.plan_version + 1,
        )
        .returning(WorkItem.id)
        .execution_options(synchronize_session="fetch")
    ).first()
    return updated is not None


def revisions_for(session: Session, item_ids: list[int]) -> list[WorkItemRevision]:
    if not item_ids:
        return []
    query = (
        select(WorkItemRevision)
        .where(WorkItemRevision.work_item_id.in_(item_ids))
        .order_by(WorkItemRevision.work_item_id, WorkItemRevision.plan_version.desc())
    )
    return list(session.scalars(query))


def work_type_usage(session: Session, site_id: int) -> dict[str, int]:
    """현장에 등록한(지우지 않은) 작업의 공종별 수. 작업 추가 화면에서 자주 쓴 공종을 앞에 둔다."""
    rows = session.execute(
        select(WorkItem.work_type, func.count())
        .where(WorkItem.site_id == site_id, WorkItem.deleted_at.is_(None))
        .group_by(WorkItem.work_type)
    ).all()
    return {work_type: count for work_type, count in rows}


def recent_times(session: Session, site_id: int, limit: int) -> list[tuple[time, time]]:
    """최근 등록한 작업 시간(겹치지 않게). 화면은 버튼으로만 보이고 미리 채우지 않는다."""
    rows = session.execute(
        select(WorkItem.start_local, WorkItem.end_local)
        .where(WorkItem.site_id == site_id, WorkItem.deleted_at.is_(None))
        .group_by(WorkItem.start_local, WorkItem.end_local)
        .order_by(func.max(WorkItem.id).desc())
        .limit(limit)
    ).all()
    return [(start, end) for start, end in rows]


def get_many(session: Session, item_ids: list[int]) -> list[WorkItem]:
    """지우지 않은 작업들(쿼리 1회). 목록 화면이 작업 이름을 한 번에 읽는다."""
    if not item_ids:
        return []
    query = select(WorkItem).where(WorkItem.id.in_(item_ids), WorkItem.deleted_at.is_(None))
    return list(session.scalars(query))
