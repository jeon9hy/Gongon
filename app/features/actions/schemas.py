from dataclasses import dataclass
from typing import Literal

ActionStatus = Literal[
    "candidate", "requested", "accepted", "blocked", "reported", "verified", "replaced", "excluded"
]  # fmt: skip
STATUS_LABELS: dict[str, str] = {
    "candidate": "조치 후보",
    "requested": "요청 대기",
    "accepted": "수행 중",
    "blocked": "보류",
    "reported": "확인 대기",
    "verified": "검증 완료",
    "replaced": "대체됨",
    "excluded": "제외",
}
EVENT_LABELS: dict[str, str] = {
    "requested": "요청",
    "accepted": "수락",
    "resumed": "보류 풀림 · 다시 수행",
    "blocked": "보류 보고",
    "reported": "완료 보고",
    "verified": "검증 완료",
    "rejected": "반려",
    "excluded": "제외",
    "replaced": "재변경으로 대체",
    "phone_record": "전화 확인 기록",
    "viewed": "열람",
}
# 확정 뒤 아직 끝나지 않은 상태. 재변경 때 requested·accepted·blocked는 대체된다
# (새 조치와의 연결은 C07).
OPEN_STATUSES: tuple[str, ...] = ("requested", "accepted", "blocked", "reported")
UNSTARTED_STATUSES: tuple[str, ...] = ("requested", "accepted", "blocked")
# 화면에서 누를 수 있는 처리. kind는 폼 action 경로의 마지막 부분이다.
ActionKind = Literal["accept", "resume", "block", "report", "verify", "reject", "exclude", "phone"]
ACTION_KINDS: tuple[str, ...] = (
    "accept", "resume", "block", "report", "verify", "reject", "exclude", "phone"
)  # fmt: skip
# 수행자 자격: self(지정 담당·실행 업체 담당자) · delegate(위임받음)
# · behalf(조정자가 전화로 확인해 대신 기록)
PerformerMode = Literal["self", "delegate", "behalf"]


@dataclass(frozen=True, slots=True)
class CandidateForm:
    """조치 후보 입력(문자열 그대로).

    기한은 날짜·시각을 같이 넣거나, 둘 다 비우고 미정 사유를 쓴다.
    """

    title: str = ""
    done_criteria: str = ""
    performing_participant_id: str = ""
    # "" 업체 내 미지정 · "user:<id>" 계정 · "contact:<id>" 계정 없는 명부의 사람
    assignee: str = ""
    verifier_user_id: str = ""
    required: bool = True
    due_date: str = ""
    due_time: str = ""
    due_note: str = ""


@dataclass(frozen=True, slots=True)
class ActionForm:
    """조치 처리 입력. revision_id는 화면을 연 때의 조치 버전이다(다르면 거부)."""

    revision_id: str = ""
    body: str = ""  # 처리 내용·막힘 사유·반려·제외 이유·통화 내용
    performed_date: str = ""
    performed_time: str = ""
    counterpart: str = ""  # 연락 상대·회사
    reference: str = ""  # 참조 번호(예약 번호 등)
    contacted_date: str = ""
    contacted_time: str = ""
    resolver: str = ""  # 막힘을 풀 담당


@dataclass(frozen=True, slots=True)
class Option:
    value: int
    label: str
    selected: bool


@dataclass(frozen=True, slots=True)
class AssigneeOption:
    value: str  # CandidateForm.assignee 형식
    label: str  # "이름 · 직책" 또는 "이름 · 계정 없음(전화 확인)"
    participant_id: int
    selected: bool


@dataclass(frozen=True, slots=True)
class CandidateEditor:
    """영향 검토 중인 버전의 조치 후보 입력 칸."""

    participants: tuple[Option, ...]
    assignees: tuple[AssigneeOption, ...]  # 수행 업체별로 묶어 보인다
    verifiers: tuple[Option, ...]
    form: CandidateForm
    title_suggestions: tuple[str, ...]  # 이 현장에서 쓴 조치 이름(재사용)
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ActionCard:
    action_id: int
    revision_id: int
    title: str
    done_criteria: str
    status: str
    status_label: str
    required: bool
    performer_text: str  # "가상펌프 · 김OO" 또는 "가상골조 · 담당 미지정(업체 담당자 누구나)"
    verifier_text: str
    due_text: str  # "10/19(월) 17:00까지" 또는 "기한 미정 · 사유"
    overdue: bool
    late_text: str | None  # 기한 뒤 처리
    blocked_text: str | None
    report_text: str | None
    exclude_text: str | None
    replaced_text: str | None
    carried: bool  # 재변경으로 이전 버전에서 이어받은 후보·조치
    history: tuple[str, ...]
    allowed: frozenset[str]  # 지금 사용자가 누를 수 있는 처리(ACTION_KINDS)와 "remove"(후보 빼기)
    behalf: bool  # 조정자가 수행자 대신 기록하는 경우: 연락 상대·시각 필수


@dataclass(frozen=True, slots=True)
class RevisionActions:
    cards: tuple[ActionCard, ...]
    required_total: int
    required_done: int
    blocked: int
    editor: CandidateEditor | None
    candidates: int = 0  # 확정 전 후보 수
    required_candidates: int = 0  # 그중 필수(0이면 확정 때 이유 필요)

    @property
    def remaining(self) -> int:
        return self.required_total - self.required_done


@dataclass(frozen=True, slots=True)
class MyActionItem:
    href: str
    title: str
    site_name: str
    status_label: str
    due_text: str
    overdue: bool
    why: str  # "처리" · "검증" · "위임받음" · "대리 기록"
    site_id: int = 0  # 머리줄 현장 칩으로 거를 때(D-092)


@dataclass(frozen=True, slots=True)
class DelegationRow:
    delegation_id: int
    site_name: str
    from_name: str
    to_name: str
    period_text: str
    can_revoke: bool


@dataclass(frozen=True, slots=True)
class DelegateChoice:
    value: str  # "site_id:user_id"
    label: str  # "현장 · 이름"


@dataclass(frozen=True, slots=True)
class MyActionsView:
    """내 조치(D-070 R3). 묶음마다 기한 지남 → 가까운 기한 → 기한 미정 순."""

    to_respond: tuple[MyActionItem, ...]  # 요청 대기·수행 중
    blocked: tuple[MyActionItem, ...]
    to_verify: tuple[MyActionItem, ...]
    delegations: tuple[DelegationRow, ...]
    delegate_choices: tuple[DelegateChoice, ...]
    errors: tuple[str, ...] = ()
    message: str | None = None
    site_id: int | None = None  # 머리줄 현장 칩에서 고른 현장(None = 전체, D-092)
    site_name: str = ""


@dataclass(frozen=True, slots=True)
class ActionRef:
    """대화방에 붙이는 조치 카드(D-111). 늘 지금 상태를 읽어 만든다."""

    action_id: int
    title: str
    href: str
    status: str
    status_label: str


@dataclass(frozen=True, slots=True)
class OpenActionLine:
    """주간 작업계획표의 안 끝난 조치 한 줄(D-112). 담당자 이름·연락처는 넣지 않는다."""

    action_id: int
    case_id: int
    title: str
    performing_participant_id: int
    status_label: str
    due_text: str
    overdue: bool
