# 현재 작업 인계

- 마지막 수정 도구 Claude Code(2026-10-07), 브랜치 `feature/S04-basic-app` 유지
- 완료: S01 done — 제383조 원문 자동 대조(D-026). 계약 S01-1(D-025)은 이전 커밋
- 방법: 국가법령정보센터 Open API `lawService.do` MST 273603(고용노동부령 제450호, 2025-09-01 시행)
- 발췌: `rules/sources/osh_standards_rule_mst273603.json` (제37·383·558·559·560조, 응답 SHA256)
- 재수집: `uv run python -m scripts.fetch_law_articles --oc test --mst <MST> --articles 37 383 --out ...`
- 현행 MST 확인: `lawSearch.do?OC=test&target=law&type=XML&query=<법령명>`
- `rules/steel.yaml`: quote·source_snapshot·source_article·verified_on, `source_verified: true`, rule_version "2025-09-01 시행"
- 로더: 검증 완료 표시인데 발췌·조문·대조일·인용이 없으면 거부
- `tests/engine/judgment/test_rule_sources.py`: 인용이 원문 부분 문자열인지, 값·단위·이상/초과가 인용과 같은지
- 변이 검사: 연산자·값·인용·조항 혼동 4종 모두 실패로 검출 확인(수동 실행, 원복함)
- 화면: 상세에 "원문 확인" 표시, 현장 설정의 고정 "원문 대조 필요" 문구 제거
- 검증: `scripts/check.py` ruff·format·mypy 통과, pytest 168 passed·skip 없음
- 기존 판정 내역은 당시 rule_version·미확인 상태 그대로(추가만). contract-examples는 합성 예시라 유지
- 다음 후보(plan.md): S01-2 타워크레인 → S01-3 폭염 → S01-4 콘크리트, 그 다음 S03 PCP 시각 정의 대조
- S01-2 쟁점: 법령은 순간풍속 초과, 단기예보 WSD는 평균풍속. 평균 > 기준이면 순간도 > 기준(하한 논리)
  - 평균 ≤ 기준이면 순간풍속 미상 → `확인 필요`. 돌풍 계수 등 근거 없는 추정은 쓰지 않음
- S01-3 쟁점: 별표 13의2 체감온도 측정법을 발췌해 기상청 체감온도 산식(TMP·REH)과 대조 필요
- S01-4: KCS 14 20 12·14(국가건설기준센터) 원문 확보. 일평균기온을 시간별 TMP로 계산 가능한지 확인
- 폴더명 Gongon 변경: VS Code 등이 폴더를 사용 중이라 Windows가 거부(2회). VS Code 종료 후 상위 폴더에서
  `ren gongon Gongon` 실행 필요. GitHub 저장소 이름은 이미 Gongon
- 기존 대기: S05 홈의 최신성/판정 없음 구분 개선, S04-2는 기본 흐름 정리 후(D-024)
- Windows 한글 경로: uv run python -m pytest|alembic|uvicorn 사용
