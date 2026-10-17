# 구조: 기능 → 폴더 → 진입점 → 의존 관계

단일 FastAPI 앱이 같은 저장소의 `engine/`을 호출한다. 서비스·저장소 분리는 하지 않는다.
현재 제품의 요구사항은 `product.md`(D-068), 작업 순서는 `plan.md`의 C작업이다. 아래 S번호는 기존 구현 위치의 출처이며 새 제품 개발 순서가 아니다. 새 구조는 §7의 계획을 따른다.
상태 표기: **있음**(실제 파일 존재) / **계획**(해당 작업에서 생성. 그 전에 빈 폴더를 만들지 않음)

## 1. 기능 위치

| 기능 | 폴더 | 대표 진입점(계획 포함) | 상태 | 작업 |
| --- | --- | --- | --- | --- |
| 앱 생성·라우터 연결 | `app/main.py` | `create_app()` | 있음 | S00 |
| 전체 검증 | `scripts/check.py` | 린트·포맷·타입·테스트(CI와 동일) | 있음 | S00 |
| 기준 원문·버전 | `rules/` | `rules/steel.yaml`(공종별 파일, 원문 대조 전 초안) | 있음 | S01 |
| 판정 데이터 계약 | `docs/schema.json`, `docs/contract.md` | 저장 판정 JSON v1.0, `service.serialize_judgment()` | 있음 | S01-1 |
| 위치·격자 변환 | `engine/geo/` | `latlon_to_kma_grid()` | 있음 | S02-1 |
| 예보 수집·정규화 | `engine/forecast/` | `fetch_vilage_forecast()` → 원자료, `normalize()` → 판정 입력 | 있음 | S02-2 |
| 순수 판정 | `engine/judgment/` | `judge(weather, rule_set, work_start_at, work_end_at) -> JudgmentResult`, `load_rule_set()` | 있음 | S03 |
| 한국 표준시 | `engine/kst.py` | `KST`(고정 +09:00, D-018) | 있음 | S01 |
| 공통 기반 | `app/core/` | `config.py`(설정), `db.py`(세션), `rules.py`(기준표·공종 목록), `clock.py`(현재 시각), `errors.py`(DB 오류 화면) | 있음 | S04-1 |
| 회원·인증 | `app/features/auth/` | `/login`·`/signup`·`/logout`, `service.require_user`(모든 기능 라우터의 로그인 의존성), 회사·사용자·세션 | 있음 | C03-1 |
| 요청 위조 방지 | `app/core/security.py` | `SameOriginMiddleware`(쓰기 요청 Origin/Referer 검사, D-057) | 있음 | C03-1 |
| 현장 등록·설정 | `app/features/sites/` | `router.py`(등록·수정·삭제 폼), `service.py`(`list_sites`·`get_site` 공개, 삭제한 현장 제외 D-040) | 있음 | S04-3·S05 |
| 예보 수집 기록 | `app/features/forecasts/` | `service.get_forecast()`(발표 시각·격자 재사용, 실패 기록) | 있음 | S02-2·S04 |
| 판정 저장·조회·상세 | `app/features/judgments/` | `service.run_for_site()`(engine 호출 + 저장), 대시보드·상세·내역 화면 | 있음 | S04-4·S05 |
| 알림 | `app/features/notifications/` | 메시지 생성·발송 어댑터(미리보기 어댑터만, 알림톡은 사업자 등록 후 D-015)·발송 이력 | 계획 | S06 |
| 실행 작업 | `app/jobs/` | `daily_forecast_judgment_notify` | 계획 | S06 |
| DB 변경 이력 | `migrations/` | Alembic 리비전(`0001`~`0015_participant_roster`) | 있음 | S04-1 |
| 작업 일정·변경 | `app/features/schedules/` | `service.items_on()`·`items_on_for_sites()`(그날 작업), `/schedule` 화면 | 있음(S08-1) | S08·S09 |
| 현장 참여·역할 | `app/features/teams/` | `service.site_ids_for`·`require_role`·`AccessibleSitesDep`(모든 현장 조회·쓰기 범위), `/sites/{id}/members` 참여 업체·담당자 명부·참여자 화면(C04-9: 업체 등록·종료·재개, 명부, 계정 연결, `participant_choices` 참여 중 업체 선택지), `scripts/grant_site.py`(기존 현장 조정자 지정) | 있음 | C03-2 |
| 공온 가이드·내 정보 | `app/features/help/` | `/guide`(화면에서 뺀 설명 모음), `/me`(계정·참여 현장) | 있음 | C04-7 |
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
- `app/core/params.py`의 `OptionalSiteIdQuery`는 현장 선택 폼이 보내는 `site_id=`를 미선택(`None`)으로 받는다. 홈·일정·판정·내역에서 공유하며 다른 잘못된 정수 값과 현장별 접근 권한 검증은 유지한다(C04-26).
- 기능 화면: `app/features/<기능>/templates/<기능>/*.html`. 서버 렌더링 링크로 동작하고(탭·필터는 쿼리 문자열) JS는 보조 상호작용에만 쓴다. 예외: 모바일 달력의 날짜 상세 앵커 전환(D-037), 공종 칩 넘김 버튼(기본 가로 스크롤 유지), 현장 선택 `<select>`의 `onchange` 제출(`<noscript>` 버튼 대체), 현장 설정의 주소 찾기(다음 우편번호 서비스 외부 스크립트 + 템플릿 안 작은 스크립트, D-047 — JS 없이도 위경도 직접 입력으로 저장 가능). 외부 API 결과는 `textContent`로만 넣는다.
- `service.py`가 DB·엔진 결과로 화면 모델(`schemas.py`)을 만들고 템플릿은 표시만 한다. 쓰기(폼 제출)는 POST 후 303으로 GET 화면에 돌아간다(새로고침 중복 실행 방지). 예시 데이터 단계(S05-0)의 `sample.py`는 D-019에서 지웠다.

## 5. 테스트

- 경로는 구현을 따른다: `engine/judgment/x.py` → `tests/engine/judgment/test_x.py`, `app/features/notifications/service.py` → `tests/app/features/notifications/test_service.py`.
- 실제 네트워크·외부 계정 없이 실행한다. 외부 API는 어댑터를 가짜로 바꿔 검증한다.
- DB 테스트는 PostgreSQL에서 실행한다(`TEST_DATABASE_URL`, D-020). `tests/conftest.py`가 마이그레이션 적용·테스트마다 테이블 비우기·현재 시각 고정·외부 API 가짜(`tests/fakes.py`)를 맡는다.

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


## 7. 작업 변경 후속 조치 구조 (D-055, 구현 전 계획)

기존 단일 FastAPI·PostgreSQL·서버 렌더링을 유지한다. 첫 프로젝트 작업공간은 Site 재사용안이며 별도 Project 중복 테이블을 미리 만들지 않는다. 실제 마이그레이션·계약은 C02 이후 해당 작업에서 확정한다.

| 기능 | 위치 | 작업·현재 상태 |
| --- | --- | --- |
| 인증·세션 | app/features/auth | C03-1 있음 |
| 조직·프로젝트 참여·역할 | app/features/teams | C03-2 있음(위임은 C06), 회사 공통 관리자 없음. 참여 업체 단독 등록·종료·담당자 명부 C04-9 있음(D-066) |
| 작업·실행 업체·계획 버전 | app/features/schedules | C04 있음. 계획 저장은 `apply_plan_change`(커밋 없음, 낙관적 잠금) |
| 변경 버전·영향 검토·확정·종료 | app/features/changes | C05 있음(제안·검토·확정·철회·재변경, `_after_confirm`에 C06·C07을 더함). 종료는 C06 |
| 수행자 응답·막힘·완료·검증 | app/features/actions | C05·C06 계획 |
| 발송 대기·시도·열람 | app/features/notifications | C07 계획, 실제 알림톡 D-015 유지 |
| 현장 대화방 | app/features/messages | C12 계획(D-071). 현장당 방 하나, 권한은 teams 서비스, 조치·변경 만들기는 actions·changes 서비스 호출 |
| 현장 게시 화면(작업자용) | app/features/board | C11 계획(D-067). board 역할, 읽기 전용, 판정·변경·일정 서비스만 호출 |

기능 간 호출은 service·schemas만 사용한다. 변경 확정은 changes 서비스가 공유 DB 세션으로 schedules·actions·notifications의 저장 처리를 조정한다. 호출된 서비스는 중간 커밋·외부 발송을 하지 않으며 계획 갱신·확정 버전·조치·발송 대기는 한 트랜잭션이다. 서비스 순환 호출·상대 기능 ORM/repository 직접 접근을 만들지 않는다.

계획 버전·확정 변경 버전은 보존하며 재변경 때 새 버전을 만든다. 종료 검사는 현재 확정 버전과 필수 조치·막힘·제외 승인을 원자적으로 확인한다. 조치 보고의 버전과 현재 대상이 다르면 최신 완료로 처리하지 않는다. 실제 처리 시각·기록 시각·검증 시각을 분리한다.

발송 대기 키는 프로젝트·변경 버전·조치·수신자·채널·알림 종류와 재알림 회차로 구분한다. 공급자 응답 유실은 확인 불가로 남기며 외부 전송의 무조건 정확히 1회를 보장하지 않는다. 앱 내부 매시 15분 실행(D-043)은 단일 프로세스 시연 구조이므로 다중 프로세스 운영 전 실행 중복 제어를 검증한다.

조회·쓰기·첨부는 매번 프로젝트·참여 업체·역할·작업 범위를 서버에서 적용한다. 목록은 필요한 기간·상태·페이지로 제한한다. 권한 정책은 teams의 공개 서비스에서 확인하며 화면에서 숨기는 것으로 대신하지 않는다. 기존 기상 schema.json은 이번 문서 변경으로 수정하지 않았다. 새 협업 계약은 C02에서 정의하고 구현 시 함께 검증한다.
