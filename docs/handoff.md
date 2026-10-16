# 현재 작업 인계

- 마지막 수정: Claude Code, 2026-10-16. C00~C04 완료·`main` 병합. 다음은 **C05 변경 건·버전**(collab-contract §4). 진행 중 브랜치 없음.
- 제품 방향(D-055·D-056): 대형 건설사 프로젝트의 작업 변경 → 업체별 후속 조치 → 완료 보고 → 검증. 실제 내부 자료는 선행조건이 아니다. 합성 자료는 `[가상]`, 시장성·현장 효과는 C08.
- 기준 문서: 계약 [collab-contract.md](collab-contract.md)(D-057), 조사 [research/C01-public-research.md](research/C01-public-research.md), 결정 D-057·D-058.
- C03: 로그인·서버 세션(0009), 같은 출처 검사(`app/core/security.py`), 현장 참여 업체·역할(0010). `sites.service.list_sites/get_site`는 `SiteScope` 필수(None=매시 자동 판정만). 비참여 404·역할 부족 403(HTML). 조정자 전용 버튼은 `ManagedSitesDep`로 숨김(권한은 서비스가 확인).
- C04-1: UTC 세션 비교, 작업 숨김 삭제(0011), 작업별 최신 판정 DB 선정, 위치·작업 시간·기준 버전이 바뀐 판정은 "재판정 필요"(단계 없음), D-053 추정 날 "보통"·설명 문구 정정.
- C04-2(0012): `work_items.performing_participant_id`(같은 현장 참여 업체만, 복합 FK)·`plan_version`, `work_item_revisions`(바뀌기 전 값). 화면의 계획 수정은 조정자만·공종 고정. `schedules.service.apply_plan_change`는 **커밋하지 않는** 낙관적 잠금 저장이다(오래된 버전 conflict, 값이 같으면 unchanged). C05 변경 확정은 이것을 같은 트랜잭션에서 부른다(`source`는 'edit' 말고 새 값).
- 검증: `scripts/check.py` 통과 444 passed·skip 없음, `PGTZ=UTC` 444 passed. 실제 서버로 로그인·참여자·편집·409 확인. 실제 기기(휴대폰) 화면 review는 미실시.
- C05 시작 시: change_cases·change_revisions 마이그레이션(0013), 상태 draft→review→confirmed/superseded/withdrawn, 확정은 조정자만·`based_on_plan_version` 확인·idempotency_key(폼 hidden UUID) 중복 방지, 계획 갱신·조치 생성·발송 대기 한 트랜잭션(조치·발송 테이블은 C06·C07에서 만들므로 C05는 계획 갱신과 버전 저장까지, 원자성 롤백 테스트 포함). 사유 코드는 총정리 §1.1의 11개 요인.
- **개발자 할 일**: 개발 DB 기존 현장 3곳은 소유자 미지정이라 안 보인다. 가입 후 `PYTHONUTF8=1 uv run python scripts/grant_site.py --email <내 이메일> --all-unassigned`. 스모크 확인용 가입자(smoke·prime·sub·edit…@example.com)와 그 현장이 남아 있으며 지워도 된다.
- 남은 위험: 로그인 시도 횟수 제한 없음, 가입 개방(D-014 시연 범위), 위임·첨부는 C06, 초대 메일 없음(D-015), 다중 프로세스 자동 판정 중복 제어 미검증.
- 원문 대기: 한중·도장·방수·아스팔트 KCS, 이동식 크레인·고소작업대 수치, 산안법 §64·사업관리 지침·KS F 4009 원문 대조. 알림톡(D-015), 기상청 트래픽 한도 미확인.
- 테스트 도구: `tests/conftest.py`의 `browser(user)`로 여러 회사 사용자, `client`=기본 사용자(가상건설 조정자). DB 제약은 세션에 직접 넣어 IntegrityError 확인. 회귀 테스트는 이전 코드로 실패하는지 확인했다.
- Windows: `uv run python -m pytest|alembic|uvicorn|mypy|ruff`, 한글 출력 `PYTHONUTF8=1`. 한글·따옴표가 많은 편집은 스크래치 파이썬 스크립트로(CRLF 유지).
- 미추적 `output/`·`reports/`·`research_notes/`·중기예보 ZIP은 보존(커밋 안 함).
