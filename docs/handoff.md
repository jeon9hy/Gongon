# 현재 작업 인계

## 지금
- 마지막 수정: Claude Code, 2026-10-30. 브랜치 `refactor/R01-cleanup`(R01 전체 정리, review). 개발자 확인 뒤 main에 빨리 감기로 합치고 브랜치를 지운다.
- R01에서 바뀐 것: 쓰지 않는 CSS·그림 삭제, `app/core/formats.py`로 중복 도우미 통합, `migrations/env.py` 모든 모델 등록, `count_queries` 픽스처·`tests/app/test_query_counts.py`, 문서 현행화(D-120). 제품 동작·화면·DB는 바꾸지 않았다.
- R01 남은 확인: 화면이 그대로인지 1440·390 폭으로 한 번 보기(지운 CSS는 모든 템플릿·JS에서 쓰이지 않음을 확인함).

## 다음
- C13 남은 앱 화면: 1b 조치 상세·응답, 1c 변경 상세·제안·확정, 1d 일정 주간 목록, 1f 내 정보·로그인(서로 독립). 앱 화면이 없는 페이지는 웹 화면이 앱 틀 안에 그대로 보이므로 하나씩 바꿔도 된다.
- 그다음 C13-2b PC 홈 현황판(시안 2) → 공유·키 결정(`launch-checklist.md`) → C13-3 배포.
- C14(서류)는 review: 실제 휴대폰 일보 입력, ‘내일 작업 준비 확인’ 가설(D-113)은 팀장 인터뷰 뒤.

## 개발 환경 (계속 유효)
- 개발 서버: 개발자 바로가기 8000번, Claude 확인용 8001번. 파이썬을 바꾸면 서버를 다시 켠다.
- 개발 DB: 마이그레이션 0028까지 적용. 개발자 계정 `sim5213@naver.com`(산군)에 현장 7곳(남산공원·롯데마트 + [TEST 0000~0004]) 시험 자료, 다시 채우기는 `scripts/seed_test_sites.py`·`seed_chat.py`(setup.md).
- 산군 계정은 이천 물류센터·해운대 오피스텔·대전 초등학교(51·52·53)에서는 협력업체 담당자(원청 = [TEST] 대한종합건설, 조정자 `test-prime@demo.gongon.test`). 나머지는 원청 조정자.
- 시험 계정(비밀번호 모두 `gongon-demo-1234`): 공무 `test-works@demo.gongon.test`, 협력업체 `test-<frame|steel|water|crane|scaffold|elec|pump>@demo.gongon.test`, 예전 시연 `pm@demo.gongon.test`.
- 화면 확인: PC에서 `?ui=app`(390폭 iframe으로 캡처, 헤드리스 Chrome 최소 창이 390보다 넓다). 점검·캡처 스크립트는 저장소 밖 scratchpad에 Playwright로 만든다(`uv run --no-project --with playwright python -I <스크립트>`).
- QA는 개발자가 Codex로 따로 한다(`docs/qa/`).

## 참고 자료
- Figma: **공온 · 웹** `3PtzyafvidwRmrTXBRzjHO`, **공온 · 앱** `bcOVE0bUZ3gKC9wjrBaItD`. 화면은 `design/figma/` 스크립트로 다시 그린다(README). 지금은 대표 화면(웹 3·앱 3)만.
- 시안: 바탕화면 `공온_시안1_웹앱_역할분리.png`·`공온_시안2_웹_현황판.png`·`공온_시안3_모바일앱.png`, 홈 시안 `홈_시안.html`.
- 사업 구상서(비공개 발표자료): https://claude.ai/artifact/Qcy4MRcd2yHEeN4DLnodWt
- 홈에 아직 없는 것(후보): ‘N시간째 응답 없음’, 업체별 응답 속도, 완료 보고 사진 썸네일, 협력업체 전용 홈 배치.

## 주의
- 커밋은 `scripts/check.py`의 종료 코드로 막는다. `alembic check`는 쓰지 않는다(D-120).
- 홈 섹션 테스트는 `</section>`으로 자르므로 섹션 안에 `<section>`을 넣지 않는다.
