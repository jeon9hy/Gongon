# 실행·검증 환경

## 필요 도구
- Python 3.12, [uv](https://docs.astral.sh/uv/) (확인 버전: uv 0.12.15, Python 3.12.10, Windows 11)
- Git. 이 저장소의 커밋 작성자 설정은 저장소 로컬 설정(`git config user.name/user.email`)을 확인한다.

## 준비
```bash
uv sync --locked          # .venv 생성, uv.lock 그대로 설치 (잠금과 pyproject가 다르면 실패)
cp .env.example .env      # 실제 값은 .env에만. 현재(S00) 코드가 읽는 변수는 없음
```

## 검증
```bash
uv run python scripts/check.py         # 커밋 전 전체 검증: ruff check · ruff format --check · mypy · pytest (CI와 동일)
uv run python scripts/check.py --fix   # 린트·포맷 자동 수정 후 전체 검증
uv run pytest tests/<경로> -q          # 작업 중 빠른 확인: 관련 테스트만
```
- `check.py`는 실패해도 나머지 단계를 모두 실행하고 끝에 단계별 ok/FAIL을 보여준다. 하나라도 실패하면 종료 코드 1.
- pytest의 건너뜀(skip)은 통과가 아니다. 사유는 `-rs` 출력으로 확인한다.
- Windows 한글 출력: `check.py`는 UTF-8 모드로 실행한다. pytest를 직접 실행할 때 깨지면 `PYTHONUTF8=1`을 설정한다(Git Bash: `export PYTHONUTF8=1`, PowerShell: `$env:PYTHONUTF8=1`).

## 앱 실행
```bash
uv run python -m uvicorn app.main:app --reload
# 확인: http://127.0.0.1:8000/healthz → {"status":"ok"}
```
- 폴더의 `공온 실행.lnk`(또는 `scripts/start.bat`)가 같은 명령을 실행하고 브라우저를 연다. 화면(S05)이 생기기 전에는 `/`가 404다.
- `uvicorn`을 직접 부르지 않고 `python -m`으로 실행한다. 한글이 든 경로에서 `uvicorn.exe`가 `uv trampoline failed to canonicalize script path`로 실패한다.
- `.lnk`는 PC 절대 경로가 들어가 커밋하지 않는다(`.gitignore`). 필요하면 `start.bat`을 가리키는 바로가기를 직접 만든다.

## 의존성 변경
- 추가: `uv add <패키지>` / 개발용: `uv add --dev <패키지>` → `pyproject.toml`과 `uv.lock`을 함께 커밋.
- 결정이 필요한 의존성(DB·HTTP 클라이언트 등)은 `docs/decisions.md`를 먼저 확인한다.

## 환경 변수
`.env.example` 참고. 변수 이름은 코드가 실제로 읽기 시작하는 작업에서 확정하고 여기 표에 추가한다.

| 변수 | 사용 위치 | 작업 | 상태 |
| --- | --- | --- | --- |
| `KMA_SERVICE_KEY` | 예보 수집 | S02 | 키 미발급 |
| `DATABASE_URL` | DB 연결 | S04 | DB 미생성 |

## DB 적용 절차
S04에서 Alembic 도입 후 작성한다(적용·되돌리기·실패 시 복구 명령).
