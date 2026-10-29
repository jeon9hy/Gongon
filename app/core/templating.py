"""화면 렌더링 공통 기반. 기능은 자기 templates 폴더를 등록하고 공통 레이아웃을 상속한다."""

from datetime import time
from pathlib import Path
from typing import Any

from fastapi.templating import Jinja2Templates
from jinja2 import FileSystemLoader, TemplateNotFound
from starlette.requests import Request
from starlette.templating import _TemplateResponse

from app.core.ui_mode import ui_mode
from app.core.work_kinds import TRADE_OF_KIND, WORK_TRADES, short_trade_name

CORE_DIR = Path(__file__).parent
STATIC_DIR = CORE_DIR / "static"


def app_variant(name: str) -> str:
    """`기능/화면.html`의 앱 화면 이름 `기능/app/화면.html`(D-109)."""
    feature, _, page = name.rpartition("/")
    return f"{feature}/app/{page}" if feature else f"app/{page}"


class DeviceTemplates(Jinja2Templates):
    """앱 화면으로 열린 요청이면 같은 기능의 앱 화면을 먼저 찾는다. 없으면 웹 화면을 앱 틀에 그린다.

    라우터·주소·권한은 하나이고 화면만 바뀐다(D-109)."""

    def TemplateResponse(
        self, request: Request, name: str, *args: Any, **kwargs: Any
    ) -> _TemplateResponse:
        if ui_mode(request) == "app":
            try:
                self.env.get_template(app_variant(name))
                name = app_variant(name)
            except TemplateNotFound:
                pass
        return super().TemplateResponse(request, name, *args, **kwargs)


templates = DeviceTemplates(directory=CORE_DIR / "templates")


def static_url(name: str) -> str:
    """정적 파일 주소에 수정 시각을 붙인다. 파일이 바뀌면 주소도 바뀌어 옛 캐시를 쓰지 않는다."""
    version = int((STATIC_DIR / name).stat().st_mtime)
    return f"/static/{name}?v={version}"


templates.env.globals["static_url"] = static_url

# 업종(최상위 공종) 색(D-089, D-064 대체): (옅은 바탕, 같은 색상의 진한 색).
# 달력 막대는 옅은 바탕에 진한 글자·왼쪽 선, 작업 점은 진한 색이다.
# 판정 표시 색(중지 빨강·확인 주황 노랑)과 겹치지 않게 고른다.
TRADE_COLORS = {
    # 자주 쓰는 여섯 업종은 색상환에서 멀리 떨어진 색(파랑·주황·초록·분홍·보라·청록, C04-51)
    "철근ㆍ콘크리트공사업": ("#DBEAFE", "#2563EB"),
    "철강구조물공사업": ("#FFEDD5", "#EA580C"),
    "구조물해체ㆍ비계공사업": ("#DCFCE7", "#16A34A"),
    "도장ㆍ습식ㆍ방수ㆍ석공사업": ("#FCE7F3", "#DB2777"),
    "전기·정보통신·소방": ("#EDE9FE", "#7C3AED"),
    "지반조성ㆍ포장공사업": ("#CCFBF1", "#0D9488"),
    "실내건축공사업": ("#FAE8FF", "#C026D3"),
    "금속ㆍ창호ㆍ지붕ㆍ건축물조립공사업": ("#E0F2FE", "#0284C7"),
    "조경식재ㆍ시설물공사업": ("#ECFCCB", "#65A30D"),
    "상ㆍ하수도설비공사업": ("#CFFAFE", "#0891B2"),
    "철도ㆍ궤도공사업": ("#E0E7FF", "#4F46E5"),
    "수중ㆍ준설공사업": ("#E0F2F1", "#0F766E"),
    "승강기ㆍ삭도공사업": ("#F3E8FF", "#9333EA"),
    "기계설비ㆍ가스공사업": ("#E2E8F0", "#475569"),
    "가스ㆍ난방공사업": ("#FEF3C7", "#B45309"),
    "공사관리(원청·감리)": ("#F1F5F9", "#64748B"),
}
OTHER_COLORS = ("#EEF0F3", "#8A93A3")


def trade_colors(trade: str) -> tuple[str, str]:
    """업종 → (옅은 바탕, 진한 색). 목록에 없으면 회색."""
    return TRADE_COLORS.get(trade, OTHER_COLORS)


def trade_color(trade: str) -> str:
    return trade_colors(trade)[1]


def trade_bg(trade: str) -> str:
    return trade_colors(trade)[0]


def work_color(label: str) -> str:
    """작업 점 색 = 그 작업 업종의 진한 색(달력 막대의 글자·선과 같다)."""
    return trade_color(TRADE_OF_KIND.get(label, ""))


templates.env.globals["trade_bg"] = trade_bg
templates.env.globals["trade_color"] = trade_color
templates.env.globals["short_trade"] = short_trade_name
templates.env.globals["work_color"] = work_color
# 업체가 맡는 업종 고르기(D-088): (이름, 법령 업종인가)
templates.env.globals["work_trade_options"] = tuple((t.name, t.legal) for t in WORK_TRADES)


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
