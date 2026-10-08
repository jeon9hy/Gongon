"""화면 렌더링 공통 기반. 기능은 자기 templates 폴더를 등록하고 공통 레이아웃을 상속한다."""

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


def register_template_dir(directory: Path) -> None:
    """기능 폴더의 templates를 검색 경로에 추가한다. 템플릿 이름은 `<기능>/<파일>`로 둔다."""
    loader = templates.env.loader
    assert isinstance(loader, FileSystemLoader)
    path = str(directory)
    if path not in loader.searchpath:
        loader.searchpath.append(path)
