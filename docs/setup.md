# 실행·검증 환경

## 필요 도구
- Python 3.12, [uv](https://docs.astral.sh/uv/) (확인 버전: uv 0.12.15, Python 3.12.10, Windows 11)
- Git. 이 저장소의 커밋 작성자 설정은 저장소 로컬 설정(`git config user.name/user.email`)을 확인한다.

## 준비
```bash
uv sync --locked          # .venv 생성, uv.lock 그대로 설치 (잠금과 pyproject가 다르면 실패)
cp .env.example .env      # 실제 값은 .env에만(커밋 금지)
```
그다음 아래 "DB 준비"와 "기상청 인증키"를 한 번 해 둔다.

## DB 준비 (PostgreSQL 17, 처음 한 번)
1. 설치: https://www.postgresql.org/download/windows/ → "Download the installer"(EDB) → **17.x Windows x86-64**.
   설치 중 슈퍼유저(`postgres`) 비밀번호를 정하고 포트는 `5432` 그대로 둔다. 마지막 Stack Builder는 건너뛴다.
   - 대신 관리자 PowerShell에서 `winget install -e --id PostgreSQL.PostgreSQL.17`도 된다(설치 창에서 비밀번호 설정).
   - 시연 배포의 Supabase와 주 버전을 맞추려고 17을 쓴다(D-014).
2. DB 만들기: 시작 메뉴 → "SQL Shell (psql)" → 물음에 Enter(기본값)로 넘기고 비밀번호 입력 →
   ```sql
   CREATE DATABASE gongon;
   CREATE DATABASE gongon_test;
   ```
3. `.env`에 연결 문자열을 넣는다(비밀번호에 `@ : / % #`가 있으면 URL 인코딩 필요, 예: `@` → `%40`).
   ```
   DATABASE_URL=postgresql://postgres:<비밀번호>@localhost:5432/gongon
   TEST_DATABASE_URL=postgresql://postgres:<비밀번호>@localhost:5432/gongon_test
   ```
4. 테이블 만들기: `uv run python -m alembic upgrade head` (`scripts/start.bat`도 실행할 때마다 먼저 적용한다)

## 기상청 인증키 (처음 한 번)
키가 없어도 앱은 동작하지만 판정이 모두 `판정 불가 · 기상청 인증키가 설정되지 않음`으로 기록된다.
같은 단기예보를 두 곳에서 받을 수 있다. 하나만 하면 된다(둘 다 있으면 API허브 우선, D-021).

### A. 기상청 API허브
1. https://apihub.kma.go.kr 로그인 → 왼쪽 메뉴 **예특보** → **단기예보 조회서비스**(`VilageFcstInfoService_2.0`, 단기예보조회 `getVilageFcst`) → **활용신청**
2. 인증키(22자)를 `.env`의 `KMA_APIHUB_KEY=`에 넣고 앱 재시작
3. 확인: 대시보드에서 "지금 판정하기". 신청 전이면 `판정 불가 · 기상청 API허브 HTTP 403: ... 활용신청이 필요한 API`로 기록된다

### B. 공공데이터포털 (현재 사용 중)
1. https://www.data.go.kr 회원가입·로그인
2. 검색창에 **기상청_단기예보 ((구)_동네예보) 조회서비스** → 오픈 API 항목 → **활용신청**
   (활용 목적: 예) "학부 프로젝트 - 공종별 기상 판정 시연"). 개발 계정은 보통 자동 승인된다.
3. 마이페이지 → 데이터활용 → Open API → 활용신청 현황 → 이 서비스 → **일반 인증키 (Decoding)** 를 복사
   - Encoding 키가 아니라 **Decoding** 키를 쓴다. 코드가 주소에 넣을 때 직접 인코딩한다.
4. `.env`에 `KMA_SERVICE_KEY=<복사한 키>` → 앱 재시작
5. 확인: 대시보드에서 "지금 판정하기". 승인 직후에는 키가 기상청 서버에 반영되기까지 시간이 걸려
   `판정 불가 · 공공데이터포털 HTTP 403: ...SERVICE_KEY_IS_NOT_REGISTERED_ERROR`가 나올 수 있다. 1~2시간 뒤 다시 누른다.
- 하루 호출 한도는 활용신청 화면에 표시된다(개발 계정). 같은 발표 시각·격자는 한 번만 호출하고 재사용한다.

## 현장 위치 찾기 키 (선택, 카카오)
없어도 앱은 동작한다(위도·경도 직접 입력). 있으면 현장 이름을 2글자 이상 칠 때 장소 후보가 뜨고, 고르면 주소·위도·경도가 채워진다(D-022).
1. https://developers.kakao.com 로그인 → 앱 관리 페이지(https://developers.kakao.com/console/app) → **[앱 생성]**
   (앱 이름 예: 공온, 회사명: 개인은 본인 이름, 대표 도메인을 요구하면 `http://localhost:8000`) → [저장]
2. 만든 앱 → **[앱] > [플랫폼 키] > [REST API 키]** 값 복사 (호출 허용 IP는 선택, 비워 둠)
3. **[카카오맵] > [사용 설정] 상태 ON** (필수). 무료 쿼터는 개발자 계정당 처음 활성화한 앱 하나에만 준다
4. `.env`에 `KAKAO_REST_API_KEY=<복사한 키>` → **공온 실행을 다시 시작**(설정은 시작할 때 읽는다)
- 키는 서버에만 있고 브라우저에는 검색 결과만 간다. 키워드로 장소 검색 무료 쿼터는 하루 10만 건이고, 다 쓰면 유료 설정 전에는 429 오류로 막힌다(과금 아님). 출처: Kakao Developers 쿼터·카카오맵 문서(2026-10-04 확인)

## 검증
```bash
uv run python scripts/check.py         # 커밋 전 전체 검증: ruff check · ruff format --check · mypy · pytest (CI와 동일)
uv run python scripts/check.py --fix   # 린트·포맷 자동 수정 후 전체 검증
uv run python -m pytest tests/<경로> -q  # 작업 중 빠른 확인: 관련 테스트만
```
- `check.py`는 실패해도 나머지 단계를 모두 실행하고 끝에 단계별 ok/FAIL을 보여준다. 하나라도 실패하면 종료 코드 1.
- pytest의 건너뜀(skip)은 통과가 아니다. 사유는 `-rs` 출력으로 확인한다.
- DB 테스트는 `TEST_DATABASE_URL`(환경 변수 또는 `.env`)이 있어야 실행된다. 없으면 24개가 건너뜀으로 표시된다.
  테스트는 그 DB의 `public` 스키마를 지우고 마이그레이션을 다시 적용하므로, DB 이름에 `test`가 없으면 실행을 거부한다.
  CI는 `postgres:17` 서비스로 항상 실행한다.
- 외부 API는 호출하지 않는다(가짜 응답 `tests/fakes.py`).
- Windows 한글 출력: `check.py`는 UTF-8 모드로 실행한다. pytest를 직접 실행할 때 깨지면 `PYTHONUTF8=1`을 설정한다(Git Bash: `export PYTHONUTF8=1`, PowerShell: `$env:PYTHONUTF8=1`).

## 앱 실행
```bash
uv run python -m alembic upgrade head
uv run python -m uvicorn app.main:app --reload
# http://127.0.0.1:8000 → 현장 설정에서 현장 등록 → 대시보드에서 "지금 판정하기"
```
- 폴더의 `공온 실행.lnk`(또는 `scripts/start.bat`)가 PostgreSQL 확인·시작 → 마이그레이션 적용 → 서버 실행 → 브라우저 열기를 한다.
  - PostgreSQL 서비스가 꺼져 있으면 `scripts/ensure_postgres.bat`이 켠다. 서비스 시작에는 관리자 권한이 필요해 그때만 UAC 확인 창이 뜬다. 로컬 PostgreSQL 서비스가 없으면(원격 DB) 건너뛴다.
  - 설치 기본값은 윈도우 시작 시 자동 실행이라 보통은 이미 켜져 있다(개발자 PC는 PostgreSQL 18, D-014는 17 — 이 프로젝트에 차이 없음).
- DB가 꺼져 있거나 `DATABASE_URL`이 없으면 화면에 원인(503)을 보여준다.
- `uvicorn`·`alembic`을 직접 부르지 않고 `python -m`으로 실행한다. 한글이 든 경로에서 `.exe`가 `uv trampoline failed to canonicalize script path`로 실패한다.
- `.lnk`는 PC 절대 경로가 들어가 커밋하지 않는다(`.gitignore`). 필요하면 `start.bat`을 가리키는 바로가기를 직접 만든다.

## 의존성 변경
- S01-1 계약 검증은 개발 의존성 `jsonschema`, `rfc3339-validator`, `types-jsonschema`를 쓴다. `FormatChecker`로 날짜·시각 형식을 실제 검사한다. `uv run python -m pytest tests/app/features/judgments/test_contract.py -q`로 예시 및 DB 저장 결과를 확인한다. DB 없는 실행의 skip은 저장 흐름 검증 완료가 아니다.
- 추가: `uv add <패키지>` / 개발용: `uv add --dev <패키지>` → `pyproject.toml`과 `uv.lock`을 함께 커밋.
- 결정이 필요한 의존성(DB·HTTP 클라이언트 등)은 `docs/decisions.md`를 먼저 확인한다.

## 환경 변수
`.env.example` 참고. 코드에서는 `app/core/config.py`만 읽는다(환경 변수가 `.env`보다 우선).

| 변수 | 사용 위치 | 작업 | 상태 |
| --- | --- | --- | --- |
| `DATABASE_URL` | 앱·마이그레이션 | S04 | 개발자 PC에 PostgreSQL 설치 후 설정 |
| `KMA_SERVICE_KEY` | 예보 수집(공공데이터포털) | S02-2 | 설정됨, 실제 호출 확인(2026-10-04) |
| `KMA_APIHUB_KEY` | 예보 수집(API허브, 있으면 우선) | S02-2 | 비워 둠 — API허브는 구역 조회만 승인돼 단기예보 호출 불가 |
| `TEST_DATABASE_URL` | DB 테스트(선택) | S04 | 개발자 PC 설정됨. CI에서는 워크플로가 설정 |
| `KAKAO_REST_API_KEY` | 현장 위치 찾기(선택) | S05 | 미발급 — 위 "현장 위치 찾기 키" |

## DB 적용 절차
```bash
uv run python -m alembic upgrade head       # 최신으로 적용
uv run python -m alembic current            # 현재 리비전 확인
uv run python -m alembic downgrade -1       # 한 단계 되돌리기(데이터가 지워질 수 있음 — 운영 DB에서는 백업 먼저)
uv run python -m alembic check              # 모델과 마이그레이션 차이 확인(차이가 있으면 실패)
```
- 테이블 변경은 `migrations/versions/`에 새 리비전을 추가해서만 한다. 적용 실패 시 `alembic current`로 위치를 확인하고, 원인을 고친 뒤 다시 `upgrade head`.
