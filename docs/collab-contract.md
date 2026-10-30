# 작업 변경 후속 조치 계약 (C02, 2026-10-16)

C01 [공개 조사](research/C01-public-research.md)의 설계 가정 A1~A7과 합성 시나리오로 정한 **시연용 구현 계약**이다. 실제 고객의 전결·양식·기한을 확인한 계약이 아니다(D-056). 기상 판정 계약은 기존 [contract.md](contract.md)·[schema.json](schema.json)이 그대로 유지한다. 결정 이유는 D-057.

서버 렌더링 폼 구조이므로 외부 JSON API는 없다. 아래 필드·상태·권한이 C03~C07 구현과 테스트의 기준이다. 필드는 해당 작업의 마이그레이션에서 만든다(미리 만들지 않음).

## 1. 공통 규칙

- 시각: DB `timestamptz`, 화면 표시는 KST. 실제 처리 시각(`performed_at`)·기록 시각(`recorded_at`)·검증 시각(`verified_at`)은 다른 필드다.
- 기한: `due_at timestamptz NULL`. NULL이면 `due_note`(미정 사유) 필수. 공급사 변경 마감은 첫 범위에 두지 않는다(A4).
- 프로젝트 = 기존 `sites` 행(A6). 화면 이름은 "프로젝트"가 아니라 기존 "현장"을 유지한다.
- 권한 실패: 참여하지 않은 현장·다른 현장의 ID는 **404**(존재를 드러내지 않음), 참여했지만 역할이 부족하면 **403**. 비로그인 화면 요청은 `/login?next=`로 303.
- 쓰기 요청(POST)은 로그인 세션 + 같은 출처(Origin, 없으면 Referer) 확인을 통과해야 한다.

## 2. C03 인증·참여 (이번에 구현)

| 테이블 | 필드 | 규칙 |
| --- | --- | --- |
| organizations | id, name(60), created_at | 회사. 같은 이름 허용(실제 사업자 확인 없음) |
| users | id, email(200, 소문자 고유), display_name(40), password_hash, organization_id, is_active, created_at | 사용자는 한 회사 소속. 비활성이면 로그인·기존 세션 모두 거부 |
| auth_sessions | id, user_id, token_sha256(고유), created_at, expires_at | 쿠키에는 원 토큰, DB에는 해시만. 만료 12시간. 로그아웃 시 행 삭제 |
| project_participants | id, site_id, organization_id, kind(`prime`/`subcontractor`), created_at | (site, organization) 고유. 현장당 `prime` 1개 |
| project_memberships | id, site_id, participant_id, user_id, role(`coordinator`/`assignee`/`viewer`), granted_by_user_id, created_at, revoked_at, revoked_by_user_id | 활성(revoked_at NULL) 멤버십은 (site, user)당 1개. participant의 site와 같아야 함(복합 FK). 사용자 회사 = participant 회사 |

역할(화면 이름): `coordinator` 조정자, `assignee` 담당자, `viewer` 열람자. `coordinator`는 `prime` 참여 업체 소속만 가능(A2).

| 행동 | 조정자 | 담당자 | 열람자 | 비참여 |
| --- | --- | --- | --- | --- |
| 현장·일정·판정 보기 | O | O | O | 404 |
| 현장 수정·삭제, 작업 추가·삭제, 판정 실행 | O | 403 | 403 | 404 |
| 참여자 추가·회수 | O | 403 | 403 | 404 |
| 현장 새로 만들기 | 로그인 사용자 누구나. 만든 사람의 회사가 `prime`, 본인이 조정자 |

- 같은 회사 사용자라도 멤버십이 없으면 그 현장을 볼 수 없다(회사 공통 관리자 없음).
- 참여자 추가: 조정자가 **가입된 사용자의 휴대폰 번호 또는 이메일**과 역할을 입력(D-073, 번호는 숫자만 저장·문자 인증 전). 그 사용자의 회사가 아직 참여 업체가 아니면 `subcontractor`로 추가. 초대 메일·초대 링크는 없다(실제 발송 조건 D-015).
- 회수: `revoked_at` 기록, 행은 보존. 회수 즉시 다음 요청부터 접근 거부. 마지막 조정자는 회수할 수 없다.
- 기존 현장(0009 이전 행)은 참여 업체가 없어 아무도 볼 수 없다. 소유자를 추정하지 않고 개발자가 `scripts/grant_site.py`로 명시 지정한다.
- 자동 매시 판정(D-043)은 시스템 작업이라 멤버십과 무관하게 삭제되지 않은 모든 현장을 처리한다. 화면의 "전체 판정"은 내가 조정자인 현장만.
- 위임·첨부 접근은 조치·근거가 생기는 C06에서 같은 정책 서비스로 구현한다(지금은 대상이 없음).

## 2-1. C04-9 참여 업체·담당자 명부 (D-066, 구현 2026-10-16)

`project_participants`를 넓힌다(새 테이블을 만들지 않는다). 기존 행은 kind=`prime`/`subcontractor` 그대로 두고 아래 필드는 NULL 허용으로 더한다.

| 테이블 | 필드 | 규칙 |
| --- | --- | --- |
| project_participants(확장) | category(`subcontractor`/`supplier`/`equipment`/`supervision`, 원청은 NULL), trade_note(공종 메모 60), work_trades(맡은 업종 목록, `app/core/work_kinds.WORK_TRADE_NAMES`의 이름만, 목록 순서·중복 없음, 기본 빈 목록, D-088), business_no(선택 20, 검증 안 함), joined_on, ended_at, ended_by_user_id, created_by_user_id | 원청 조정자만 등록·수정·종료·재개. 종료한 업체는 작업 실행 업체·조치 담당 선택에서 빠지고 기존 연결은 유지. 원청은 종료 불가 |
| organizations | 명부로 만든 업체도 organizations 행을 만든다(사용자 0명 허용) | 같은 현장에 같은 이름 업체가 있으면 경고하고 조정자가 고른다(자동 병합 없음) |
| participant_contacts(새) | id, site_id, participant_id(복합 FK), name(40), job_title(40), phone(30, 선택), memo(200), user_id(NULL=계정 미연결), created_at, created_by_user_id, removed_at | 같은 현장 참여자만 조회. 열람자에게는 phone·memo 숨김. user_id 연결은 그 사용자의 회사 = 업체 회사일 때만, 현장당 사용자 1명 1연결 |

- 화면: 현장 → 참여 업체·참여자 화면을 "업체 카드(구분·공종·기간·상태) + 담당자 목록 + 업체 추가/종료/재개 + 담당자 추가/연결"로 바꾼다. 참여자(멤버십) 추가는 그대로 두되 "명부의 사람과 연결"을 고를 수 있게 한다.
- 작업 추가·수정의 실행 업체 선택은 참여 중인 업체만, 구분별로 묶어 보인다.
- 시연 자료(`scripts/seed_demo.py`)는 명부 구조로 바꾼다(회사 합치기 SQL 제거).
- 구현 세부(0015): 원청 구분 NULL·종료 불가는 CHECK. 같은 이름 비교는 앞뒤·연속 공백과 영문 대소문자만 무시. 참여자 추가 때 같은 이름 업체에 **붙이기**를 고르면 ① 명부로만 만든 업체(사용자 0명)는 참여 업체의 회사를 가입자 회사로 바꾸고, ② 사용자가 있는 업체(예: 원청 동료)는 가입자를 그 회사로 옮긴다 — 다른 현장 참여·동료·명부 연결이 없는 새 가입자만. 참여 종료 업체의 사람은 새로 추가하지 않는다(재개 먼저). 참여 종료는 멤버십을 회수하지 않는다. 작업 수정 때 이미 연결된 종료 업체는 그대로 둘 수 있다. 명부 삭제는 removed_at(행 보존, 계정 연결도 풀림).

## 3. C04 작업 기반 (구현 완료 2026-10-16)

- WorkItem에 `performing_participant_id`(실행 업체, NULL 허용 = 미지정), `plan_version`(1부터). 계획 시간·위치 변경은 `work_item_revisions`에 이전 값을 보존하고 버전을 올린다.
- 저장 시 제출한 `plan_version`이 현재와 다르면 409와 "다른 사람이 먼저 바꿨습니다" 안내(동시 수정).
- C04-1은 S08-4-1~4 결함 수정(plan의 C02~C07 분해 기준 참조).
- D-064의 오늘 시작 규칙은 작업 추가·수정과 변경 제안·확정에 같이 적용한다(C04-10). 같은 분까지 거부하고, 이미 시작한 오늘 작업의 날짜·시작 유지 예외는 같다. 확정 시점에 다시 검증하며 실패하면 계획·변경 상태를 저장하지 않는다.

## 4. C05 변경 건·버전 (구현 완료 2026-10-16, D-060)

변경 건 `change_cases`: site_id, work_item_id, title, created_by, created_at. 버전 `change_revisions`: case_id, number(1..), status, reasons(text[] — product.md §1 요인 코드), before/after 계획 값(work_date·start·end·location), note, based_on_plan_version, proposed_by/at, confirmed_by/at, withdrawn_by/at, withdraw_reason.

| 버전 상태 | 뜻 | 다음 |
| --- | --- | --- |
| `draft` 초안 | 제안 작성 중 | `review`, `withdrawn` |
| `review` 영향 검토 | 조치 후보 편집 | `confirmed`, `withdrawn` |
| `confirmed` 확정 | 불변. 계획 갱신·조치 생성·발송 대기를 한 트랜잭션으로 | 새 버전이 확정되면 `superseded` |
| `superseded` 대체됨 | 이후 버전이 현재 | — |
| `withdrawn` 철회 | 확정 전 철회, 이유 필수 | — |

- 확정: 조정자만. `based_on_plan_version` ≠ 현재 계획 버전이면 거부. 같은 `idempotency_key`(폼 hidden UUID) 재제출은 같은 결과를 돌려주고 중복 생성 없음.
- 변경 건 종료(`closed_at`)는 현재 `confirmed` 버전 기준 §5 종료 조건을 원자적으로 확인한다.

## 5. C06 후속 조치·검증

`action_items`(0017): case_id, revision_id, site_id, title(80), done_criteria(완료 기준 120자, 선택 — 무엇을 확인하면 끝나는지, D-070), performing_participant_id(참여 중 업체), assignee_user_id 또는 assignee_contact_id(계정 없는 명부의 사람, 둘 다 NULL = 업체 내 미지정, D-074), verifier_user_id, required(bool), due_at 또는 due_note(미정 사유 필수), status, 보고·검증·제외·막힘 기록 칸, replaced_by_id(C07).

- 후보: 초안·영향 검토 버전에 `candidate`로 붙인다(조정자 또는 그 버전 제안자). 확정과 같은 트랜잭션에서 `requested`. 확정 뒤에는 내용을 고치지 않고 제외만 한다.
- 확정 때 필수 조치가 0건이면 `change_revisions.no_action_reason` 필수. 재변경 확정 때 이전 확정 버전의 `requested·accepted·blocked`는 `replaced`(새 조치 연결·보완 후보는 C07).
- 잠금 순서: 변경 건 → 버전 → 조치. 종료한 건(`closed_at`)은 확정·재변경 제안·조치 처리를 받지 않는다.
- 내 조치(`/actions`): 내 응답 대기·막힘·검증 대기. 묶음마다 기한 지남 → 가까운 기한 → 기한 미정. 조정자에게는 계정 없는 명부 담당의 조치가 '대리 기록'으로 보인다.

| 조치 상태 | 뜻 | 허용 전이(행위자) |
| --- | --- | --- |
| `candidate` 조치 후보 | 확정 전 버전에 더함 | 확정 때 `requested`, 그 전엔 빼기(삭제) |
| `requested` 요청 대기 | 확정으로 생성 | `accepted`·`reported`·`blocked`(수행자). 수락은 선택(D-114) |
| `accepted` 수행 중 | 수행자가 수락 | `reported`·`blocked`(수행자) |
| `blocked` 막힘 | 사유 필수, 해결 담당은 선택(D-114, 0028) | `accepted`(수행자) |
| `reported` 완료 보고 | 처리 내용·performed_at·근거 | `verified`·`rejected→accepted`(검증자) |
| `verified` 검증 완료 | 검증자 확인 | — |
| `replaced` 대체됨 | 재변경으로 새 조치가 대신함 | — |
| `excluded` 제외 | 조정자가 이유와 함께 제외 | — |

- 모든 전이는 `action_events`(action_id, revision_id, kind, actor_user_id, on_behalf, performed_at, recorded_at, body)로 남긴다. 열람(`viewed`)·전화 확인 기록(`phone_record`, 상대·회사·연락 시각)도 사건이며 상태를 바꾸지 않는다.
- 수행자 = 지정 담당자(명부 담당이 나중에 계정과 연결되면 그 계정), 미지정이면 실행 업체 소속 조정자·담당자, 위임받은 사람. 조정자는 수행자 대신 전화로 확인해 기록할 수 있다(`on_behalf`, 연락 상대·시각 필수). 검증자 ≠ 담당자·완료 보고자(A3, 프로젝트 설정 전까지 예외 없음). 열람자는 처리할 수 없다(403), 비참여자는 404.
- 보고·검증 요청의 `revision_id`가 조치의 revision과 다르거나 조치가 `replaced`면 거부.
- 종료 조건: 현재 버전의 `required` 조치가 모두 `verified` 또는 `excluded`(이유 있음), `blocked` 없음. 필수 0건이면 확정 때 이유 필수.
- 자동 종료(D-114): 검증·제외 처리 뒤 현재 확정 버전의 확정 조치가 하나 이상이고 모두 `verified·excluded·replaced`이며 진행 중 재변경이 없으면 같은 트랜잭션에서 `closed_at`·`closed_by_user_id`(처리한 사람)를 채운다. 선택 조치가 남았으면 조정자가 종료 버튼으로 닫는다.
- 입력 기본값(D-114): 기한이 없으면 사유 없이도 ‘기한 미정’(`due_note` NULL 허용, 0028에서 CHECK 제거). 완료 보고 처리 시각·대리 기록 연락 시각은 날짜·시각을 둘 다 비우면 지금(하나만 적으면 거부). 후보 입력의 검증자는 조치를 거는 사람(조정자·담당자일 때)으로 미리 고른다.
- 첨부·위임: 근거는 텍스트(A5). 위임은 `action_delegations`(from, to, 기간)로 같은 업체 안에서만, 행위자 기록.

## 6. C07 발송 대기·재변경

- `dispatches`: 고유키 (site, revision, action, recipient, channel, kind, round). 상태 `pending → sent | failed | unknown`(공급자 응답 유실). 초기 채널은 `web`·`preview`뿐이며 미리보기를 "발송됨"으로 표시하지 않는다.
- 새 버전 확정 시: 이전 버전의 `requested`/`accepted`/`blocked` 조치 → `replaced` + 새 조치 연결, `reported`/`verified` 조치 → 새 버전에 `보완 필요` 조치 후보로 제시(조정자가 확정). 자동 원복 없음.

## 6-2. C12 현장 대화방 (D-071)

- `site_messages`(0018): site_id, author_user_id, body(1~1000자), linked_case_id(같은 현장 변경 건, 선택), created_at, deleted_at. 현장당 방 하나, 활성 멤버십만 읽기·쓰기(비참여 404). 지우기는 작성자만, 행은 남기고 '삭제된 메시지'로 보인다.
- 변경 건 카드는 저장한 글이 아니라 지금 상태(최신 버전·종료)를 읽어 보인다. 메시지·읽음은 조치 상태를 바꾸지 않는다. 새 메시지는 4초마다 `after_id` 뒤만 불러온다.
- 아직 없음: 메시지에서 조치·변경 제안 바로 만들기(지금은 작업 일정에서 제안), 읽음 표시, 푸시 알림.

## 6-1. C11 현장 게시 화면 (D-067)

- 역할 `board` 추가(project_memberships.role, 0019, 원청 참여 업체 아래). 화면 `/board/{site_id}` 한 장만 열 수 있고 다른 모든 화면·쓰기는 403/404(다른 화면은 조정자·담당자·열람자 범위로만 열림). 조정자·담당자·열람자도 게시 화면을 열 수 있다.
- 보이는 것: 오늘·내일 작업(시간·공종·위치·업체 이름), 그날 확정된 변경(바뀐 시간), 내일 날씨 한 줄, "작업 여부는 반장·소장 지시를 따릅니다". 보이지 않는 것: 연락처·메모·조치 내용·단가·다른 현장.
- 큰 글씨·가로 화면, 일정 간격으로 스스로 새로 고침. 공용 계정은 조정자가 만들고 회수한다.

## 6-3. C14 서류 (D-112)

- 모두 읽기 전용 인쇄 화면이며 조정자·담당자·열람자가 연다(비참여 404). 연락처·작업 메모는 넣지 않는다. 바닥에 ‘공온 기록 · 공식 서류 아님’과 출력 시각·출력한 사람.
- 주간 작업계획표 `/reports/{site}/weekly?start=YYYY-MM-DD`: 고른 날이 든 주(월~일), 기본은 다음 주. 확정 변경은 [그 주 월요일 − 7일, 그 주 월요일) KST, 조치는 지금 `requested·accepted·blocked·reported`.
- 작업일보 `work_reports`(0026): 작업(`work_item_id`, unique) 하나에 한 행. `outcome` ∈ done·partial·not_done, `causes`는 변경 원인 코드(REASON_LABELS)이고 done이 아니면 하나 이상(DB CHECK), done이면 비운다. `workers` 0~999 또는 NULL(모름, 0으로 채우지 않음), `equipment_note` ≤120자, `note` ≤500자, `work_date`·`plan_version`은 기록할 때의 작업 값, `recorded_by_user_id`·`recorded_at`은 마지막 기록. 고치면 덮어쓴다(이력 없음, 확인 항목).
- 기록 조건: 작업 날짜 ≤ 오늘(KST). 조정자는 모든 작업, 담당자는 자기 참여 업체가 실행 업체인 작업만(아니면 403), 열람자·게시 403. 기록 뒤 계획 버전이 바뀌면 ‘기록 뒤 계획 바뀜’으로 보이고 기록을 새 계획으로 옮기지 않는다. 결과가 done이 아니면 변경 제안 폼으로 가는 링크만 준다(자동 변경 없음).
- `known_when`(0027, D-113): day_before·morning·on_site 또는 NULL(모름), done이면 NULL(DB CHECK).
- 작업 차질 월 집계 `/reports/{site}/losses?month=`: 그달 `work_date`의 done이 아닌 기록을 원인별로(여러 원인이면 원인마다, 합계는 기록 하나를 한 번), 건수·적은 인원 합(없으면 ‘-’)·known_when 분포(모름 포함). 금액으로 바꾸지 않는다.
- 공사일보 `/reports/{site}/daily?day=`: 그날 작업을 업체별로, 합계 인원은 적은 값만 더한다(모두 없으면 ‘-’). 그날 확정된 변경을 붙인다.
- 기상 작업중지 기록 `/reports/{site}/weather?month=YYYY-MM`: 그달 `work_date`의 work_reports 중 done이 아니고 causes에 weather가 있는 것. ‘전체 중지’는 그날 작업 수 ≤ 기상 원인 못함 수. 판정은 그 작업·그 날짜의 판정 가운데 `judged_at ≤ work_start_at`인 마지막 하나(없으면 ‘판정 기록 없음’, 진행으로 채우지 않음). 판정은 참고이며 공기 연장 근거는 관측·계약 조건.
- 변경 건 문서 `/reports/{site}/changes/{case}?kind=order|report`: 변경 건 상세(changes 서비스, 열람 기록 포함)와 같은 값. 확정 버전이 있으면 그것, 없으면 최근 버전에 ‘아직 확정 전’ 표시. 주소의 현장과 변경 건의 현장이 다르면 404.

## 7. 합성 시나리오 대응 (C01 §5)

| 시나리오 단계 | 계약 |
| --- | --- |
| 가상건설이 현장 생성, 가상골조·가상펌프 담당자 추가 | C03 participants·memberships |
| 슬래브 타설 작업 등록, 실행 업체 가상골조 | C04 WorkItem |
| 10-20 09:00 → 10-21 10:00, 사유 자재 | C05 revision v1 confirmed |
| 4개 조치·검증자·기한 | C06 action_items |
| 펌프 예약 변경 완료 보고 → 검증 | C06 reported → verified |
| 10-22로 재변경 | C07 v2, 미수행 replaced, 기수행은 보완 후보 |
