"""쓰기 요청의 요청 위조 방지(D-057): Origin(없으면 Referer)이 이 앱과 같은 호스트여야 한다.

세션 쿠키 SameSite=Lax와 함께 쓴다. 현행 브라우저는 폼 POST에 Origin을 보낸다.
둘 다 없는 쓰기 요청은 출처를 확인할 수 없으므로 거부한다.
"""

from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def is_same_origin(headers: Headers) -> bool:
    host = headers.get("host", "")
    source = headers.get("origin") or headers.get("referer")
    # 프록시 뒤에서 scheme이 바뀔 수 있어 호스트(포트 포함)만 비교한다.
    return bool(host and source and urlsplit(source).netloc == host)


class SameOriginMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] in UNSAFE_METHODS
            and not is_same_origin(Headers(scope=scope))
        ):
            response = PlainTextResponse("요청 출처를 확인할 수 없습니다.", status_code=403)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


class NoStoreHtmlMiddleware:
    """화면(HTML)은 브라우저가 저장하지 않게 한다.

    뒤로 가기 때 저장본 대신 서버에 다시 물어서, 로그인 뒤의 로그인 화면은 홈으로,
    로그아웃 뒤의 앱 화면은 로그인으로 보낸다(로그인 상태와 다른 화면을 보여 주지 않음)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if headers.get("content-type", "").startswith("text/html"):
                    headers["cache-control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_header)
