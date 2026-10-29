"""요청마다 앱 화면과 웹 화면 중 하나를 고른다(D-109, 슬랙 방식 화면 분리).

주소·기능은 하나이고 화면(템플릿)만 다르다. 정하는 순서:
1. 주소의 `?ui=app|web` — 사용자가 직접 바꾼 값이며 쿠키에 남긴다.
2. 쿠키 `gongon_ui` — 이전에 바꾼 값.
3. 앱 껍데기(웹뷰)의 User-Agent 표시 `GongonApp`.
4. 휴대폰 브라우저(아이패드·태블릿은 웹 화면).
"""

import re
from http.cookies import SimpleCookie
from typing import Literal
from urllib.parse import parse_qs

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

UiMode = Literal["app", "web"]
UI_COOKIE = "gongon_ui"
UI_QUERY = "ui"
APP_SHELL_MARK = "GongonApp"
_PHONE_UA = re.compile(r"iPhone|iPod|Android.+Mobile|Windows Phone", re.IGNORECASE)
_COOKIE_MAX_AGE_S = 365 * 24 * 3600


def _as_mode(value: str | None) -> UiMode | None:
    return value if value in ("app", "web") else None  # type: ignore[return-value]


def detect(headers: Headers, query_string: bytes) -> tuple[UiMode, bool]:
    """(화면 종류, 주소로 바꿨는가). 바꿨으면 응답에 쿠키를 남긴다."""
    asked = _as_mode(parse_qs(query_string.decode("latin-1")).get(UI_QUERY, [None])[-1])
    if asked:
        return asked, True
    cookie = SimpleCookie(headers.get("cookie", ""))
    saved = _as_mode(cookie[UI_COOKIE].value) if UI_COOKIE in cookie else None
    if saved:
        return saved, False
    agent = headers.get("user-agent", "")
    return ("app" if APP_SHELL_MARK in agent or _PHONE_UA.search(agent) else "web"), False


def in_app_shell(headers: Headers) -> bool:
    """앱 껍데기 안이면 서비스 소개 없이 바로 로그인으로 간다(D-110)."""
    return APP_SHELL_MARK in headers.get("user-agent", "")


def ui_mode(request: Request) -> UiMode:
    return getattr(request.state, "ui_mode", "web")


class UiModeMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        mode, chosen = detect(Headers(scope=scope), scope.get("query_string", b""))
        scope.setdefault("state", {})["ui_mode"] = mode

        async def send_with_cookie(message: Message) -> None:
            if chosen and message["type"] == "http.response.start":
                MutableHeaders(scope=message).append(
                    "set-cookie",
                    f"{UI_COOKIE}={mode}; Path=/; Max-Age={_COOKIE_MAX_AGE_S}; SameSite=Lax",
                )
            await send(message)

        await self.app(scope, receive, send_with_cookie)
