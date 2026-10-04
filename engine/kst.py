"""한국 표준시. 한국은 일광절약시간이 없어 고정 오프셋을 쓴다(D-008 택일, tzdata 불필요)."""

from datetime import timedelta, timezone

KST = timezone(timedelta(hours=9), "KST")
