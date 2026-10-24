from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, defer

from app.features.judgments.models import Judgment, JudgmentRun

# 화면이 묶는 작업 단위(service._key와 같음): 작업 일정 판정은 작업 ID, 아니면 공종.
# 작업 일정의 공종은 바뀌지 않으므로 (공종, 작업 ID)로 나눠도 같은 묶음이다.
# NULL 작업 ID는 공종별로 한 묶음이다.
_WORK_KEY = (Judgment.site_id, Judgment.target_date, Judgment.work_type, Judgment.work_item_id)


def latest_for_site_date(session: Session, site_id: int, target_date: date) -> list[Judgment]:
    """한 현장·대상 날짜에서 작업마다 최신 판정 하나. 최신순."""
    return _latest_per_work(
        session, Judgment.site_id == site_id, Judgment.target_date == target_date
    )


def latest_for_site_between(
    session: Session, site_id: int, start: date, end: date
) -> list[Judgment]:
    """한 현장의 [start, end] 판정(주간 보기, 쿼리 1회).

    작업 카드가 시간별 값과 구간(windows)을 모두 쓰므로 함께 읽는다. windows를 미루면 카드마다
    한 번씩 더 조회해 홈·일정·판정 화면에서 100번 넘게 다시 읽었다(C04-56).

    날짜·작업마다 최신 예보의 최신 판정과, 그 직전 다른 예보의 최신 판정까지 두 건(공온지수 예보
    안정성). 최신순이라 같은 묶음의 첫 행이 현재 판정이다.
    """
    conditions = (
        Judgment.site_id == site_id,
        Judgment.target_date >= start,
        Judgment.target_date <= end,
    )
    per_forecast = (
        select(Judgment.id, Judgment.judged_at, *_WORK_KEY)
        .ext(distinct_on(*_WORK_KEY, Judgment.forecast_issued_at))
        .where(*conditions)
        .order_by(
            *_WORK_KEY, Judgment.forecast_issued_at, Judgment.judged_at.desc(), Judgment.id.desc()
        )
        .subquery()
    )
    rank = (
        func.row_number()
        .over(
            partition_by=[getattr(per_forecast.c, c.key) for c in _WORK_KEY],
            order_by=[per_forecast.c.judged_at.desc(), per_forecast.c.id.desc()],
        )
        .label("rank")
    )
    ranked = select(per_forecast.c.id, rank).subquery()
    ids = select(ranked.c.id).where(ranked.c.rank <= 2)
    return list(
        session.scalars(
            select(Judgment)
            .where(Judgment.id.in_(ids))
            .order_by(Judgment.judged_at.desc(), Judgment.id.desc())
        )
    )


def latest_for_sites_date(
    session: Session, site_ids: list[int], target_date: date
) -> list[Judgment]:
    """여러 현장의 대상 날짜에서 작업마다 최신 판정 하나(현장마다 따로 조회하지 않음). 최신순."""
    if not site_ids:
        return []
    return _latest_per_work(
        session, Judgment.site_id.in_(site_ids), Judgment.target_date == target_date
    )


def _latest_per_work(session: Session, *conditions: ColumnElement[bool]) -> list[Judgment]:
    """조건 안에서 작업마다 최신 판정 하나를 DB에서 먼저 고른다(C04-1, S08-4-3).

    예전에는 전체를 개수 제한한 뒤 묶어서, 기록이 쌓이면 오래 판정하지 않은 작업이 빠졌다.
    """
    ids = (
        select(Judgment.id)
        .ext(distinct_on(*_WORK_KEY))
        .where(*conditions)
        .order_by(*_WORK_KEY, Judgment.judged_at.desc(), Judgment.id.desc())
    )
    return list(
        session.scalars(
            select(Judgment)
            .where(Judgment.id.in_(ids))
            .order_by(Judgment.judged_at.desc(), Judgment.id.desc())
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
    work_item_id: int | None,
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
            Judgment.work_item_id.is_not_distinct_from(work_item_id),
        )
    ).first()


def get(session: Session, judgment_id: int) -> Judgment | None:
    return session.get(Judgment, judgment_id)


def _latest_ids(
    site_id: int | None, site_ids: Sequence[int] | None, until: date | None
) -> Select[int]:
    """날짜·현장·작업(공종·작업 일정·작업 시간)마다 가장 최근 판정 하나의 id.

    PostgreSQL DISTINCT ON으로 고른다.

    다시 판정해 덮어쓴 이전 판정은 기록으로 남기되 목록에는 내지 않는다(D-049).
    """
    key = (
        Judgment.target_date,
        Judgment.site_id,
        Judgment.work_type,
        Judgment.work_item_id,
        Judgment.work_start_at,
        Judgment.work_end_at,
    )
    query = (
        select(Judgment.id)
        .ext(distinct_on(*key))
        .order_by(*key, Judgment.judged_at.desc(), Judgment.id.desc())
    )
    if site_id is not None:
        query = query.where(Judgment.site_id == site_id)
    if site_ids is not None:
        query = query.where(Judgment.site_id.in_(site_ids))
    if until is not None:
        query = query.where(Judgment.target_date <= until)
    return query


def page(
    session: Session,
    site_id: int | None,
    verdict: str | None,
    offset: int,
    limit: int,
    site_ids: Sequence[int] | None = None,
    until: date | None = None,
) -> list[Judgment]:
    """작업별 최신 판정만, 대상 날짜 → 현장 → 최근 순.

    site_ids를 주면 그 현장들만(홈에서 삭제한 현장을 뺄 때), until을 주면 그 날짜까지 대상만.
    판정 단계 필터는 최신 판정에 건다(덮어쓰인 이전 판정의 단계로 걸리지 않게).
    """
    # 목록에는 시간별 상세(JSONB)가 필요 없다.
    query = (
        select(Judgment)
        .options(defer(Judgment.hours), defer(Judgment.windows))
        .where(Judgment.id.in_(_latest_ids(site_id, site_ids, until).scalar_subquery()))
    )
    if verdict is not None:
        query = query.where(Judgment.verdict == verdict)
    # 내역 화면이 날짜·현장으로 묶을 때 한 묶음이 이어지게 한다.
    query = query.order_by(
        Judgment.target_date.desc(), Judgment.site_id, Judgment.judged_at.desc(), Judgment.id
    )
    return list(session.scalars(query.offset(offset).limit(limit)))


def verdict_counts(
    session: Session, site_id: int | None, site_ids: Sequence[int] | None = None
) -> dict[str, int]:
    """작업별 최신 판정의 단계별 건수(목록과 같은 기준)."""
    query = (
        select(Judgment.verdict, func.count())
        .where(Judgment.id.in_(_latest_ids(site_id, site_ids, None).scalar_subquery()))
        .group_by(Judgment.verdict)
    )
    return {verdict: count for verdict, count in session.execute(query)}


def latest_runs(session: Session, site_ids: Sequence[int]) -> dict[int, JudgmentRun]:
    """현장마다 가장 최근 판정 실행(쿼리 1회). 실행은 시간 순으로 추가되어 가장 큰 id가 최근이다."""
    if not site_ids:
        return {}
    latest_ids = (
        select(func.max(JudgmentRun.id))
        .where(JudgmentRun.site_id.in_(site_ids))
        .group_by(JudgmentRun.site_id)
    )
    rows = session.scalars(select(JudgmentRun).where(JudgmentRun.id.in_(latest_ids)))
    return {r.site_id: r for r in rows}
