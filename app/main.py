"""FastAPI 앱 생성과 기능 라우터 연결만 담당한다. 업무 로직은 app/features/에 둔다."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="gongon")

    # 프로세스 생존 확인용(liveness). DB·외부 API 상태는 확인하지 않는다.
    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
