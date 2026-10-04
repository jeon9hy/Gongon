"""DB 설정·연결 문제를 500 대신 원인과 해결 방법이 보이는 화면으로 바꾼다."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.exc import OperationalError

from app.core.db import DatabaseNotConfiguredError
from app.core.templating import templates

logger = logging.getLogger(__name__)


def install_error_handlers(app: FastAPI) -> None:
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


def _render(request: Request, title: str, hint: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "error.html",
        {"nav_active": "", "title": title, "hint": hint},
        status_code=503,
    )
