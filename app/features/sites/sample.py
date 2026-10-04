"""화면 확인용 예시 현장. 실제 현장이 아니며 S04-3에서 DB 조회로 바꾼다."""

from app.features.sites.schemas import SiteSetting

SITES = (
    SiteSetting(1, "○○현장", "서울특별시 ○○구 ○○로 00", 37.5665, 126.9780, True, "07:00", "17:00", True, ""),
    SiteSetting(2, "△△현장", "부산광역시 △△구 △△로 00", 35.1796, 129.0756, True, "08:00", "18:00", False, ""),
)  # fmt: skip
