# 구조: 기능 → 폴더 → 진입점 → 의존 관계

단일 FastAPI 앱이 같은 저장소의 `engine/`을 호출한다. 서비스·저장소 분리는 하지 않는다.
상태 표기: **있음**(실제 파일 존재) / **계획**(해당 작업에서 생성. 그 전에 빈 폴더를 만들지 않음)

## 1. 기능 위치

| 기능 | 폴더 | 대표 진입점(계획 포함) | 상태 | 작업 |
| --- | --- | --- | --- | --- |
| 앱 생성·라우터 연결 | `app/main.py` | `create_app()` | 있음 | S00 |
| 전체 검증 | `scripts/check.py` | 린트·포맷·타입·테스트(CI와 동일) | 있음 | S00 |
| 기준 원문·버전 | `rules/` | `rules/steel.yaml`(공종별 파일) | 계획 | S01 |
| 판정 데이터 계약 | `docs/schema.json` | JSON Schema | 계획 | S01 |
| 위치·격자 변환 | `engine/geo/` | `latlon_to_kma_grid()` | 있음 | S02-1 |
| 예보 수집·정규화 | `engine/forecast/` | 수집 → 원자료 + 정규화 시계열 | 계획 | S02-2 |
| 순수 판정 | `engine/judgment/` | `judge(weather_input, rule_set) -> JudgmentResult` | 계획 | S03 |
| 공통 기반 | `app/core/` | `config.py`(설정), `db.py`(세션), 로깅 | 계획 | S04-1 |
| 회원·인증 | `app/features/auth/` | `router.py`, 현재 사용자 의존성 | 계획 | S04-2 |
| 현장 등록·설정 | `app/features/sites/` | `router.py`, `service.py`(화면은 예시 데이터 `sample.py`) | 화면만 있음 | S05-0 → S04-3·S05 |
| 판정 저장·조회·상세 | `app/features/judgments/` | `service.py`(화면은 예시 데이터 `sample.py`, 이후 engine 호출 + 저장) | 화면만 있음 | S05-0 → S04-4·S05 |
| 알림 | `app/features/notifications/` | 메시지 생성·발송 어댑터(미리보기 어댑터만, 알림톡은 사업자 등록 후 D-015)·발송 이력 | 계획 | S06 |
| 실행 작업 | `app/jobs/` | `daily_forecast_judgment_notify` | 계획 | S06 |
| DB 변경 이력 | `migrations/` | Alembic 리비전 | 계획 | S04-1 |
| 작업 일정·변경 | `app/features/schedules/` | — | 계획(첫 확장) | S08·S09 |
| 팀·공유·확인 | `app/features/teams/` | — | 계획(첫 확장) | S09 |
| 실제 작업 기록 | `app/features/work_records/` | — | 계획(첫 확장) | S10 |
| 집계·보고서·비용 | `app/features/reports/` | — | 계획(선택) | S11 |

기능 폴더 안에는 필요한 것만 둔다: `router.py`(API) · `schemas.py`(입출력) · `service.py`(처리, 다른 기능이 부르는 공개 진입점) ·
`repository.py`(DB 접근) · `models.py`(DB 모델) · `templates/`(화면).

## 2. 의존 규칙

```text
app/main.py ──> app/features/* ──> app/core/
                     │
app/jobs/ ───────────┴──> engine/forecast, engine/geo, engine/judgment
engine/forecast ──> engine/judgment (입력 타입만, 필요할 때)
engine/judgment, engine/geo ──> (표준 라이브러리, 전달받은 데이터)
```

`tests/test_import_boundaries.py`가 강제하는 규칙:
- `engine/` ↛ `app/`
- `engine/judgment/` ↛ DB·HTTP·웹(`sqlalchemy`, `psycopg`, `alembic`, `httpx`, `httpx2`, `requests`, `urllib.request`, `fastapi`, `starlette`), `engine.forecast`, `engine.geo`
- `engine/geo/` ↛ 같은 DB·HTTP·웹, `engine.forecast`, `engine.judgment`
- `app/core/` ↛ `app.features`, `app.jobs`
- `app/features/<A>/` ↛ `app.features.<B>`의 `repository`·`models`·`router` (B ≠ A). 다른 기능은 `service`·`schemas`로만 호출

리뷰로 확인하는 규칙: 기능 간 순환 참조 금지, `app/jobs/`는 순서만 연결(판정·발송 로직은 각 기능 `service.py`), 팀 기능은 메시지를 직접 보내지 않고 `notifications` 서비스에 요청.
규칙을 바꾸면 테스트·이 문서·`docs/decisions.md`를 함께 갱신한다.

## 3. 코드 작성 규칙

| 주제 | 규칙 |
| --- | --- |
| 언어 | 식별자는 영어, 사용자에게 보이는 문구와 판정 값은 한국어. 판정은 영문 멤버·한국어 값의 `StrEnum`(예: `Verdict.STOP_REVIEW = "중지 검토"`)으로 S01에서 계약과 함께 정의 |
| 엔진 타입 | `engine/` 입출력은 표준 `dataclass(frozen=True, slots=True)`. 외부 자료(기준 YAML, 기상청 응답)는 들어오는 경계에서 검증 후 변환 |
| API 타입 | 기능별 `schemas.py`의 Pydantic 모델. 엔진 결과 → API 형식 변환은 해당 기능 `service.py`에서 |
| 시각 | 시간대 있는 `datetime`만(ruff `DTZ`가 검사). KST 상수는 S01에서 `engine/` 안 한 곳에 정의하고 재사용 |
| 예상 가능한 데이터 문제 | 누락·비교 불가는 예외가 아니라 결과 값(`판정 불가`·`확인 필요` + 사유)으로 표현 |
| 실패 | 외부 호출 실패는 원인을 담은 기능별 예외로 올리고 수집·발송 상태(성공/실패/사유/시도 횟수)로 저장. `except Exception: pass`처럼 삼키지 않음 |
| 설정 | 환경 변수는 `app/core/config.py` 한 곳에서 읽음. 엔진에는 값을 인자로 전달(엔진이 환경 변수를 직접 읽지 않음) |
| 판정 내역 | 저장 후 수정하지 않고 새로 추가(당시 판단을 다시 확인할 수 있게) |
| 로깅 | 표준 `logging`. 수집·판정·발송 로그에 현장 ID·예보 발표 시각·발송 키를 포함 |

## 4. 화면

서버 렌더링(FastAPI + Jinja2)으로 기능별 `app/features/<기능>/templates/`에 둔다(D-004). JS 빌드 단계는 두지 않는다.
문구·용어·색상 값은 `docs/brand.md`.
- 공통 기반: `app/core/templating.py`(Jinja2 설정, 기능이 `register_template_dir()`로 자기 templates를 등록), `app/core/templates/base.html`(레이아웃·메뉴), `_macros.html`(아이콘·판정 배지), `app/core/static/gongon.css`(brand.md 토큰을 CSS 변수로 옮김, `/static/`).
- 기능 화면: `app/features/<기능>/templates/<기능>/*.html`. 서버 렌더링 링크로 동작하고(탭·필터는 쿼리 문자열) JS는 쓰지 않는다. 예외로 현장 필터 `<select>`만 `onchange` 제출을 쓴다(`<noscript>` 버튼 대체).
- 예시 데이터 단계(S05-0): 각 기능의 `sample.py`가 데이터를, `service.py`가 화면 모델(`schemas.py`)을 만든다. 화면에 "예시 데이터" 표시를 둔다. DB 연결 시 `service.py`만 바꾸고 템플릿은 유지한다.

## 5. 테스트

- 경로는 구현을 따른다: `engine/judgment/x.py` → `tests/engine/judgment/test_x.py`, `app/features/notifications/service.py` → `tests/app/features/notifications/test_service.py`.
- 실제 네트워크·외부 계정 없이 실행한다. 외부 API는 어댑터를 가짜로 바꿔 검증한다.
- DB 테스트는 PostgreSQL에서 실행한다(준비 방법은 S04-1에서 결정, D-005). 여러 테스트가 쓰는 준비 코드는 `tests/conftest.py`에 둔다.

## 6. 데이터 무결성·최적화 설계 (구현 작업에서 적용)

| 주제 | 결정 | 확인 방법 | 작업 |
| --- | --- | --- | --- |
| 시각 | 계약은 `+09:00` 포함 ISO 8601, DB는 `timestamptz` | 시간대 없는 값 거부 테스트 | S01·S04 |
| 단위 | 필드 이름에 단위 표기(`_mps`, `_mm_per_h`, `_cm_per_h`, `_c`) | 계약 검증 | S01 |
| 자료 구분 | 예보 / 현장 관측 / 담당자 결정 / 실제 작업 기록을 다른 테이블·타입으로 저장 | 스키마 리뷰 | S04·S08~S10 |
| 예보 재사용 | 수집 단위는 (발표 시각, 격자 nx·ny). 같은 격자의 현장들은 한 번 수집한 자료를 공유 | 가짜 어댑터 호출 수: 같은 격자 현장 N곳 → 수집 1회 | S02-2·S06 |
| 판정 재사용 | 판정 내역 키에 예보 발표 시각·격자·기준 버전 포함. 하나라도 다르면 새로 판정 | 기준 버전만 바뀐 입력 → 새 판정 테스트 | S04-4·S06 |
| 알림 중복 방지 | 발송 키(현장, 대상 날짜, 알림 종류, 수신자) 고유 제약 + 상태 기록, 재실행 시 성공 건 건너뜀 | 같은 작업 2회 실행 → 발송 1회 | S06 |
| 조회 범위 | 현장 소유권 조건을 쿼리에 포함, 목록은 기간·페이지 제한 | 쿼리 수 측정: 목록 건수가 늘어도 쿼리 수 고정(N+1 없음) | S04 |

측정 도구: 외부 호출 수는 가짜 어댑터의 호출 기록, 쿼리 수는 SQLAlchemy `before_cursor_execute` 이벤트로 세는 테스트 공용 도구(S04-1에서 `tests/conftest.py`에 추가). 응답 시간은 필요할 때만 측정하고 조건·전후 값을 기록한다.
