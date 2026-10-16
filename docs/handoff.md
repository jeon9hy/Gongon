# 현재 작업 인계

- 마지막 수정: Claude Code, 2026-10-16. C00~C03 완료, `main`에 병합 예정(브랜치 `feature/C03-auth`). 다음은 **C04-1**(기존 결함 S08-4-1~4 이식)부터.
- 제품 방향(D-055·D-056): 대형 건설사 프로젝트의 작업 변경 → 업체별 후속 조치 → 완료 보고 → 검증. 실제 내부 자료·인터뷰는 구현 선행조건이 아니다. 합성 자료는 `[가상]`으로 표시하고 시장성·현장 효과는 C08 별도 검증.
- C01: [docs/research/C01-public-research.md](research/C01-public-research.md). 출처 10건 중 공식 원문 직접 확인은 Procore Action Plans뿐, 나머지는 2차(원문 대조 필요). Touchplan은 403으로 재확인 못 함. 설계 가정 A1~A7, 미확인 8건, 합성 시나리오(타설 연기·조치 4건·재변경).
- C02: [docs/collab-contract.md](collab-contract.md) + D-057. 역할 조정자/담당자/열람자, 조정자는 원청만, 자기 검증 금지, C04~C07 테이블·상태 전이·종료 조건·발송 대기 키. 시연 계약이며 고객 확인 아님.
- C03-1(0009): 가입(회사+사용자 생성)·로그인·로그아웃, scrypt, 서버 세션(토큰 SHA-256만 저장, 12시간), 쿠키 HttpOnly·SameSite=Lax(`SESSION_COOKIE_SECURE`), `app/core/security.py` 쓰기 요청 같은 출처 검사. 모든 기능 라우터에 `require_user`.
- C03-2(0010): `project_participants`(현장당 회사 1행·원청 1개)·`project_memberships`(복합 FK로 같은 현장 강제, 활성 1개, 회수 행 보존). `sites.service.list_sites/get_site`는 `SiteScope`가 필수 인자(None=매시 자동 판정만). 비참여 404·역할 부족 403(HTML 안내). 참여자 화면 `/sites/{id}/members`. 화면 전체 판정은 내가 조정자인 현장만.
- 검증: `scripts/check.py` 통과, 415 passed·skip 없음(인증 29·접근 23 추가). 실제 서버(uvicorn)로 로그인 이동·외부 출처 403·가입·참여자 추가·담당자 열람 200/쓰기 403 확인.
- **개발자 할 일**: 개발 DB의 기존 현장 3곳은 소유자를 추정하지 않아 지금 아무도 볼 수 없다. 화면에서 가입 후 `PYTHONUTF8=1 uv run python scripts/grant_site.py --email <내 이메일> --all-unassigned`.
- 개발 DB에 스모크 확인용 가입자(smoke·prime·sub…@example.com)와 그들 소유 현장 1곳(스모크현장····)이 남아 있다. 그 계정으로만 보이며 지워도 된다.
- 남은 위험·후속: 로그인 시도 횟수 제한 없음. 가입은 누구나 가능(D-014 비상업 시연 범위). 일정·대시보드의 실행·추가 버튼은 역할과 무관하게 보이고 누르면 403 안내(C04에서 숨김). 위임·첨부 접근은 C06. 초대 메일 없음(D-015).
- C04-1: S08-4-1 PGTZ=UTC 일정 검사 2 failed(테스트 135·155행 `.hour`), S08-4-2 같은 공종·시간 작업 삭제 시 고유 키 충돌 500, S08-4-3 대시보드 `latest_for_*` LIMIT 후 묶음, S08-4-4 입력 변경 후 재판정 필요 표시 없음. 재현 기록은 plan S08-4.
- C04-2: WorkItem에 실행 업체(`performing_participant_id`)·`plan_version`·`work_item_revisions`, 409 동시 수정. 기존 작업 행의 실행 업체는 NULL(미지정)로 두고 추정하지 않는다.
- 원문 대기·외부 조건은 그대로: 한중·도장·방수·아스팔트 KCS, 이동식 크레인·고소작업대 수치, 알림톡(D-015), 기상청 트래픽 한도.
- 테스트 도구: `tests/conftest.py`의 `browser(user)`로 여러 회사 사용자를 만든다. `client`=기본 사용자(가상건설 조정자). DB 제약 검사는 세션에 직접 넣어 IntegrityError 확인.
- Windows 한글 경로: `uv run python -m pytest|alembic|uvicorn|mypy|ruff`. 스크립트 한글 출력은 `PYTHONUTF8=1`. bash heredoc에 한글·따옴표가 많으면 실패하니 스크래치 파일로 실행.
- 미추적 `output/`·`reports/`·`research_notes/`·중기예보 ZIP은 과거 자료로 보존(커밋 안 함). 기획 PDF는 `output/pdf`에만 있다.
