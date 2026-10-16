from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """로그인한 사용자. 다른 기능은 이 값으로 권한을 확인한다(teams 서비스)."""

    user_id: int
    email: str
    display_name: str
    organization_id: int
    organization_name: str


@dataclass(frozen=True, slots=True)
class SignupForm:
    email: str = ""
    display_name: str = ""
    organization_name: str = ""
    password: str = ""


@dataclass(frozen=True, slots=True)
class AuthView:
    """로그인·가입 화면. 비밀번호는 다시 채우지 않는다."""

    next_path: str
    email: str = ""
    display_name: str = ""
    organization_name: str = ""
    errors: tuple[str, ...] = ()
    message: str | None = None
