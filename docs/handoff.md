# 현재 작업 인계

- 현재 작업 ID / 상태: S02-1 / review · 마지막 수정 도구: Claude Code
- 브랜치: `feature/S02-1-geo-grid` (S00 브랜치에서 분기. `main`은 아직 커밋 없음)
- 완료한 부분
  - S00: 환경·CI·공통 지침·문서·브랜드 규칙. 남은 것은 Codex가 `AGENTS.md`를 읽는지 확인(plan.md S00)
  - 로컬 실행 도구: `scripts/start.bat`, 폴더의 `공온 실행.lnk`(커밋 안 함). 화면(S05) 전이라 `/`는 404, 확인은 `/healthz`
  - S02-1: `engine/geo/grid.py` `latlon_to_kma_grid()` + `tests/engine/geo/test_grid.py`. `check.py` 전체 ok
- 남은 부분
  - S02-1: 공식 격자 파일의 다른 지점으로 테스트 보강(plan.md S02-1 체크 항목)
  - S00: Codex 확인 → done → `main` 반영
- 메모: 한글이 든 경로에서 `uv run pytest`·`uvicorn.exe`는 `uv trampoline failed` 오류. `uv run python -m pytest`, `python -m uvicorn` 사용(`check.py`는 영향 없음, setup.md)
- 미커밋 변경: S02-1 구현·문서(커밋 전 `git status`로 확인)
- 검증(2026-10-04, 로컬 Windows): `uv run python scripts/check.py` ruff·format·mypy·pytest 모두 ok (24 통과, 3 건너뜀: judgment·app.core·features 패키지 아직 없음 — 통과 아님)
- 결정 사항: D-001~D-015 (`docs/decisions.md`)
- 다음 행동: S02-1 격자 파일 대조 → S01 초안(YAML·계약, 원문 대조는 개발자 확인 대기) 또는 S02-2(가짜 어댑터)
- 막힌 조건: Codex 모델 설정(개발자). S01 원문 대조(개발자). `KMA_SERVICE_KEY`(S02-2 실호출). `공온지수`는 구현 금지(D-010)
