"""현장 선택 폼의 빈 쿼리 값을 현장 미선택으로 해석한다."""

from typing import Annotated

from pydantic import BeforeValidator


def _blank_as_none(value: object) -> object:
    return None if value == "" else value


OptionalSiteIdQuery = Annotated[int | None, BeforeValidator(_blank_as_none)]
