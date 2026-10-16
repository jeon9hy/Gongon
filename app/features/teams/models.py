from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, func
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
