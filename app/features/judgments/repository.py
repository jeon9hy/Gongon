from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, defer

from app.features.judgments.models import Judgment

LATEST_LIMIT = 50


def latest_for_site_date(session: Session, site_id: int, target_date: date) -> list[Judgment]:
    """한 현장·대상 날짜의 판정을 최신순으로. 공종마다 첫 행이 최신 판정이다."""
    return list(
        session.scalars(
            select(Judgment)
            .where(Judgment.site_id == site_id, Judgment.target_date == target_date)
            .order_by(Judgment.judged_at.desc(), Judgment.id.desc())
            .limit(LATEST_LIMIT)
        )
    )


def find_same(
    session: Session,
    *,
    site_id: int,
    target_date: date,
    work_type: str,
    forecast_issued_at: datetime,
    rule_version: str,
    grid_nx: int,
    grid_ny: int,
    work_start_at: datetime,
    work_end_at: datetime,
) -> Judgment | None:
    """같은 예보·기준·위치·작업 시간으로 이미 낸 판정(uq_judgments_reuse_key와 같은 키)."""
    return session.scalars(
        select(Judgment).where(
            Judgment.site_id == site_id,
            Judgment.target_date == target_date,
            Judgment.work_type == work_type,
            Judgment.forecast_issued_at == forecast_issued_at,
            Judgment.rule_version == rule_version,
            Judgment.grid_nx == grid_nx,
            Judgment.grid_ny == grid_ny,
            Judgment.work_start_at == work_start_at,
            Judgment.work_end_at == work_end_at,
        )
    ).first()


def get(session: Session, judgment_id: int) -> Judgment | None:
    return session.get(Judgment, judgment_id)


def page(
    session: Session, site_id: int | None, verdict: str | None, offset: int, limit: int
) -> list[Judgment]:
    # 목록에는 시간별 상세(JSONB)가 필요 없다.
    query = select(Judgment).options(defer(Judgment.hours), defer(Judgment.windows))
    if site_id is not None:
        query = query.where(Judgment.site_id == site_id)
    if verdict is not None:
        query = query.where(Judgment.verdict == verdict)
    query = query.order_by(Judgment.target_date.desc(), Judgment.judged_at.desc(), Judgment.id)
    return list(session.scalars(query.offset(offset).limit(limit)))


def verdict_counts(session: Session, site_id: int | None) -> dict[str, int]:
    query = select(Judgment.verdict, func.count()).group_by(Judgment.verdict)
    if site_id is not None:
        query = query.where(Judgment.site_id == site_id)
    return {verdict: count for verdict, count in session.execute(query)}
