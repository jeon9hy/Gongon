"""가입·로그인·세션 확인(D-057). 다른 기능은 require_user로 로그인 사용자를 받는다.

비밀번호는 hashlib.scrypt, 세션 쿠키에는 임의 토큰, DB에는 그 SHA-256만 둔다.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_session
from app.features.auth.models import AuthSession, Organization, User
from app.features.auth.schemas import CurrentUser, SignupForm

SESSION_COOKIE = "gongon_session"
SESSION_TTL = timedelta(hours=12)
PASSWORD_MIN = 10
PASSWORD_MAX = 128
EMAIL_MAX = 200
NAME_MAX = 40
ORGANIZATION_MAX = 60

# 약 16MB 메모리·수십 ms. 바꾸면 저장된 해시는 그 값에 적힌 매개변수로 계속 검증된다.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = _scrypt(password, bytes.fromhex(salt_hex), int(n), int(r), int(p))
    return hmac.compare_digest(digest, bytes.fromhex(digest_hex))


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=64 * 1024 * 1024, dklen=32
    )


@lru_cache
def _dummy_hash() -> str:
    """없는 이메일도 같은 시간만큼 검증해 가입 여부를 응답 시간으로 드러내지 않는다."""
    return hash_password(secrets.token_hex(16))


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_signup(session: Session, form: SignupForm) -> tuple[str, ...]:
    errors: list[str] = []
    email = normalize_email(form.email)
    local, at, domain = email.partition("@")
    if not (local and at and "." in domain) or " " in email or len(email) > EMAIL_MAX:
        errors.append("이메일 형식을 확인하세요.")
    elif session.scalar(select(User.id).where(User.email == email)) is not None:
        errors.append("이미 가입한 이메일입니다. 로그인하세요.")
    if not 1 <= len(form.display_name.strip()) <= NAME_MAX:
        errors.append(f"이름을 1~{NAME_MAX}자로 입력하세요.")
    if not 1 <= len(form.organization_name.strip()) <= ORGANIZATION_MAX:
        errors.append(f"회사 이름을 1~{ORGANIZATION_MAX}자로 입력하세요.")
    if not PASSWORD_MIN <= len(form.password) <= PASSWORD_MAX:
        errors.append(f"비밀번호는 {PASSWORD_MIN}~{PASSWORD_MAX}자로 입력하세요.")
    return tuple(errors)


def signup(session: Session, form: SignupForm) -> tuple[int | None, tuple[str, ...]]:
    """회사와 사용자를 함께 만든다. 같은 회사의 다른 사용자 연결은 실제 사업자 확인 전이라 없다."""
    errors = validate_signup(session, form)
    if errors:
        return None, errors
    organization = Organization(name=form.organization_name.strip())
    session.add(organization)
    session.flush()
    user = User(
        email=normalize_email(form.email),
        display_name=form.display_name.strip(),
        password_hash=hash_password(form.password),
        organization_id=organization.id,
    )
    session.add(user)
    session.commit()
    return user.id, ()


def authenticate(session: Session, email: str, password: str) -> int | None:
    user = session.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        verify_password(password, _dummy_hash())
        return None
    if not verify_password(password, user.password_hash) or not user.is_active:
        return None
    return user.id


def start_session(session: Session, user_id: int, now: datetime) -> str:
    """원 토큰을 돌려준다(쿠키 값). 만료된 이 사용자의 세션도 함께 정리한다."""
    session.execute(
        delete(AuthSession).where(AuthSession.user_id == user_id, AuthSession.expires_at <= now)
    )
    token = secrets.token_urlsafe(32)
    session.add(
        AuthSession(
            user_id=user_id,
            token_sha256=_token_hash(token),
            created_at=now,
            expires_at=now + SESSION_TTL,
        )
    )
    session.commit()
    return token


def end_session(session: Session, token: str) -> None:
    session.execute(delete(AuthSession).where(AuthSession.token_sha256 == _token_hash(token)))
    session.commit()


def resolve(session: Session, token: str | None, now: datetime) -> CurrentUser | None:
    """만료·비활성 사용자의 세션은 없는 것으로 본다."""
    if not token:
        return None
    row = session.execute(
        select(User, Organization.name)
        .join(AuthSession, AuthSession.user_id == User.id)
        .join(Organization, Organization.id == User.organization_id)
        .where(AuthSession.token_sha256 == _token_hash(token), AuthSession.expires_at > now)
    ).first()
    if row is None or not row[0].is_active:
        return None
    user, organization_name = row
    return CurrentUser(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        organization_id=user.organization_id,
        organization_name=organization_name,
    )


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii", "replace")).hexdigest()


def safe_next(path: str | None) -> str:
    """로그인 뒤 돌아갈 주소. 다른 사이트로 보내지 않도록 이 앱의 경로만 허용한다."""
    if not path or not path.startswith("/") or path.startswith("//") or "\\" in path:
        return "/"
    return path


def require_user(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    now: Annotated[datetime, Depends(now_kst)],
) -> CurrentUser:
    """로그인이 필요한 화면의 의존성. 없으면 로그인 화면으로 보낸다(303)."""
    user = resolve(session, request.cookies.get(SESSION_COOKIE), now)
    if user is None:
        target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        raise HTTPException(
            status_code=303, headers={"Location": f"/login?next={quote(target, safe='')}"}
        )
    request.state.user = user  # 공통 레이아웃이 이름·로그아웃을 표시한다
    return user


CurrentUserDep = Annotated[CurrentUser, Depends(require_user)]
