"""DB 설정·연결 문제를 500 대신 원인과 해결 방법이 보이는 화면으로 바꾼다.

찾을 수 없음(404)·권한 없음(403)도 JSON 대신 같은 화면으로 보인다.
그 밖의 상태(로그인 이동 303 등)는
FastAPI 기본 처리를 그대로 쓴다.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException

from app.core.db import DatabaseNotConfiguredError
from app.core.templating import templates

logger = logging.getLogger(__name__)


PAGE_STATUSES = {
    403: (
        "권한이 없습니다",
        "이 현장에서 이 작업은 조정자만 할 수 있습니다. 필요하면 현장 조정자에게 요청하세요.",
    ),
    404: (
        "찾을 수 없습니다",
        "없거나 참여하지 않은 현장·기록입니다. 참여가 필요하면 현장 조정자에게 요청하세요.",
    ),
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> Response:
        if error.status_code not in PAGE_STATUSES:
            return await http_exception_handler(request, error)
        title, hint = PAGE_STATUSES[error.status_code]
        return _render(request, title, hint, error.status_code, setup=False)

    @app.exception_handler(DatabaseNotConfiguredError)
    def db_not_configured(request: Request, error: DatabaseNotConfiguredError) -> HTMLResponse:
        return _render(
            request, "DB 설정이 필요합니다", ".env에 DATABASE_URL을 넣고 앱을 다시 시작하세요."
        )

    @app.exception_handler(OperationalError)
    def db_unreachable(request: Request, error: OperationalError) -> HTMLResponse:
        logger.error("DB 연결 실패: %s", error)
        return _render(
            request,
            "DB에 연결할 수 없습니다",
            "PostgreSQL이 실행 중인지, DATABASE_URL과 마이그레이션 적용 여부를 확인하세요.",
        )


def _render(
    request: Request, title: str, hint: str, status_code: int = 503, setup: bool = True
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "error.html",
        {"nav_active": "", "title": title, "hint": hint, "setup": setup},
        status_code=status_code,
    )
