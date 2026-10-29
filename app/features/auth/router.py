from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.templating import register_template_dir, templates
from app.features.auth import service
from app.features.auth.schemas import AuthView, SignupForm

register_template_dir(Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False)

SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(now_kst)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _render(request: Request, name: str, view: AuthView, status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(
        request, f"auth/{name}.html", {"nav_active": "", "view": view}, status_code=status_code
    )


def _signed_in(token: str, next_path: str, settings: Settings) -> RedirectResponse:
    response = RedirectResponse(service.safe_next(next_path), status_code=303)
    response.set_cookie(
        service.SESSION_COOKIE,
        token,
        max_age=int(service.SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )
    return response


def _signed_in_already(request: Request, session: Session, now: datetime) -> bool:
    return service.resolve(session, request.cookies.get(service.SESSION_COOKIE), now) is not None


@router.get("/login", response_model=None)
def login_page(request: Request, session: SessionDep, now: NowDep, next: str = "/") -> Response:
    # 로그인한 뒤 뒤로 가기로 다시 와도 로그인 화면을 보이지 않는다
    if _signed_in_already(request, session, now):
        return RedirectResponse(service.safe_next(next), status_code=303)
    return _render(request, "login", AuthView(next_path=service.safe_next(next)))


@router.post("/login")
def login(
    request: Request,
    session: SessionDep,
    now: NowDep,
    settings: SettingsDep,
    email: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "/",
) -> Response:
    user_id = service.authenticate(session, email, password)
    if user_id is None:
        view = AuthView(
            next_path=service.safe_next(next),
            email=email.strip(),
            errors=("이메일 또는 비밀번호가 맞지 않습니다.",),
        )
        return _render(request, "login", view, status_code=401)
    return _signed_in(service.start_session(session, user_id, now), next, settings)


@router.get("/signup", response_model=None)
def signup_page(request: Request, session: SessionDep, now: NowDep, next: str = "/") -> Response:
    if _signed_in_already(request, session, now):
        return RedirectResponse(service.safe_next(next), status_code=303)
    return _render(request, "signup", AuthView(next_path=service.safe_next(next)))


@router.post("/signup")
def signup(
    request: Request,
    session: SessionDep,
    now: NowDep,
    settings: SettingsDep,
    email: Annotated[str, Form()] = "",
    display_name: Annotated[str, Form()] = "",
    organization_name: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "/",
) -> Response:
    form = SignupForm(email, display_name, organization_name, password, phone)
    user_id, errors = service.signup(session, form)
    if user_id is None:
        view = AuthView(
            next_path=service.safe_next(next),
            email=email.strip(),
            display_name=display_name.strip(),
            organization_name=organization_name.strip(),
            phone=phone.strip(),
            errors=errors,
        )
        return _render(request, "signup", view, status_code=422)
    return _signed_in(service.start_session(session, user_id, now), next, settings)


@router.post("/logout")
def logout(request: Request, session: SessionDep) -> RedirectResponse:
    token = request.cookies.get(service.SESSION_COOKIE)
    if token:
        service.end_session(session, token)
    response = RedirectResponse(service.signed_out_landing(request), status_code=303)
    response.delete_cookie(service.SESSION_COOKIE)
    return response
