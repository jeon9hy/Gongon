from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SiteMessage(Base):
    """현장 대화방 메시지(C12). 지우면 deleted_at만 남기고 본문은 보이지 않는다."""

    __tablename__ = "site_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    linked_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("change_cases.id", ondelete="SET NULL")
    )
    # 첨부(D-111): 메시지 하나에 하나. 사진은 보관소 키, 연락처·조치는 지금 상태로 카드
    photo_key: Mapped[str | None] = mapped_column(String(120))
    photo_type: Mapped[str | None] = mapped_column(String(20))
    photo_bytes: Mapped[int | None] = mapped_column(Integer)
    linked_contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("participant_contacts.id", ondelete="SET NULL")
    )
    linked_action_id: Mapped[int | None] = mapped_column(
        ForeignKey("action_items.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
