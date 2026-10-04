# 구조: 기능 → 폴더 → 진입점 → 의존 관계

단일 FastAPI 앱이 같은 저장소의 `engine/`을 호출한다. 서비스·저장소 분리는 하지 않는다.
상태 표기: **있음**(실제 파일 존재) / **계획**(해당 작업에서 생성. 그 전에 빈 폴더를 만들지 않음)

## 1. 기능 위치

| 기능 | 폴더 | 대표 진입점(계획 포함) | 상태 | 작업 |
| --- | --- | --- | --- | --- |
| 앱 생성·라우터 연결 | `app/main.py` | `create_app()` | 있음 | S00 |
| 기준 원문·버전 | `rules/` | `rules/steel.yaml`(공종별 파일) | 계획 | S01 |
| 판정 데이터 계약 | `docs/schema.json` | JSON Schema | 계획 | S01 |
| 예보 수집·정규화 | `engine/forecast/` | `fetch_short_term_forecast()` → 원자료 + 정규화 시계열 | 계획 | S02 |
| 위치·격자 변환 | `engine/geo/` | `latlon_to_kma_grid()` | 계획 | S02 |
| 순수 판정 | `engine/judgment/` | `judge(weather_input, rule_set) -> JudgmentResult` | 계획 | S03 |
| 공통 기반 | `app/core/` | 설정 로딩, DB 세션, 로깅 | 계획 | S04 |
| 회원·인증 | `app/features/auth/` | `router.py`, 현재 사용자 의존성 | 계획 | S04 |
| 현장 등록·설정 | `app/features/sites/` | `router.py`, `service.py` | 계획 | S04·S05 |
| 판정 저장·조회·상세 | `app/features/judgments/` | `service.py`(engine 호출 + 저장) | 계획 | S04·S05 |
| 알림 | `app/features/notifications/` | 메시지 생성·발송 어댑터·발송 이력 | 계획 | S06 |
| 실행 작업 | `app/jobs/` | `daily_forecast_judgment_notify` | 계획 | S06 |
| DB 변경 이력 | `migrations/` | Alembic 리비전 | 계획 | S04 |
| 작업 일정·변경 | `app/features/schedules/` | — | 계획(첫 확장) | S08·S09 |
| 팀·공유·확인 | `app/features/teams/` | — | 계획(첫 확장) | S09 |
| 실제 작업 기록 | `app/features/work_records/` | — | 계획(첫 확장) | S10 |
| 집계·보고서·비용 | `app/features/reports/` | — | 계획(선택) | S11 |

기능 폴더 안에는 필요한 것만 둔다: `router.py`(API) · `schemas.py`(입출력) · `service.py`(처리) ·
`repository.py`(DB 접근) · `models.py`(DB 모델) · `templates/`(화면).

## 2. 의존 규칙

```text
app/main.py ──> app/features/* ──> app/core/
                     │
app/jobs/ ───────────┴──> engine/forecast, engine/geo, engine/judgment
engine/forecast ──> engine/judgment (입력 타입만, 필요할 때)
engine/judgment ──> (표준 라이브러리, 기준 데이터)
```

- `engine/`은 `app/`을 import하지 않는다. — 테스트로 강제
- `engine/judgment/`는 DB(`sqlalchemy`, `psycopg`)·HTTP(`httpx`, `httpx2`, `requests`, `urllib.request`)·웹(`fastapi`, `starlette`)·`engine.forecast`·`engine.geo`를 import하지 않는다. 기준은 데이터로 전달받는다. — 테스트로 강제
- 기능 간 호출은 상대 기능의 `service.py` 공개 함수로만 한다. 다른 기능의 `repository.py`·`models.py`를 직접 쓰지 않는다. 순환 참조 금지. — 리뷰로 확인
- `app/jobs/`는 순서만 연결한다. 판정·발송 로직은 각 기능 `service.py`에 있다.
- 팀 기능은 메시지를 직접 보내지 않고 `notifications` 서비스에 요청한다.
- 강제 규칙 위치: `tests/test_import_boundaries.py`의 `BOUNDARY_RULES`. 규칙을 바꾸면 이 문서와 `docs/decisions.md`도 갱신한다.

## 3. 화면

서버 렌더링(FastAPI + Jinja2)으로 기능별 `app/features/<기능>/templates/`에 둔다(D-004). JS 빌드 단계는 두지 않는다.
예: 판정 상세 화면 → `app/features/judgments/templates/`.

## 4. 테스트 위치

구현 경로를 그대로 따른다: `engine/judgment/x.py` → `tests/engine/judgment/test_x.py`,
`app/features/notifications/service.py` → `tests/app/features/notifications/test_service.py`.
구조 규칙 테스트: `tests/test_import_boundaries.py`.

## 5. 데이터 무결성·최적화 설계 (구현 작업에서 적용)

| 주제 | 결정 | 적용 작업 |
| --- | --- | --- |
| 시각 | 시간대 없는 datetime 금지(ruff `DTZ`). 계약은 `+09:00` 포함 ISO 8601, DB는 `timestamptz` | S01·S04 |
| 단위 | 필드 이름에 단위 표기(`_mps`, `_mm_per_h`, `_cm_per_h`, `_c`) | S01 |
| 자료 구분 | 예보 / 현장 관측 / 담당자 결정 / 실제 작업 기록을 다른 테이블·타입으로 저장 | S04·S08~S10 |
| 예보 재사용 | 수집 단위는 (발표 시각, 격자 nx·ny). 같은 격자의 현장들은 한 번 수집한 자료를 공유 | S02·S06 |
| 판정 재사용 | 판정 내역 키에 예보 발표 시각·격자·기준 버전을 포함. 하나라도 다르면 새로 판정 | S04·S06 |
| 알림 중복 방지 | 발송 키(현장, 대상 날짜, 알림 종류, 수신자) 고유 제약 + 상태(대기/성공/실패) 기록, 재실행 시 성공 건 건너뜀 | S06 |
| 조회 범위 | 현장 소유권 조건을 쿼리에 포함, 목록은 기간·페이지 제한 | S04 |
