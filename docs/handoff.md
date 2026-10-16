# 현재 작업 인계

- 마지막 수정: Claude Code, 2026-10-16. C00~C05·C04-4~6·바닥 영역(푸터) 개편 완료·`main` 병합. 다음은 **C06 후속 조치·검증**(collab-contract §5). C06은 `feature/C06-actions`에 WIP(0015 마이그레이션·actions 모델·서비스 초안, changes 연결·화면·테스트 전).
- 제품 방향(D-055·D-056): 대형 건설사 프로젝트의 작업 변경 → 업체별 후속 조치 → 완료 보고 → 검증. 실제 내부 자료는 선행조건이 아니다. 합성 자료는 `[가상]`, 시장성·현장 효과는 C08.
- 기준 문서: 계약 [collab-contract.md](collab-contract.md), 조사 [research/C01-public-research.md](research/C01-public-research.md), 결정 D-057~D-060.
- C03: 로그인·세션(0009), 같은 출처 검사, 참여 업체·역할(0010). `sites.service.list_sites/get_site`는 `SiteScope` 필수(None=매시 자동 판정만). 비참여 404·역할 부족 403(HTML). 버튼 표시는 `ManagedSitesDep`(조정자)·`ProposableSitesDep`(조정자·담당자), 권한은 서비스가 확인.
- C04: UTC 비교·작업 숨김 삭제(0011)·작업별 최신 판정 DB 선정·"재판정 필요"(C04-1), 실행 업체·계획 버전·변경 이력·낙관적 잠금(0012, C04-2), 현장 주요 공종·기본 시간 제거·작업 있는 날만 판정·폭염을 작업 카드에 합침·작업 추가 편의(0013, C04-3, D-059).
- C04-6(D-063): 주 메뉴 4개(홈·작업 일정·변경·현장), 작업 일정 하위 메뉴(달력·공온 판정·판정 내역, base.html의 subnav), 화면 머리 문구는 brand.md ‘공온 말투’.
- C04-5(D-062): 홈 = 오늘 작업(현장별, 계획 시간 기준 예정·진행 중·끝남) → 내일 준비(판정). 전체 톤 변경은 개발자가 보고 되돌림(푸터만 유지).
- C04-4(D-061, 개발자 요청): 오늘 작업 등록·수정 허용(지난 날짜만 거부), 일정 화면 기본 선택 오늘, 오늘 작업은 판정하지 않음(판정은 내일부터 7일 그대로). 모든 date/time 입력은 `app/core/static/picker.js` 고르기 판(일→월→연, 시+5분)으로 바뀜(값 형식·서버 검증 동일, 숨긴 입력의 value를 바꾸면 버튼 글자도 바뀜).
- C05(0014, D-060): `app/features/changes`. 제안(조정자·담당자)→영향 검토→확정(조정자)·철회(이유). 확정 = `schedules.service.apply_plan_change_by_id`(source='change') + 이전 확정 버전 superseded + 이 버전 confirmed, 한 트랜잭션. confirm_key로 재전송 구분, 제안 뒤 계획 버전이 바뀌면 확정 거부. 메뉴 "변경", 작업 카드 "변경 제안".
- **C06 시작 지점**: `changes.service._after_confirm(session, revision)`에서 확정 버전의 후속 조치를 같은 트랜잭션으로 만든다. 계약 §5의 action_items·action_events, 상태 requested→accepted/blocked→reported→verified(반려는 accepted), 검증자≠보고자, 대상 버전이 현재가 아니면 거부, 종료 조건(현재 버전 필수 조치 모두 verified/excluded·막힘 없음, 0건이면 이유). 조치 후보 입력은 영향 검토 단계(review)에서 받는다. 위임·텍스트 근거도 C06.
- 검증: `scripts/check.py` 통과 483 passed·skip 없음, `PGTZ=UTC` 483 passed. 실제 브라우저(로컬 Chromium + 스크래치 playwright-core)로 작업 추가 모달·현장 설정·대시보드·변경 제안→확정 확인(가로 넘침·스크립트 오류 없음). 휴대폰 실기기는 미실시.
- **개발자 할 일**: 개발 DB 기존 현장 3곳은 소유자 미지정이라 안 보인다. 가입 후 `PYTHONUTF8=1 uv run python scripts/grant_site.py --email <내 이메일> --all-unassigned`. 그 현장들의 예전 "주요 공종"은 더 쓰지 않으므로 작업 일정에서 작업을 등록해야 판정된다. 확인용 가입자(smoke·prime·sub·edit·pw·pg·ch…@example.com)와 그 현장(대부분 삭제 처리)이 남아 있으며 지워도 된다.
- 남은 위험: 로그인 시도 횟수 제한 없음, 가입 개방(D-014 시연 범위), 초대 메일 없음(D-015), 다중 프로세스 자동 판정 중복 제어 미검증, 변경 목록 50건 상한.
- 원문 대기: 한중·도장·방수·아스팔트 KCS, 이동식 크레인·고소작업대 수치, 산안법 §64·사업관리 지침·KS F 4009 원문 대조. 알림톡(D-015), 기상청 트래픽 한도 미확인.
- 테스트 도구: `tests/conftest.py`의 `browser(user)`(여러 회사 사용자), `client`=기본 사용자(가상건설 조정자), `tests/helpers.add_site_with_work`(현장+내일 작업). 다른 요청이 저장한 값을 테스트 세션에서 읽을 때는 `session.expire_all()`.
- Windows: `uv run python -m pytest|alembic|uvicorn|mypy|ruff`, 한글 출력 `PYTHONUTF8=1`. 한글·따옴표가 많은 편집은 스크래치 파이썬 스크립트로(CRLF 유지), bash heredoc은 깨질 수 있다.
- 2026-10-16 개발자 요청으로 미추적 옛 자료(`output/` PDF·`reports/`·`research_notes/`·`tmp/`, 바탕 화면의 같은 PDF 2개)와 도구 캐시를 지웠다. 현재 기준은 총정리·`docs/proposals/` 기획서 v2.1·`docs/research/C01-public-research.md`.
