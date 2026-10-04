# 현재 작업 인계

- 현재 작업: 기본 흐름(D-019) — S01 doing, S02-2·S03·S04-1·3·4·S05 review · 마지막 수정 도구: Claude Code
- 브랜치: `feature/S04-basic-app` (`feature/S02-1-geo-grid` 위에서 분기. `main`은 아직 커밋 없음)
- 완료한 부분
  - 현장 등록·수정(위경도 → 기상청 격자) → 대시보드 "지금 판정하기" → 기상청 단기예보 수집(발표 시각·격자 재사용) → 철골 판정 → 저장 → 대시보드·상세·내역
  - 기준표 `rules/steel.yaml`(원문 대조 전), 엔진 `engine/judgment`, 수집 `engine/forecast`, DB `migrations/0001_initial`
  - 기준 미확인 공종(크레인·고소작업대 등)은 판정하지 않고 `확인 필요`로만 표시(D-017)
  - 예시 데이터 `sample.py`는 삭제. 로그인·알림 발송은 보류(D-019)
  - 홈(전체 현장 개요)·현장 대시보드 분리, 주소 자동완성(카카오, D-022), 작업 기간(D-023, 마이그레이션 0002)
- 개발자가 할 일 (막힌 조건)
  1. **PostgreSQL 17 설치·DB 생성·`.env`의 `DATABASE_URL` 설정** → `docs/setup.md` "DB 준비". 이게 없어서 `start.bat`이 마이그레이션 단계에서 멈추고 웹앱이 안 열림(2026-10-04 확인)
  2. (완료) 기상청 키: 공공데이터포털 `KMA_SERVICE_KEY`로 실제 호출 성공, `.env`에 설정됨(D-021)
  3. (선택) 카카오 REST API 키 → `.env`의 `KAKAO_REST_API_KEY` → 현장 이름 자동완성(D-022, `docs/setup.md`)
  4. 제383조 원문 대조 → `rules/steel.yaml`의 `quote`·`source_verified`
- 다음 작업 후보: `docs/schema.json`(S01) · 쿼리 수 측정 도구(S04-1) · S06 매일 17시 실행·알림 미리보기 저장 · S04-2 로그인
- 메모
  - 한글 경로: `uv run python -m pytest|alembic|uvicorn`으로 실행(`.exe` trampoline 실패). `alembic.ini`는 ASCII만
  - Git Bash `curl`은 한글 폼 값을 cp949로 보내 422가 난다. 화면 확인은 브라우저나 Python으로
  - 헤드리스 Edge 캡처는 명령이 끝난 뒤 조금 늦게 파일이 생긴다
- 미커밋 변경: 없음(커밋 전 `git status`로 확인)
- 검증(2026-10-04, 로컬 Windows): `scripts/check.py` 전체 ok — 임시 PostgreSQL 16.2(pgserver, 설치 없이 실행, 프로젝트 의존성 아님)에 `TEST_DATABASE_URL`을 걸어 DB 테스트 포함 실행. DB 없이 실행하면 DB 테스트 24개는 건너뜀(통과 아님). Alembic upgrade·downgrade·check 확인. 헤드리스 Edge로 대시보드(수집 실패·가짜 예보 성공)·상세·현장 설정 확인
- CI: `postgres:17` 서비스 추가(아직 GitHub에서 실행 확인 전 — push 후 확인)
- 결정 사항: D-001~D-023 (`docs/decisions.md`)
- 그 밖의 막힌 조건: Codex 모델 설정(S00). `공온지수` 구현 금지(D-010)
