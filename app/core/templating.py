"""화면 렌더링 공통 기반. 기능은 자기 templates 폴더를 등록하고 공통 레이아웃을 상속한다."""

from datetime import time
from pathlib import Path

from fastapi.templating import Jinja2Templates
from jinja2 import FileSystemLoader

CORE_DIR = Path(__file__).parent
STATIC_DIR = CORE_DIR / "static"

templates = Jinja2Templates(directory=CORE_DIR / "templates")


def static_url(name: str) -> str:
    """정적 파일 주소에 수정 시각을 붙인다. 파일이 바뀌면 주소도 바뀌어 옛 캐시를 쓰지 않는다."""
    version = int((STATIC_DIR / name).stat().st_mtime)
    return f"/static/{name}?v={version}"


templates.env.globals["static_url"] = static_url

# 공종별 색(D-064). 판정 4단계 색(초록·주황·빨강·회색)과 겹치지 않게 고른다.
# 색만으로 구분하지 않도록 이름을 함께 쓴다.
WORK_TYPE_COLORS = {
    "철골 작업": "#2563EB",
    "콘크리트 타설": "#7C3AED",
    "이동식 크레인": "#0891B2",
    "고소작업대": "#DB2777",
    "도장·방수": "#4F46E5",
    "아스팔트 포장": "#92400E",
}


def work_color(label: str) -> str:
    return WORK_TYPE_COLORS.get(label, "#8A93A3")


templates.env.globals["work_color"] = work_color


def as_time(hm: str) -> time:
    """화면 비교용 "HH:MM" → time. 비어 있거나 형식이 다르면 하루의 시작으로 본다."""
    try:
        return time.fromisoformat(hm)
    except ValueError:
        return time.min


templates.env.filters["as_time"] = as_time


def register_template_dir(directory: Path) -> None:
    """기능 폴더의 templates를 검색 경로에 추가한다. 템플릿 이름은 `<기능>/<파일>`로 둔다."""
    loader = templates.env.loader
    assert isinstance(loader, FileSystemLoader)
    path = str(directory)
    if path not in loader.searchpath:
        loader.searchpath.append(path)
