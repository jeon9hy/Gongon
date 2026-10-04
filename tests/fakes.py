"""테스트용 외부 API 가짜."""

import json
from typing import Any


class FakeKma:
    """기상청 getVilageFcst 가짜. 응답 구조는 활용가이드 형식, 값은 테스트가 정한다."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        # (fcstDate, fcstTime) → {category: value}
        self.values: dict[tuple[str, str], dict[str, str]] = {}
        self.fail_with: Exception | None = None
        for hour in range(24):
            self.set_hour("20261005", hour, PCP="강수없음", WSD="2.0", SNO="적설없음")

    def set_hour(self, fcst_date: str, hour: int, **values: str) -> None:
        self.values.setdefault((fcst_date, f"{hour:02d}00"), {}).update(values)

    def __call__(self, url: str, params: dict[str, str], timeout_s: float) -> bytes:
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
