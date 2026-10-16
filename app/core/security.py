"""쓰기 요청의 요청 위조 방지(D-057): Origin(없으면 Referer)이 이 앱과 같은 호스트여야 한다.

세션 쿠키 SameSite=Lax와 함께 쓴다. 현행 브라우저는 폼 POST에 Origin을 보낸다.
둘 다 없는 쓰기 요청은 출처를 확인할 수 없으므로 거부한다.
"""

from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

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
