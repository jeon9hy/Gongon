# 현재 작업 인계

- 마지막 수정 도구 Claude Code(2026-10-08). 브랜치가 겹쳐 쌓여 있음(모두 main 반영 전):
  `feature/S01-2-crane-heat` → `feature/S05-montage-ui` → `feature/S01-law-live-check` → `feature/S03-pcp-window` → `docs/S08-schedule-pivot` → `fix/S01-2-remove-tower-crane` → `feature/S05-readable-cards` → `rules/S01-4-concrete` → `feature/S05-app-shell` → `feature/S05-minimal-ui` → `fix/S05-font-color-align` → `feature/S08-1-work-items`(현재)
- S03 done(D-030): 공식 자료 3곳에 PCP·SNO 예보 시각 구간 정의 없음 → 누적값은 h·h+1 예보 둘 다 비교
  - 같으면 그 판정, 다르면 확인 필요(사유에 두 값). h 예보 없으면 판정 불가(다음 시각으로 안 메움)
  - 순간값(풍속·기온·습도·체감온도)은 기존대로 h만. 엔진 `engine/judgment/judge.py` ACCUMULATED
  - 테스트: 경계 입력을 '같은 값이 다음 시각까지' 형태로 바꾸고 D-030 테스트 4개 추가. 205 passed
  - 실제 기상청 예보로 현장 1 판정 성공(철골·폭염 진행) 확인
- S01 실검증(D-029): `uv run python -m scripts.verify_law_sources` — LAW_OC(.env)로 현행 MST·조문 텍스트 대조
  - 2026-10-08 결과 일치(MST 273603, 조문 6·별표 1). 종료 코드 0 일치 / 1 차이 / 2 확인 불가
- S05 review: Montage 토큰 화면(D-028). 개발자 브라우저 확인 대기
- API 상태: 기상청(공공데이터포털)·카카오 로컬·법령(LAW_OC) 모두 실제 호출 확인
- 계획 변경(D-031, 브랜치 `docs/S08-schedule-pivot`): 제언서 반영. 총정리·plan 수정, 코드 충돌 없음
- S01-4 review(D-033, 브랜치 `rules/S01-4-concrete`): 콘크리트 강우(가이드라인 2024.12)·서중(KCS 14 20 41:2025) 공식 원문 반영,
  일평균기온(KCS 8회 정의)·종료 후 24h 최고 계산(`engine/forecast/daily.py`), 엔진 이하·미만, 계약 v1.2. 실제 예보로 산군 판정 확인
  - 남음: 한중 KCS 14 20 40·도장 41 47 00·방수 41 40 01·아스팔트 44 50 10 원문(kcsc.re.kr 브라우저 전용 → 개발자가 PDF 전달)
- 타워크레인 제외(D-032, 마이그레이션 0003 개발 DB 적용함). S05 칩·최근 판정 묶기(`feature/S05-readable-cards`)
- S05 화면: 앱 바·상태 띠(D-034·035, Pretendard 직접 제공). 개발자 브라우저 확인 대기
- S08-1 review(D-036, `feature/S08-1-work-items`): `/schedule` 작업 입력, 작업별 판정, 마이그레이션 0004(개발 DB 적용·되돌리기·check 확인), 실제 예보로 작업 판정 확인
- 다음: S08-2 CSV·엑셀 업로드(라이브러리 결정 필요) → S08-3 주간 보기 → S09-1·2
- S01-5(이동식 크레인·고소작업대)는 공식 수치 확인 후 끼워 넣음
- 남은 review: S00 main 반영, S04-1·3·4 쿼리 수 측정·마이그레이션 되돌리기 검증
- 폴더명 Gongon: VS Code 종료 후 상위 폴더에서 `ren gongon Gongon`
- Windows 한글 경로: uv run python -m pytest|alembic|uvicorn|mypy 사용
