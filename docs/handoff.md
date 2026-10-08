# 현재 작업 인계

- 마지막 수정 도구 Claude Code(2026-10-08), 브랜치 `feature/S05-montage-ui`(`feature/S01-2-crane-heat` 끝에서 분기)
- 이번 작업: S05 화면 수정 요청 — 전체 화면을 원티드 Montage 디자인 토큰으로 교체(D-028)
  - `app/core/static/gongon.css`: `:root` 토큰을 Montage 값으로(파랑 primary, Pretendard, 16/10px 둥글기, 그림자), 라임·검정 선택 상태 → 연파랑 바탕 + 파랑 글자
  - `base.html`: Google Fonts(Plus Jakarta·IBM Plex) → Pretendard CDN
  - `detail.html`·`dashboard.html`: 인라인 색 2곳을 토큰으로
  - 문서: `docs/brand.md` §5 토큰 표, `docs/decisions.md` D-028, `docs/plan.md` S05
- Montage MCP(`montage-mcp-server`)는 OAuth 토큰이 저장되지 않아 미사용. 값은 DocuMaster의 `@wanteddev/wds` 3.12.2 `theme.css`(MIT)에서 옮김
- 검증: 헤드리스 Edge로 홈·대시보드·내역·상세·현장 설정(1366px)과 대시보드·현장 설정(390px, iframe) 확인. `scripts/check.py` 통과(pytest 193 passed, skip 없음)
  - 헤드리스 Edge `--window-size=390`은 최소 폭 때문에 잘려 보인다 → 390px iframe 감싸기로 확인
- 남은 확인: 개발자가 실제 브라우저에서 보고 고칠 점 전달 → S05 done
- 이전 작업(S01-2·3 타워크레인·폭염, D-027)은 `feature/S01-2-crane-heat`에 커밋 완료, main 반영 전
- 다음 판정 작업: 묶음 B(S01-4) 콘크리트·도장·방수·아스팔트 KCS 원문 → 일평균·최저기온 계산
- 그다음 묶음 C(S01-5) 이동식 크레인·고소작업대(법령 수치 없음, 공식 가이드 확인)
- 남은 확인: S03 PCP 시각 정의(D-018) 활용가이드 대조
- 폴더명 Gongon: VS Code 종료 후 상위 폴더에서 `ren gongon Gongon`
- Windows 한글 경로: uv run python -m pytest|alembic|uvicorn|mypy 사용
