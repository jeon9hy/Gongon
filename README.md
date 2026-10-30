![공온 — 변경 뒤 필요한 일을 연결하고, 처리 결과까지 확인합니다.](docs/assets/readme-hero.svg)

<div align="center">

**공사 계획의 변경부터, 업체별 조치와 완료 근거까지.**

`Python 3.12` · `FastAPI` · `PostgreSQL` · `규칙 기반 판정`

[시작하기](#시작하기) · [제품 요구사항](docs/product.md) · [구조](docs/architecture.md) · [현재 작업](docs/plan.md)

</div>

---

## 어떤 서비스인가요?

공온은 대형 건설사 프로젝트에서 **원청과 협력업체의 작업 변경 후속 조치를 연결하는 서비스**입니다. 작업 시간을 바꾸는 데서 그치지 않고, 누가 무엇을 언제까지 처리해야 하는지와 실제 처리 근거를 함께 남깁니다.

기상은 변경을 일으키는 여러 원인 중 하나입니다. 기존 기상 판정은 공종별 기준과 예보를 대조하는 근거 모듈로 유지합니다.

> **현재 단계** · 1인 개발 중인 비상업 시연 프로젝트입니다. 실제 현장 효과·실기기 검증은 별도로 진행하며, 문자 인증과 실제 알림 발송은 아직 연결하지 않았습니다.

## 변경 뒤, 이렇게 이어집니다

| ① 변경 제안 | ② 영향 검토·확정 | ③ 후속 조치 | ④ 완료 보고·검증 |
| --- | --- | --- | --- |
| 바뀐 작업과 원인·근거 기록 | 현재 계획과 비교하고 버전 확정 | 담당자·완료 기준·기한 연결 | 처리 근거 제출 후 검증 |

**메시지를 읽거나 계획을 수정한 것만으로 실제 조치가 끝났다고 처리하지 않습니다.**

## 화면과 주요 기능

![시연 자료로 확인한 공온 작업 일정 화면](docs/assets/readme-schedule.png)

*시연용 가상 현장 화면입니다.*

| 화면 | 할 수 있는 일 |
| --- | --- |
| **홈** | 내 차례(할 일·확인 대기·보류·결정 대기), 오늘 일정, 내일 판정, 이번 주 공온지수 |
| **일정** | 달력·작업 등록(공정표 파일 가져오기 포함)·공온 판정 7일 표·판정 내역 |
| **변경·조치** | 변경 건 제안·검토·확정, 맡은 조치 수락·보류·완료 보고·검증 |
| **서류** | 공사일보, 주간 작업계획표, 작업 차질 집계, 작업 지시서·실정보고 초안(PC) |
| **업체** | 참여 업체·담당자 명부·역할, 현장 코드로 참여 |
| **대화·게시 화면** | 현장 참여자 대화(사진·변경 건·조치 첨부), TV용 오늘·내일 작업 표시 |

공유·발송·실기기 확인을 포함한 상태는 [작업 목록](docs/plan.md)에서 확인할 수 있습니다.

## 기상 판정은 근거와 함께

| 진행 | 확인 필요 | 중지 검토 | 판정 불가 |
| --- | --- | --- | --- |
| 비교 가능한 예보가 기준에 해당하지 않음 | 조건·예보의 추가 확인 필요 | 예보가 중지 검토 기준에 해당 | 판정에 필요한 예보가 없음 |

- **같은 입력·같은 기준 버전이면 같은 결과.** 제품에 LLM 호출이나 머신러닝 판정은 없습니다.
- 예보 발표 시각·기준 버전·시간별 값을 저장해 판정 근거를 확인합니다. 같은 발표 시각·격자의 예보는 현장 간 재사용합니다.
- 예보로 직접 비교하지 못하는 순간풍속·노면 상태 등은 현장 확인 대상으로 남깁니다.
- **공온지수 v2**는 0~100의 규칙 기반 참고 점수입니다. 먼 날의 예보를 쓴 점수에는 ‘중기 참고’를 표시하며 확률·안전도·작업 허가를 뜻하지 않습니다.

<details>
<summary><strong>공종별 기준과 출처 보기</strong></summary>

| 공종 | 기준 파일 | 주요 출처 |
| --- | --- | --- |
| 철골 작업 | [steel.yaml](rules/steel.yaml) | 산업안전보건기준에 관한 규칙 제383조 |
| 콘크리트 타설 | [concrete.yaml](rules/concrete.yaml) | KCS 14 20 41·14 20 40, 국토교통부 강우 지침 |
| 이동식 크레인·고소작업대 | [mobile_crane.yaml](rules/mobile_crane.yaml) · [aerial_platform.yaml](rules/aerial_platform.yaml) | 안전보건규칙 제37조, 강풍주의보 기준, 제383조 준용(D-081) |
| 도장·방수 | [paint_waterproof.yaml](rules/paint_waterproof.yaml) | KCS 41 47 00·41 40 01 |
| 아스팔트 포장 | [asphalt_paving.yaml](rules/asphalt_paving.yaml) | KCS 44 50 10 |
| 폭염(공통) | [heat.yaml](rules/heat.yaml) | 안전보건규칙 제559~560조 |

원문 발췌는 [rules/sources](rules/sources)에 보존하고 [원문 대조 테스트](tests/engine/judgment/test_rule_sources.py)로 확인합니다. 법정 기준과 제품에서 준용한 기준을 구분합니다.

</details>

## 시작하기

**준비물:** Python 3.12, uv, PostgreSQL. 전체 설정과 Windows 실행 방법은 [실행 가이드](docs/setup.md)에 있습니다.

```bash
uv sync --locked
cp .env.example .env
```

개발용 `gongon`과 테스트용 `gongon_test` DB를 만들고 `.env`를 채웁니다. 키와 계정 값은 Git에 올리지 않습니다.

| 환경 변수 | 용도 |
| --- | --- |
| `DATABASE_URL` · `TEST_DATABASE_URL` | 개발·테스트 PostgreSQL 연결 |
| `KMA_SERVICE_KEY` · `KMA_APIHUB_KEY` | 기상청 예보 수집. API별 활용 신청 필요 |
| `KAKAO_REST_API_KEY` | 주소 → 좌표 변환(선택, 좌표 직접 입력 가능) |
| `AUTO_REFRESH=0` | 개발 중 자동 예보 판정 끄기 |

```bash
uv run python -m alembic upgrade head
uv run python -m uvicorn app.main:app --reload
```

[로컬 공온 열기](http://127.0.0.1:8000) · Windows에서는 `scripts/start.bat`으로 PostgreSQL 확인·마이그레이션·브라우저 열기를 함께 실행할 수 있습니다.

## 검증과 구조

```bash
uv run python scripts/check.py
```

CI와 같은 ruff·포맷·mypy·pytest 검사입니다. 외부 API는 가짜 어댑터로 바꾸며, 테스트에는 실제 네트워크나 외부 계정이 필요하지 않습니다. DB 테스트를 실행하려면 테스트 DB 설정이 필요합니다.

```text
app/features/   기능별 API · 처리 · DB 접근 · 화면
app/core/       공통 설정 · 인증 경계 · 템플릿 · 스타일
engine/         예보 정규화 · 위치 변환 · 규칙 기반 판정
rules/          공종별 기준표와 공식 원문 발췌
migrations/     DB 변경 이력
scripts/        실행 · 검증 · 시연 자료 · 원문 수집
tests/          기능 · 권한 · 경계 · 중복 실행 검증
docs/           요구사항 · 계약 · 결정 · 작업 인계
```

의존성은 `app → engine` 한 방향입니다. 순수 판정·위치 계산은 DB·HTTP·웹에 의존하지 않고, 기능 간 호출은 `service`·`schemas`를 거칩니다. [폴더 경계 테스트](tests/test_import_boundaries.py)가 이를 확인합니다.

| 개발 문서 | 내용 |
| --- | --- |
| [제품 요구사항](docs/product.md) · [계약](docs/collab-contract.md) | 무엇을 누구를 위해 만드는지, 권한·상태 전이 |
| [실행 가이드](docs/setup.md) · [구조](docs/architecture.md) | 환경 설정, 코드 위치와 의존 규칙 |
| [작업 목록](docs/plan.md) · [인계](docs/handoff.md) | 진행 상태와 재개 지점 |
| [결정 기록](docs/decisions.md) · [브랜드](docs/brand.md) | 확정한 선택, 화면 문구와 시각 기준 |

---

최종 판단은 현장 책임자가 합니다. 공온 판정은 규칙 기반 참고 정보이며 작업 허가·공식 검측·안전 보장을 대신하지 않습니다.
