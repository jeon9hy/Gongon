from dataclasses import dataclass

from app.features.actions.schemas import ActionRef
from app.features.changes.schemas import CaseCard
from app.features.teams.schemas import ContactCard


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
    # 첨부(D-111): 사진 주소(현장 참여자만 열림)·연락처·조치. 지운 메시지는 모두 None
    photo_url: str | None = None
    contact: ContactCard | None = None
    action: ActionRef | None = None


@dataclass(frozen=True, slots=True)
class RoomChoice:
    """방 목록 한 줄. 마지막 메시지가 있으면 미리보기와 시각을 보인다(카톡처럼 최근 순)."""

    site_id: int
    name: str
    selected: bool
    last_text: str = ""  # 마지막 메시지 미리보기("이름: 본문"), 없으면 빈 글
    last_time: str = ""  # 오늘이면 "오후 3:05", 어제면 "어제", 그 전은 "10월 27일"


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
    contact_choices: tuple[ContactCard, ...] = ()
    action_choices: tuple[ActionRef, ...] = ()
