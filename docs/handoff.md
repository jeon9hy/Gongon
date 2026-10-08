# 현재 작업 인계

- 마지막 수정 도구 Claude Code(2026-10-08). 브랜치가 겹쳐 쌓여 있음(모두 main 반영 전):
  `feature/S01-2-crane-heat` → `feature/S05-montage-ui` → `feature/S01-law-live-check` → `feature/S03-pcp-window`(현재)
- S03 done(D-030): 공식 자료 3곳에 PCP·SNO 예보 시각 구간 정의 없음 → 누적값은 h·h+1 예보 둘 다 비교
  - 같으면 그 판정, 다르면 확인 필요(사유에 두 값). h 예보 없으면 판정 불가(다음 시각으로 안 메움)
  - 순간값(풍속·기온·습도·체감온도)은 기존대로 h만. 엔진 `engine/judgment/judge.py` ACCUMULATED
  - 테스트: 경계 입력을 '같은 값이 다음 시각까지' 형태로 바꾸고 D-030 테스트 4개 추가. 205 passed
  - 실제 기상청 예보로 현장 1 판정 성공(철골·폭염 진행) 확인
- S01 실검증(D-029): `uv run python -m scripts.verify_law_sources` — LAW_OC(.env)로 현행 MST·조문 텍스트 대조
  - 2026-10-08 결과 일치(MST 273603, 조문 6·별표 1). 종료 코드 0 일치 / 1 차이 / 2 확인 불가
- S05 review: Montage 토큰 화면(D-028). 개발자 브라우저 확인 대기
- API 상태: 기상청(공공데이터포털)·카카오 로컬·법령(LAW_OC) 모두 실제 호출 확인
- 다음: S01-4(묶음 B) 콘크리트·도장·방수·아스팔트 KCS 원문 확보 → 일평균·최저기온 계산
- 그다음 S01-5(묶음 C) 이동식 크레인·고소작업대(법령 수치 없음, 공식 가이드 확인)
- 남은 review: S00 main 반영, S04-1·3·4 쿼리 수 측정·마이그레이션 되돌리기 검증
- 폴더명 Gongon: VS Code 종료 후 상위 폴더에서 `ren gongon Gongon`
- Windows 한글 경로: uv run python -m pytest|alembic|uvicorn|mypy 사용
