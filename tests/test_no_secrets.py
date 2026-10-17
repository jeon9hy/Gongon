""".env의 키·비밀번호가 저장소에 들어가지 않는지 검사한다(개발자 요청 2026-10-17).

로컬에서는 .env의 실제 값이 추적 파일(git ls-files)에 없는지 보고, CI처럼 .env가 없으면
.env가 무시 목록에 있는지만 본다. 값은 실패 메시지에도 남기지 않는다.
"""

import subprocess
from pathlib import Path

from app.core.config import ENV_FILE, REPO_ROOT, read_env_file

# 짧은 값(0·1 같은 설정)은 우연히 겹치므로 비밀로 보지 않는다.
MIN_SECRET_CHARS = 8


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8"
    )


def test_env_files_are_ignored() -> None:
    # check-ignore: 무시 대상이면 0, 아니면 1
    assert git("check-ignore", "-q", "--no-index", ".env").returncode == 0
    assert git("check-ignore", "-q", "--no-index", ".env.local").returncode == 0
    assert git("check-ignore", "-q", "--no-index", ".env.example").returncode == 1


def test_env_values_are_not_in_tracked_files() -> None:
    values = {
        name: value
        for name, value in read_env_file(ENV_FILE).items()
        if len(value) >= MIN_SECRET_CHARS
    }
    secrets = set()
    for name, value in values.items():
        secrets.add((name, value))
        if "://" in value and "@" in value:  # 연결 문자열 안의 비밀번호
            password = value.split("://", 1)[1].split("@", 1)[0].partition(":")[2]
            if len(password) >= MIN_SECRET_CHARS - 2:
                secrets.add((f"{name} 비밀번호", password))
    leaked = []
    for path in git("ls-files").stdout.splitlines():
        file = Path(REPO_ROOT, path)
        if not file.is_file() or file.suffix in {".png", ".woff2", ".ico", ".lnk"}:
            continue
        text = file.read_text(encoding="utf-8", errors="ignore")
        leaked += [f"{path}: {name}" for name, value in secrets if value in text]
    assert not leaked, leaked
