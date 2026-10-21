from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ProjectParticipant(Base):
    """현장에 참여한 회사. 원청(prime)은 현장당 하나다(0010 마이그레이션이 강제)."""

    __tablename__ = "project_participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    kind: Mapped[str] = mapped_column(String(20))  # prime | subcontractor
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 명부(C04-9, D-066). 원청은 category NULL·종료 불가. 기존 협력업체 행은 category NULL.
    category: Mapped[str | None] = mapped_column(String(20))
    trade_note: Mapped[str | None] = mapped_column(String(60))
    # 맡은 업종(D-088): 작업 고르기 업종 목록의 이름. 작업 고르기를 이 업종부터 보인다
    work_trades: Mapped[list[str]] = mapped_column(
        ARRAY(String(60)), default=list, server_default=text("'{}'::varchar[]")
    )
    business_no: Mapped[str | None] = mapped_column(String(20))  # 선택 입력, 검증하지 않는다
    joined_on: Mapped[date | None] = mapped_column(Date)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class ProjectMembership(Base):
    """사용자의 현장 참여와 역할. 회수해도 행을 남겨 누가 언제 권한을 줬고 거뒀는지 보존한다."""

    __tablename__ = "project_memberships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["participant_id", "site_id"],
            ["project_participants.id", "project_participants.site_id"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(Integer)
    participant_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(20))  # coordinator | assignee | viewer
    granted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class ParticipantContact(Base):
    """참여 업체의 담당자 명부(계정 없이 등록). 직책은 표시·연락용이고 권한과 무관하다(D-066)."""

    __tablename__ = "participant_contacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["participant_id", "site_id"],
            ["project_participants.id", "project_participants.site_id"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(Integer)
    participant_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(40))
    job_title: Mapped[str] = mapped_column(String(40), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    memo: Mapped[str] = mapped_column(String(200), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # None = 계정 미연결
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
