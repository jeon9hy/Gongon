"""테스트용 외부 API 가짜."""

import json
from typing import Any


class FakeKma:
    """기상청 getVilageFcst·getMidLandFcst 가짜. 응답 구조는 활용가이드 형식, 값은 테스트가 정한다.

    중기예보는 mid_item을 정하지 않으면 실제 '자료 없음' 형식(resultCode 03)으로 답한다.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self.mid_calls: list[dict[str, str]] = []
        self.mid_item: dict[str, Any] | None = None
        # (fcstDate, fcstTime) → {category: value}
        self.values: dict[tuple[str, str], dict[str, str]] = {}
        self.fail_with: Exception | None = None
        # 특일 정보(공휴일) 가짜: {"20261003": "개천절"}. 형식은 실제 getRestDeInfo 응답과 같다.
        self.holidays: dict[str, str] = {}
        self.holiday_calls: list[dict[str, str]] = []
        for hour in range(24):
            self.set_hour(
                "20261005", hour, PCP="강수없음", WSD="2.0", SNO="적설없음", TMP="20", REH="50"
            )

    def set_hour(self, fcst_date: str, hour: int, **values: str) -> None:
        self.values.setdefault((fcst_date, f"{hour:02d}00"), {}).update(values)

    def __call__(self, url: str, params: dict[str, str], timeout_s: float) -> bytes:
        if "MidFcstInfoService" in url:
            return self._mid(params)
        if "SpcdeInfoService" in url:
            self.holiday_calls.append(params)
            if self.fail_with is not None:
                raise self.fail_with
            year = params["solYear"]
            item = [
                {
                    "dateKind": "01",
                    "dateName": name,
                    "isHoliday": "Y",
                    "locdate": int(day),
                    "seq": 1,
                }
                for day, name in sorted(self.holidays.items())
                if day.startswith(year)
            ]
            found: dict[str, Any] = {
                "items": {"item": item} if item else "",
                "totalCount": len(item),
            }
            return json.dumps(
                {"response": {"header": {"resultCode": "00"}, "body": found}}
            ).encode()
        self.calls.append(params)
        if self.fail_with is not None:
            raise self.fail_with
        items: list[dict[str, Any]] = [
            {
                "baseDate": params["base_date"],
                "baseTime": params["base_time"],
                "category": category,
                "fcstDate": fcst_date,
                "fcstTime": fcst_time,
                "fcstValue": value,
                "nx": int(params["nx"]),
                "ny": int(params["ny"]),
            }
            for (fcst_date, fcst_time), values in sorted(self.values.items())
            for category, value in values.items()
        ]
        body = {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
                "body": {
                    "dataType": "JSON",
                    "items": {"item": items},
                    "pageNo": 1,
                    "numOfRows": len(items),
                    "totalCount": len(items),
                },
            }
        }
        return json.dumps(body, ensure_ascii=False).encode("utf-8")

    def _mid(self, params: dict[str, str]) -> bytes:
        self.mid_calls.append(params)
        if self.mid_item is None:
            body: dict[str, Any] = {
                "response": {"header": {"resultCode": "03", "resultMsg": "NO_DATA"}}
            }
        else:
            body = {
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
                    "body": {"dataType": "JSON", "items": {"item": [self.mid_item]},
                             "pageNo": 1, "numOfRows": 10, "totalCount": 1},
                }
            }  # fmt: skip
        return json.dumps(body, ensure_ascii=False).encode("utf-8")
