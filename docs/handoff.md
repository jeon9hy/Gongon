# 현재 작업 인계

- 마지막 수정: Claude Code, 2026-10-16. C00~C05·C04-4~8 완료·`main` 병합. 진행 중 브랜치는 `feature/C06-actions`(WIP) 하나.
- **다음 작업: C04-9 참여 업체·담당자 명부**(D-066, 계약 §2-1, plan의 C04-9 분해). `main`에서 `feature/C04-9-participant-roster` 브랜치로 시작한다. 마이그레이션 번호는 0015.
- 그다음 **C06 이어받기**: plan의 'C06 이어받기' 절을 그대로 따른다(main 합치기 → 마이그레이션 0016으로 번호 변경 → changes 연결·라우터·화면·테스트). 그 뒤 C07, C11 현장 게시 화면(D-067).
- 제품 방향(D-055·D-056): 작업 변경 → 업체별 후속 조치 → 완료 보고 → 검증. 날씨는 공온 점검 5항목 중 하나(D-065). 주 사용자는 원청 공사·공무 담당자(D-066). 작업자는 별도 서비스가 아니라 게시 화면(D-067, 공개 링크 금지 유지).
- 요구사항: [product.md](product.md) + 결정 + 계약(D-068, 총정리·기획서는 삭제). 기준 문서: 계약 [collab-contract.md](collab-contract.md), 조사 [research/C01-public-research.md](research/C01-public-research.md), 결정 D-057~D-067, 화면 문구 [brand.md](brand.md)('공온 말투': 화면엔 설명문 없이 짧고 재치 있게, 설명은 /guide).
- 화면 구조: 주 메뉴 홈·작업 일정·변경·현장(가운데 정렬), 작업 일정 하위 메뉴 달력·공온 판정·판정 내역. 이름 메뉴에 내 정보(/me)·공온 가이드(/guide)·로그아웃(app/features/help).
- 홈(D-065): 오늘(시간표·먼저 챙길 것)/내일(브리핑 3줄)/이번 주 공온지수, 공온 점검은 judgments.service `_check_boards`·`CHECK_LABELS`, 새로 점검은 날짜 옆 버튼·휴대폰 당기기(run-all).
- 작업 일정(D-064): 공종 색(`app/core/templating.WORK_TYPE_COLORS`) 점 달력·점 누르면 작업 상세 모달, 날짜 이동은 fetch로 달력·상세만 교체, 오늘 작업은 지금 이후 시작만(수정 시 시작 그대로면 예외), 일요일 시작. 날짜·시간 입력은 `app/core/static/picker.js`(시간은 30분 목록+직접 입력, `data-after`·`data-min`).
- 권한: `sites.service.list_sites/get_site`는 `SiteScope` 필수. 비참여 404·역할 부족 403. 버튼 표시는 `ManagedSitesDep`·`ProposableSitesDep`, 권한은 서비스가 확인.
- 시연 자료: `PYTHONUTF8=1 uv run python scripts/seed_demo.py`(개발 DB 현장 38에 이미 있음, `pm@demo.gongon.test` / `gongon-demo-1234`). 지금은 가입 후 회사 이름이 같은 행을 SQL로 합친다 → C04-9에서 명부 구조로 바꾼다.
- 검증: `scripts/check.py` 495 passed·skip 없음. 실제 브라우저(로컬 Chrome + 스크래치 playwright-core)로 9개 화면 데스크톱·휴대폰 폭(가로 넘침·스크립트 오류 없음). 휴대폰 실기기·당겨서 새로 점검의 실제 터치는 미확인.
- 개발자 할 일: 개발 DB 기존 현장 3곳은 소유자 미지정 → 가입 후 `scripts/grant_site.py --email <내 이메일> --all-unassigned`. 확인용 가입자(…@example.com)와 그 현장은 지워도 된다.
- 남은 위험: 로그인 시도 횟수 제한 없음, 가입 개방(D-014), 초대 메일 없음(D-015), 다중 프로세스 자동 판정 중복 제어 미검증, 변경 목록 50건 상한, 명부 연락처 보관·동의(D-066, 운영 전 확인).
- 원문 대기: 한중·도장·방수·아스팔트 KCS, 이동식 크레인·고소작업대 수치, 산안법 §64·사업관리 지침·KS F 4009. 알림톡(D-015), 기상청 트래픽 한도.
- 테스트 도구: `tests/conftest.py`의 `browser(user)`·`client`(가상건설 조정자, 지금=2026-10-04 15:00), `tests/helpers.add_site_with_work`. 지난 시각의 오늘 작업은 DB에 직접 넣는다. 다른 요청이 저장한 값은 `session.expire_all()` 뒤 읽는다.
- Windows: `uv run python -m pytest|alembic|uvicorn|mypy|ruff`, 한글 출력 `PYTHONUTF8=1`. 한글·따옴표가 많은 편집은 파일로 쓴 파이썬 스크립트로(bash heredoc은 자주 깨짐). `rm`에 변수 경로를 쓰면 `${VAR:?}`로.
