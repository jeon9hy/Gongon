"""화면 렌더링 공통 기반. 기능은 자기 templates 폴더를 등록하고 공통 레이아웃을 상속한다."""

from pathlib import Path

from fastapi.templating import Jinja2Templates
from jinja2 import FileSystemLoader

CORE_DIR = Path(__file__).parent
STATIC_DIR = CORE_DIR / "static"

templates = Jinja2Templates(directory=CORE_DIR / "templates")


def register_template_dir(directory: Path) -> None:
    """기능 폴더의 templates를 검색 경로에 추가한다. 템플릿 이름은 `<기능>/<파일>`로 둔다."""
    loader = templates.env.loader
    assert isinstance(loader, FileSystemLoader)
    path = str(directory)
    if path not in loader.searchpath:
        loader.searchpath.append(path)
