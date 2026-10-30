# 구조: 기능 → 폴더 → 진입점 → 의존 관계

단일 FastAPI 앱이 같은 저장소의 `engine/`을 호출한다(서비스 분리 없음). 요구사항은 `product.md`, 작업 순서는 `plan.md`.
새 폴더·파일은 그 기능을 구현하는 작업에서 만든다. 빈 폴더·빈 추상화 계층을 미리 만들지 않는다.

## 1. 기능 위치

| 기능 | 폴더 | 대표 진입점 |
| --- | --- | --- |
| 앱 생성·라우터 연결 | `app/main.py` | `create_app()`(미들웨어·라우터·`/healthz`만) |
| 공통 기반 | `app/core/` | `config.py`(환경 변수는 여기서만), `db.py`(세션), `clock.py`(`now_kst`, 테스트에서 고정), `formats.py`(폼 값 읽기·날짜 표시), `params.py`(빈 `site_id=`는 미선택), `rules.py`(기준표·판정 공종), `work_kinds.py`(작업 고르기, D-085), `files.py`(올린 파일 보관 어댑터, D-111), `security.py`(같은 출처 검사 D-057·HTML 캐시 금지), `ui_mode.py`(앱/웹 화면 고르기, D-109), `templating.py`, `errors.py` |
| 회원·인증 | `app/features/auth/` | `/login`·`/signup`·`/logout`, `service.require_user`(모든 기능 라우터의 로그인 의존성) |
| 현장 등록·설정 | `app/features/sites/` | `service.list_sites`·`get_site`(삭제한 현장 제외, D-040), 주소 → 위경도(`places.py`, 카카오) |
| 현장 참여·역할·업체 | `app/features/teams/` | `service.site_ids_for`·`require_role`·`AccessibleSitesDep`(모든 조회·쓰기 범위), 참여 업체·담당자 명부·현장 코드(D-095) |
| 작업 일정 | `app/features/schedules/` | `service.items_on`·`items_between_for_sites`, `apply_plan_change`(계획 버전, 커밋 없음·낙관적 잠금), 공정표 가져오기 `importer.py`(D-086), 공휴일 `holidays.py` |
| 변경 건 | `app/features/changes/` | 제안·검토·확정·철회·재변경·종료. 확정은 한 트랜잭션에서 일정·조치를 함께 저장 |
| 후속 조치 | `app/features/actions/` | 후보·요청·수락·보류·완료 보고·검증·제외·위임, `closure_problems`(종료 조건) |
| 예보 수집 기록 | `app/features/forecasts/` | `service.get_forecast()`(발표 시각·격자 재사용, 실패 기록) |
| 판정·홈·내역 | `app/features/judgments/` | `service.run_for_site()`(engine 호출 + 저장), `build_home`·`build_dashboard`·`build_history`·`build_inbox`, 매시 자동 판정 `auto_refresh.py`(D-043) |
| 현장 대화방 | `app/features/chat/` | 현장당 방 하나, 사진·연락처·변경 건·조치 첨부(D-071·D-111) |
| 현장 게시 화면 | `app/features/board/` | `/board/{site}` 읽기 전용(board 역할, D-067) |
| 서류 | `app/features/reports/` | 공사일보(`work_reports`)·주간 작업계획표·기상 작업중지 기록·차질 집계·변경 건 문서(D-112~D-114) |
| 서비스 사이트 | `app/features/intro/` | `/`(로그인 전 소개, 로그인 뒤 내 현장 → `/home`), `/features`·`/collab`·`/about`·`/pricing`(D-110·D-115) |
| 가이드·내 정보 | `app/features/help/` | `/guide`(화면에서 뺀 설명), `/me` |
| 위치·격자 변환 | `engine/geo/` | `latlon_to_kma_grid()` |
| 예보 정규화 | `engine/forecast/` | `kma.py`(단기), `mid.py`(중기), `daily.py`, `sensible.py`(체감온도) |
| 순수 판정 | `engine/judgment/` | `judge()`, `load_rule_set()`, 공온지수 `index.py`(D-052), 중기 참고 `mid_reference.py` |
| 한국 표준시·공휴일 | `engine/kst.py`, `engine/holidays.py` | `KST`(고정 +09:00) |
| 기준 원문·버전 | `rules/` | 공종별 YAML, 원문 발췌 `rules/sources/` |
| 판정 데이터 계약 | `docs/schema.json`, `docs/contract.md` | 저장 판정 JSON v1.0, `judgments.service.serialize_judgment()` |
| 협업 계약 | `docs/collab-contract.md` | 권한·상태 전이·조치·서류 |
| DB 변경 이력 | `migrations/versions/` | Alembic 리비전(번호 순, 손으로 작성) |
| 스크립트 | `scripts/` | `check.py`(전체 검증), 시연 자료 `seed_*.py`, 원문 수집·대조 `fetch_*`·`verify_law_sources.py`, `grant_site.py`, `start.bat` |
| 디자인(Figma) | `design/figma/` | 공온 · 웹/앱 파일을 그리는 use_figma 스크립트. 앱 화면을 바꾸면 해당 스크립트도 고친다(README) |

아직 없는 것: 발송 대기·재시도(`app/features/notifications/`, C07 남은 일, 실제 알림톡은 D-015). 만들 때 이 표에 더한다.

기능 폴더에는 필요한 것만 둔다: `router.py`(HTTP) · `schemas.py`(입출력·화면 모델) · `service.py`(처리, 다른 기능이 부르는 공개 진입점) · `repository.py`(DB 조회가 길 때) · `models.py`(DB 모델) · `templates/<기능>/`(화면). 한 기능의 `service.py`가 너무 커지면 같은 폴더의 모듈로 나누되 다른 기능은 계속 `service`만 부른다.

## 2. 의존 규칙

```text
app/main.py ──> app/features/* ──> app/core/
                     └──────────> engine/forecast, engine/geo, engine/judgment
engine/forecast ──> engine/judgment (입력 타입만)
engine/judgment, engine/geo ──> (표준 라이브러리, 전달받은 데이터)
```

`tests/test_import_boundaries.py`가 강제한다:
- `engine/` ↛ `app/`
- `engine/judgment/` ↛ DB·HTTP·웹(`sqlalchemy`, `psycopg`, `alembic`, `httpx`, `httpx2`, `requests`, `urllib.request`, `fastapi`, `starlette`), `engine.forecast`, `engine.geo`
- `engine/geo/` ↛ 같은 DB·HTTP·웹, `engine.forecast`, `engine.judgment`
- `app/core/` ↛ `app.features`
- `app/features/<A>/` ↛ `app.features.<B>`의 `repository`·`models`·`router`(B ≠ A). 다른 기능은 `service`·`schemas`로만

리뷰로 확인한다: 기능 간 순환 호출 금지, 호출된 서비스는 중간 커밋·외부 발송을 하지 않는다(커밋은 요청을 받은 기능이 한 번), 권한은 teams 서비스로 서버에서 확인하고 화면에서 숨기는 것으로 대신하지 않는다.
규칙을 바꾸면 테스트·이 문서·`decisions.md`를 함께 고친다.

## 3. 코드 작성 규칙

| 주제 | 규칙 |
| --- | --- |
| 언어 | 식별자는 영어, 사용자에게 보이는 문구와 판정 값은 한국어. 판정은 영문 멤버·한국어 값의 `StrEnum`(`Verdict.STOP_REVIEW = "중지 검토"`) |
| 엔진 타입 | `engine/` 입출력은 `dataclass(frozen=True, slots=True)`. 외부 자료(기준 YAML, 기상청 응답)는 들어오는 경계에서 검증 후 변환 |
| 화면·API 타입 | 기능별 `schemas.py`. DB·엔진 결과 → 화면 모델 변환은 그 기능의 `service.py` |
| 시각 | 시간대 있는 `datetime`만(ruff `DTZ`). `engine.kst.KST` 하나를 쓴다. DB에서 읽은 시각은 `.astimezone(KST)` 뒤에 비교·표시 |
| 공통 형식 | 폼 값 읽기(`parse_int`·`parse_date`·`parse_time`)와 요일·날짜 문구(`weekday_name`·`day_text`)는 `app/core/formats.py`. 기능마다 다시 만들지 않는다 |
| 예상 가능한 데이터 문제 | 누락·비교 불가는 예외가 아니라 결과 값(`판정 불가`·`확인 필요` + 사유) |
| 실패 | 외부 호출 실패는 원인을 담은 예외로 올리고 수집·발송 상태(성공/실패/사유/시도 횟수)로 저장. `except Exception: pass` 금지 |
| 설정 | 환경 변수는 `app/core/config.py`에서만. 엔진에는 값을 인자로 전달 |
| 판정 내역 | 저장 후 수정하지 않고 새로 추가 |
| 로깅 | 표준 `logging`. 수집·판정·발송 로그에 현장 ID·예보 발표 시각·발송 키 |

## 4. 화면

서버 렌더링(FastAPI + Jinja2, D-004), JS 빌드 없음. 문구·용어·색은 `docs/brand.md`.
- 공통: `app/core/templating.py`(기능이 `register_template_dir()`로 자기 templates 등록), `templates/base.html`(틀·메뉴), `_macros.html`(아이콘·판정 배지·툴팁), `static/gongon.css`(brand 토큰 → CSS 변수), `static/app.css`(앱 화면만), 웹·앱 공용 스크립트 `static/*.js`.
- `service.py`가 화면 모델을 만들고 템플릿은 표시만 한다. 쓰기(폼)는 POST 후 303으로 GET 화면에 돌아간다(새로고침 중복 실행 방지). 탭·필터는 쿼리 문자열, JS는 보조 상호작용에만(외부 API 결과는 `textContent`로만 넣는다).
- **앱 화면/웹 화면(D-109)**: 주소·라우터·권한·화면 모델은 하나, 템플릿만 둘. `ui_mode.py` 미들웨어가 `request.state.ui_mode`(`app`|`web`)를 정한다(`?ui=` → 쿠키 `gongon_ui` → User-Agent `GongonApp` → 휴대폰 브라우저, 태블릿은 웹). `DeviceTemplates`는 앱이면 `<기능>/app/<화면>.html`을 먼저 찾고 없으면 웹 화면을 쓴다. 새 앱 화면은 **라우터를 고치지 않고** 같은 이름의 `app/` 템플릿만 더한다. 상세 화면은 `{% block app_bar scoped %}`로 뒤로 가기, `{% set hide_tabbar = true %}`로 아래 탭 숨김(예: `chat/app/room.html`).
- **PC 웹은 반응형이 아니다**: 좁은 화면 규칙(`max-width` ≤ 960px)은 모두 `html[data-narrow]`(앱 화면·모달 안 embed)로 묶고, PC 웹은 `body` 최소 폭 1024px. 새 좁은 화면 규칙에도 `html[data-narrow]`를 붙인다.
- 확인: PC에서 주소 끝 `?ui=app`(되돌리기 `?ui=web`), 휴대폰 실기기는 `--host 0.0.0.0`으로 켜고 같은 와이파이에서 `http://<PC IP>:8000`.
- 쓰지 않게 된 CSS 선택자·그림은 그 작업에서 지운다(동적 클래스 `x--{{ 값 }}`은 템플릿에서 확인).

## 5. 테스트

- 경로는 구현을 따른다: `engine/judgment/x.py` → `tests/engine/judgment/test_x.py`, `app/features/<기능>/…` → `tests/app/features/<기능>/test_*.py`.
- 실제 네트워크·외부 계정 없이 실행한다. 외부 API는 어댑터를 가짜로 바꾼다(`tests/fakes.py`).
- DB 테스트는 PostgreSQL(`TEST_DATABASE_URL`, D-020). `tests/conftest.py`가 마이그레이션 적용·시험마다 표 비우기(DELETE + setval)·현재 시각 고정(`FIXED_NOW`)·외부 API 가짜·가벼운 비밀번호 해시를 맡는다.
- 쿼리 수는 픽스처 `count_queries`(SQLAlchemy `before_cursor_execute`)로 센다. 주요 목록 화면은 `tests/app/test_query_counts.py`가 작업 건수와 무관함을 확인한다. 새 목록 화면은 `PAGES`에 더한다. 성능 개선은 전후 쿼리 수·응답 시간을 적은 경우에만 주장한다.
- 화면 테스트가 HTML을 `</section>`으로 잘라 보는 곳이 있다(홈). 섹션 안에 `<section>`을 넣지 않는다.

## 6. 데이터 무결성·최적화

| 주제 | 결정 | 확인 방법 |
| --- | --- | --- |
| 시각 | 계약은 `+09:00` 포함 ISO 8601, DB는 `timestamptz` | 시간대 없는 값 거부, `PGTZ=UTC` 재실행 |
| 단위 | 필드 이름에 단위(`_mps`, `_mm_per_h`, `_cm_per_h`, `_c`) | 계약 검증 |
| 자료 구분 | 예보 / 현장 관측 / 담당자 결정 / 후속 조치 / 실제 작업 결과(`work_reports`)를 다른 테이블로 | 스키마 리뷰 |
| 예보 재사용 | 수집 단위는 (발표 시각, 격자 nx·ny). 같은 격자의 현장은 한 번 수집한 자료를 공유 | 가짜 어댑터 호출 수: 같은 격자 N곳 → 1회 |
| 판정 재사용 | 판정 키에 발표 시각·격자·기준 버전. 하나라도 다르면 새로 판정 | 기준 버전만 바뀐 입력 → 새 판정 |
| 조회 범위 | 현장 권한 조건을 쿼리에 포함, 목록은 기간·건수 제한 | 건수가 늘어도 쿼리 수 고정(N+1 없음) |
| 변경 확정 | 계획 갱신·확정 버전·조치(·발송 대기)를 한 트랜잭션. 외부 발송은 커밋 후 | 확정 실패 시 아무것도 남지 않음 |
| 버전 | 계획 버전·변경 버전은 보존하고 재변경은 새 버전. 구버전 보고·검증은 최신 완료로 치지 않음 | 구버전 revision_id 거부 |
| 종료 | 현재 확정 버전의 필수 조치가 검증·제외되고 보류가 없을 때만(잠금 후 확인) | 종료 조건 테스트 |
| 알림 중복 방지(C07) | 발송 키(현장·변경 버전·조치·수신자·채널·종류·회차) 고유 제약. 공급자 응답 유실은 확인 불가로 남김 | 같은 작업 2회 실행 → 발송 1회 |

매시 자동 판정(D-043)은 단일 프로세스 시연 구조다. 여러 프로세스로 배포하기 전에 실행 중복 제어를 검증한다.
DB 모델(`models.py`)은 컬럼 중심이고 인덱스·부분 고유·CHECK 제약은 마이그레이션에만 둔다. 그래서 `alembic check`는 차이를 보고하며 쓰지 않는다. 마이그레이션은 손으로 쓰고 테스트가 실제 PostgreSQL에 적용해 확인한다.
