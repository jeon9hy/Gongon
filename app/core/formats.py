"""폼 값 읽기와 날짜 표시. 기능마다 같은 형식을 다시 만들지 않도록 한 곳에 둔다."""

from datetime import date, time

WEEKDAYS = "월화수목금토일"


def weekday_name(day: date) -> str:
    return WEEKDAYS[day.weekday()]


def day_text(day: date) -> str:
    """'10월 30일(금)'."""
    return f"{day.month}월 {day.day}일({weekday_name(day)})"


def parse_int(raw: str) -> int | None:
    try:
        return int(raw)
    except ValueError:
        return None


def parse_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def parse_time(raw: str) -> time | None:
    try:
        return time.fromisoformat(raw.strip())
    except ValueError:
        return None
