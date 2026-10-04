"""화면 확인용 예시 데이터. 실제 예보·판정이 아니며 S04-4에서 DB 조회로 바꾼다.

값은 docs/brand.md 시안(예시)의 숫자를 그대로 옮겼다. 기준값·기준 버전은 [원문 대조 필요] 상태다.
"""

from app.features.judgments.schemas import (
    Criterion,
    Element,
    ElementSeries,
    HistoryRow,
    HourRow,
    NoticeItem,
    Tile,
    WorkVerdict,
    WorkWindow,
)

HOURS = tuple(range(7, 17))  # 07:00~16:00 정시

SERIES: dict[Element, ElementSeries] = {
    "rain": ElementSeries(
        key="rain",
        label="강우",
        unit="mm/h",
        threshold=1.0,
        axis_max=2.5,
        hourly_values=(0, 0, 0, 0, 0, 0, 0.6, 1.0, 2.0, 1.5),
        over_hours=frozenset({14, 15, 16}),
    ),
    "wind": ElementSeries(
        key="wind",
        label="풍속",
        unit="m/s",
        threshold=10,
        axis_max=12,
        hourly_values=(2.1, 2.4, 3.0, 3.6, 4.2, 4.8, 5.5, 6.4, 6.1, 5.2),
        over_hours=frozenset(),
    ),
    "snow": ElementSeries(
        key="snow",
        label="강설",
        unit="cm/h",
        threshold=1.0,
        axis_max=1.5,
        hourly_values=(0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        over_hours=frozenset(),
    ),
}

SITE_NAME = "○○현장"
TARGET_DATE = "10월 5일(월)"
WORK_HOURS = "07:00–17:00"
FORECAST_ISSUED = "10월 4일 14:00"
RULE_VERSION = "2025-07-17 시행"

WINDOWS = (
    WorkWindow("07:00–13:00", "진행", None),
    WorkWindow("13:00–17:00", "중지 검토", "15:00 강우 2.0 mm/h · 기준 1.0 mm/h 이상"),
)
TILES = (
    Tile("진행", 7),
    Tile("확인 필요", 0),
    Tile("중지 검토", 3),
    Tile("판정 불가", 0),
)
# 공종 목록은 sites 예시 데이터의 ○○현장과 같다. 콘크리트 타설은 총정리 §1의 기온 기준만 비교한 예시다.
WORK_VERDICTS = (
    WorkVerdict("철골 작업", "13:00–17:00", "중지 검토", "15:00 강우 2.0 mm/h · 기준 1.0 mm/h 이상", "/judgments/1"),
    WorkVerdict("타워크레인 운전", "07:00–17:00", "확인 필요",
                "기준은 순간풍속인데 예보는 평균 풍속(최대 6.4 m/s)이라 직접 비교할 수 없음 · 현장 풍속계 확인", None),
    WorkVerdict("콘크리트 타설", "07:00–17:00", "진행", "기온 기준만 비교 · 일평균 17℃, 최고 22℃ (한중·서중 조건 아님)", None),
    WorkVerdict("고소작업대", "07:00–17:00", "확인 필요", "판정 기준 확인 전 · 현장에서 직접 판단", None),
)  # fmt: skip
NOTICE_TITLE = "[공온] 내일(10/5) ○○현장"
NOTICE_ITEMS = (
    NoticeItem("철골 13:00–17:00", "중지 검토", "강우"),
    NoticeItem("타워크레인", "확인 필요", "순간풍속"),
    NoticeItem("고소작업대", "확인 필요", "기준 확인 전"),
)
NOTICE_DISCLAIMER = "최종 판단은 현장 책임자가 합니다."

DETAIL_CHIPS = (
    "자료 유형: 예보 (현장 관측 아님)",
    "예보 발표 2026-10-04 14:00 KST",
    "판정 시각 2026-10-04 14:13 KST",
    "기준 버전 2025-07-17 시행",
    "기상청 격자 {grid}",
)
SOURCE = "산업안전보건기준에 관한 규칙 제383조"
CRITERIA = (
    Criterion("강우", "PCP", "rain", "중지 검토", "2.0", "mm/h", "15:00",
              "기준: 시간당 1.0 mm 이상 → 중지 검토", SOURCE),
    Criterion("풍속", "WSD", "wind", "진행", "6.4", "m/s", "14:00",
              "기준: 10 m/s 이상 → 중지 검토", SOURCE),
    Criterion("강설", "SNO", "snow", "진행", "0.0", "cm/h", None,
              "기준: 시간당 1 cm 이상 → 중지 검토", SOURCE),
)  # fmt: skip
HOUR_ROWS = (
    HourRow("13:00", "0.6", "5.5", "0.0", False, "진행", "모든 요소 기준 미만", False),
    HourRow("14:00", "1.0", "6.4", "0.0", True, "중지 검토", "강우 1.0 ≥ 1.0 (기준과 같음, ‘이상’에 해당)", False),
    HourRow("15:00", "2.0", "6.1", "0.0", True, "중지 검토", "강우 2.0 ≥ 1.0 · 구간 최댓값", True),
    HourRow("16:00", "1.5", "5.2", "0.0", True, "중지 검토", "강우 1.5 ≥ 1.0", False),
)  # fmt: skip

DETAIL_JUDGMENT_ID = 1  # 상세 예시가 있는 판정은 첫 행 하나뿐이다
HISTORY = (
    HistoryRow(1, "10/05(월)", "○○현장", "철골 13:00–17:00", "중지 검토", "10/04 14:00", "2025-07-17", None),
    HistoryRow(None, "10/05(월)", "○○현장", "철골 07:00–13:00", "진행", "10/04 14:00", "2025-07-17", None),
    HistoryRow(None, "10/05(월)", "○○현장", "타워크레인 07:00–17:00", "확인 필요", "10/04 14:00", "2025-07-17", "순간풍속은 예보로 직접 비교 불가"),
    HistoryRow(None, "10/05(월)", "○○현장", "콘크리트 타설 07:00–17:00", "진행", "10/04 14:00", "2025-07-17", None),
    HistoryRow(None, "10/05(월)", "○○현장", "고소작업대 07:00–17:00", "확인 필요", "10/04 14:00", "—", "판정 기준 확인 전"),
    HistoryRow(None, "10/05(월)", "△△현장", "철골 08:00–18:00", "진행", "10/04 14:00", "2025-07-17", None),
    HistoryRow(None, "10/05(월)", "△△현장", "이동식 크레인 08:00–18:00", "확인 필요", "10/04 14:00", "—", "판정 기준 확인 전"),
    HistoryRow(None, "10/02(금)", "○○현장", "철골 07:00–17:00", "진행", "10/01 14:00", "2025-07-17", None),
    HistoryRow(None, "10/01(목)", "○○현장", "철골 07:00–17:00", "판정 불가", "—", "2025-07-17", "예보 수집 실패 · 재시도 기록 있음"),
    HistoryRow(None, "09/30(수)", "△△현장", "철골 08:00–18:00", "중지 검토", "09/29 14:00", "2025-07-17", None),
    HistoryRow(None, "09/29(화)", "○○현장", "철골 07:00–17:00", "진행", "09/28 14:00", "2025-07-17", None),
    HistoryRow(None, "09/28(월)", "○○현장", "철골 07:00–17:00", "진행", "09/27 14:00", "2025-07-17", None),
)  # fmt: skip
