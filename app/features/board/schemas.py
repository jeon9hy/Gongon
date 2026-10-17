from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BoardItem:
    time_text: str
    work_type: str
    location: str
    company: str
    phase: str  # 오늘만: "예정" · "진행 중" · "끝남"


@dataclass(frozen=True, slots=True)
class BoardView:
    site_id: int
    site_name: str
    today_text: str
    tomorrow_text: str
    today: tuple[BoardItem, ...]
    tomorrow: tuple[BoardItem, ...]
    changes: tuple[str, ...]  # 오늘 확정된 변경 한 줄씩
    weather_text: str | None
    updated_text: str
