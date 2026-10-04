# 현재 작업 인계

- 현재 작업 ID / 상태: S05-0 / review · 마지막 수정 도구: Claude Code
- 브랜치: `feature/S02-1-geo-grid` (S00 브랜치에서 분기, S02-1 커밋 위에 S05-0이 쌓여 있음. `main`은 아직 커밋 없음)
- 방향 변경(D-016): 화면을 예시 데이터로 먼저 만들고 기능은 나중에 연결. 계획서 순서(S01→S03→S04→S05)에서 화면만 앞당김
- 완료한 부분
  - S00: 환경·CI·지침·문서 (남은 것: Codex가 `AGENTS.md`를 읽는지 확인)
  - S02-1: `engine/geo` 격자 변환 (남은 것: 공식 격자 파일 추가 지점 대조, plan.md)
  - S05-0: 화면 4개 `/`·`/judgments`·`/judgments/1`·`/sites`. 공통 기반 `app/core/{templating.py,templates,static}`, 기능 화면 `app/features/{judgments,sites}`. 예시 데이터는 각 `sample.py`
  - S05-0 추가: 공종 7개(D-017). 현장 설정에서 여러 공종 선택, 대시보드 "공종별 판정" 카드, 알림 미리보기·내역에 여러 공종. 기준 미확인 공종은 `확인 필요`만
  - 실행: 폴더의 `공온 실행.lnk`(커밋 안 함) 또는 `scripts/start.bat` → 브라우저가 `/`를 연다
- 남은 부분
  - S05-0: 개발자가 화면을 보고 수정 요청 → 반영 → done
  - 이후 연결 순서: S01(기준·계약) → S03(엔진) → S02-2(예보) → S04(DB·API) → S05(예시 데이터를 실제 API로 교체)
- 메모: 한글 경로에서 `uv run pytest`·`uvicorn.exe`는 `uv trampoline failed`. `uv run python -m pytest`, `python -m uvicorn` 사용. 화면의 숫자·기준 버전은 시안 예시이며 `원문 대조 필요`
- 미커밋 변경: S05-0 전체(커밋 전 `git status`로 확인)
- 검증(2026-10-04, 로컬 Windows): `uv run python scripts/check.py` ruff·format·mypy·pytest 모두 ok (43 통과, 1 건너뜀: engine.judgment 패키지 아직 없음 — 통과 아님). 헤드리스 Edge 캡처로 4개 화면 모두 확인(대시보드는 휴대폰 폭도 확인)
- 결정 사항: D-001~D-017 (`docs/decisions.md`)
- 막힌 조건: 크레인·콘크리트 등 다른 공종을 첫 출시 판정에 넣을지(개발자). Codex 모델 설정(개발자). S01 원문 대조(개발자). `KMA_SERVICE_KEY`(S02-2 실호출). `공온지수`는 구현 금지(D-010)
