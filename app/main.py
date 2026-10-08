"""FastAPI 앱 생성과 기능 라우터 연결만 담당한다. 업무 로직은 app/features/에 둔다."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.errors import install_error_handlers
from app.core.templating import STATIC_DIR
from app.features.judgments.router import router as judgments_router
from app.features.schedules.router import router as schedules_router
from app.features.sites.router import router as sites_router


def create_app() -> FastAPI:
    app = FastAPI(title="gongon")
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


app = create_app()
