"""화면 렌더링 공통 기반. 기능은 자기 templates 폴더를 등록하고 공통 레이아웃을 상속한다."""

from datetime import time
from pathlib import Path

from fastapi.templating import Jinja2Templates
from jinja2 import FileSystemLoader

from app.core.work_kinds import TRADE_OF_KIND, WORK_TRADES, short_trade_name

CORE_DIR = Path(__file__).parent
STATIC_DIR = CORE_DIR / "static"

templates = Jinja2Templates(directory=CORE_DIR / "templates")


def static_url(name: str) -> str:
    """정적 파일 주소에 수정 시각을 붙인다. 파일이 바뀌면 주소도 바뀌어 옛 캐시를 쓰지 않는다."""
    version = int((STATIC_DIR / name).stat().st_mtime)
    return f"/static/{name}?v={version}"


templates.env.globals["static_url"] = static_url

# 업종(최상위 공종) 색(D-089, D-064 대체): (옅은 바탕, 같은 색상의 진한 색).
# 달력 막대는 옅은 바탕에 진한 글자·왼쪽 선, 작업 점은 진한 색이다.
# 판정 표시 색과 겹치지 않고 갈색·올리브 같은 탁한 색은 쓰지 않는다.
TRADE_COLORS = {
    "지반조성ㆍ포장공사업": ("#FCE6D6", "#C2662F"),
    "실내건축공사업": ("#FADDEB", "#B83A72"),
    "금속ㆍ창호ㆍ지붕ㆍ건축물조립공사업": ("#D8ECFA", "#2F7BB0"),
    "도장ㆍ습식ㆍ방수ㆍ석공사업": ("#FFE0DA", "#C4523F"),
    "조경식재ㆍ시설물공사업": ("#D9F2E4", "#2E8A5E"),
    "철근ㆍ콘크리트공사업": ("#DFE4FB", "#4655C2"),
    "구조물해체ㆍ비계공사업": ("#EBE0FA", "#7B48C4"),
    "상ㆍ하수도설비공사업": ("#D4F0EE", "#1F8A82"),
    "철도ㆍ궤도공사업": ("#E8E6EF", "#625C85"),
    "철강구조물공사업": ("#D6E6FE", "#2B63D9"),
    "수중ㆍ준설공사업": ("#D3F2F8", "#16849A"),
    "승강기ㆍ삭도공사업": ("#F5DDF5", "#A33D9B"),
    "기계설비ㆍ가스공사업": ("#DFE8F1", "#4A6B8F"),
    "가스ㆍ난방공사업": ("#EAF3D2", "#62841E"),
    "전기·정보통신·소방": ("#FDE2C4", "#B5650F"),
    "공사관리(원청·감리)": ("#E9ECF0", "#5A6577"),
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
