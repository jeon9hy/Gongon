"""FastAPI 앱 생성과 기능 라우터 연결만 담당한다. 업무 로직은 app/features/에 둔다."""

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.templating import STATIC_DIR
from app.features.judgments.auto_refresh import run_hourly
from app.features.judgments.router import router as judgments_router
from app.features.schedules.router import router as schedules_router
from app.features.sites.router import router as sites_router


def create_app(auto_refresh: bool = False) -> FastAPI:
    """auto_refresh: 매시 전체 현장 자동 판정(D-043). 테스트는 끈다(외부 호출 없음)."""

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(run_hourly()) if auto_refresh else None
        yield
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="gongon", lifespan=lifespan)
    install_error_handlers(app)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(judgments_router)
    app.include_router(sites_router)
    app.include_router(schedules_router)

    # 프로세스 생존 확인용(liveness). DB·외부 API 상태는 확인하지 않는다.
    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app(auto_refresh=get_settings().auto_refresh)
