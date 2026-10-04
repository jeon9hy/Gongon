"""커밋 전 전체 검증. CI도 이 스크립트를 실행하므로 로컬과 CI의 검증 범위가 같다.

사용: uv run python scripts/check.py          # 린트·포맷·타입·테스트
      uv run python scripts/check.py --fix    # 자동 수정 가능한 린트·포맷을 먼저 고친 뒤 검증
"""

import os
import subprocess
import sys

CHECK_STEPS: tuple[tuple[str, list[str]], ...] = (
    ("ruff check", ["ruff", "check", "."]),
    ("ruff format", ["ruff", "format", "--check", "."]),
    ("mypy", ["mypy"]),
    ("pytest", ["pytest", "-q", "-rs"]),
)
FIX_STEPS: tuple[list[str], ...] = (
    ["ruff", "check", "--fix", "."],
    ["ruff", "format", "."],
)


def run_module(args: list[str]) -> int:
    # Windows 콘솔에서도 한글 출력이 깨지지 않도록 UTF-8 모드로 실행한다.
    env = {**os.environ, "PYTHONUTF8": "1"}
    return subprocess.run([sys.executable, "-m", *args], env=env).returncode


def main(argv: list[str]) -> int:
    if "--fix" in argv:
        for args in FIX_STEPS:
            run_module(args)

    # 한 단계가 실패해도 나머지를 실행해 한 번에 모든 실패를 보여준다(재실행 횟수 감소).
    failed = [name for name, args in CHECK_STEPS if run_module(args) != 0]

    print()
    for name, _ in CHECK_STEPS:
        print(f"{'FAIL' if name in failed else 'ok  '}  {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
