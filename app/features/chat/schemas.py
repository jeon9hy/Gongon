from dataclasses import dataclass

from app.features.changes.schemas import CaseCard


@dataclass(frozen=True, slots=True)
class MessageView:
    message_id: int
    author_name: str
    author_company: str
    mine: bool
    body: str | None  # 지운 메시지는 None
    time_text: str  # "10/17 09:05"
    day_text: str  # 날짜 구분선 "10월 17일(토)"
    case: CaseCard | None
    can_delete: bool


@dataclass(frozen=True, slots=True)
class RoomChoice:
    site_id: int
    name: str
    selected: bool


@dataclass(frozen=True, slots=True)
class ChatView:
    site_id: int
    site_name: str
    rooms: tuple[RoomChoice, ...]
    messages: tuple[MessageView, ...]
    last_id: int  # 새 메시지 불러오기 기준
    has_older: bool
    case_choices: tuple[CaseCard, ...]
    can_write: bool
    errors: tuple[str, ...] = ()
    draft: str = ""
