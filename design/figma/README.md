# 공온 Figma (웹 · 앱) — 만들고 고치는 법

공온 화면을 Figma에 두 파일로 둔다. 화면은 **이 폴더의 스크립트로 그린다**. Figma에서 손으로 고친 것은 스크립트를 다시 실행하면 사라지므로, 바꿀 것은 스크립트에 반영한다.

| 파일 | 주소 | 페이지(Starter라 3쪽까지) |
| --- | --- | --- |
| 공온 · 웹 | https://www.figma.com/design/3PtzyafvidwRmrTXBRzjHO | 서비스 사이트 · PC 앱 · 기초 |
| 공온 · 앱 | https://www.figma.com/design/bcOVE0bUZ3gKC9wjrBaItD | 기초 · 화면 |

계정: 김정현의 팀(Starter, View 좌석). Figma MCP 호출 한도가 빠듯하니 한 번 실행에 한 페이지를 통째로 그린다.

## 무엇이 어디에

- `_common.js` — 모든 스크립트 앞에 붙이는 공통 부분: 색 토큰(gongon.css `:root`와 같은 이름·값), 아이콘(`_macros.html`과 같은 SVG), 글꼴(Pretendard가 Figma에 없어 Gothic A1), 도우미(이름으로 페이지·섹션·컴포넌트 찾기, 같은 이름 화면 바꿔 그리기).
- `web/01_foundation.js` — 웹 "기초": 색 견본, 컴포넌트 Button · VerdictBadge · SegTab · WeatherTile · CompanyRow · SiteHeader · SiteRow · AppBar.
- `web/02_service_site.js` — "서비스 사이트": 01 첫 화면(로그인 전) · 02 내 현장 고르기.
- `web/03_pc_app.js` — "PC 앱": 03 홈 · 현장 하나.
- `app/01_foundation.js` — 앱 "기초": 색 견본, 컴포넌트 TabBar · ListRow · JobRow · TodoTile.
- `app/02_screens.js` — "화면": 01 오늘 · 02 내 조치 · 03 대화방 · 첨부.

각 화면 스크립트 첫 줄 주석에 대응하는 앱 템플릿이 적혀 있다(예: `judgments/app/home.html`).

## 실행하는 법 (Claude Code · Codex 공통)

1. Figma MCP의 `figma-use` 스킬을 먼저 읽는다(필수).
2. `create_session`(파일 키) → `use_figma`에 **`_common.js` 내용 + 스크립트 내용**을 이어 붙여 `code`로 보낸다. 한 번에 한 스크립트.
3. 순서: 처음이면 `01_foundation` → 화면 스크립트. 화면만 바뀌었으면 그 화면 스크립트만.
4. 결과의 `images`(예: `{"logo": [...], "mascot-3d-card": [...]}`)에 나온 노드에 그림을 채운다: `upload_assets`(nodeIds = 그 id들, scaleMode FIT) → 받은 주소마다 `app/core/static/brand/<이름>.png`을 POST.
   ```sh
   curl -F "file=@app/core/static/brand/mascot-3d-card.png;type=image/png" "<submitUrl>"
   ```
5. 다 그린 뒤 섹션 스크린샷 한 장으로 확인한다(겹침·잘림·빈 그림 자리).

## 다시 실행하면

- **화면**: 같은 이름의 화면을 지우고 **같은 자리**에 다시 그린다. 새 이름이면 섹션 오른쪽 끝에 붙는다. 그림은 매번 다시 채운다(4번).
- **색**: 컬렉션 "공온 색" 값이 `TOKENS`로 다시 맞춰진다.
- **컴포넌트**: 이미 있으면 **그대로 둔다**(없을 때만 만든다).

## 자주 하는 일

- **앱 화면이 바뀌었다** → 해당 화면 스크립트의 내용(글·배치)을 고치고 그 스크립트만 다시 실행.
- **새 화면을 넣는다** → 같은 페이지의 화면 스크립트에 `screen('04 …')` 블록을 더하거나, 같은 모양의 새 스크립트를 만든다. 페이지는 늘리지 말고(쪽 수 한도) 섹션 안에 이어 붙인다.
- **색을 바꿨다**(gongon.css) → `_common.js`의 `TOKENS`를 고치고 아무 스크립트나 한 번 실행하면 변수 값이 바뀌어 연결된 곳이 모두 바뀐다.
- **아이콘을 더 쓴다** → `_macros.html`의 경로를 `_common.js`의 `ICONS`에 그대로 옮긴다(지어내지 않는다).
- **컴포넌트 바꾸기** → 기초 페이지에서 그 컴포넌트를 지우고 기초 스크립트를 다시 실행한 뒤, 그 컴포넌트를 쓰는 화면 스크립트도 다시 실행한다(지운 컴포넌트의 인스턴스는 연결이 끊긴다).

## 알아 둘 것 (실제로 걸린 것)

- 실패한 `use_figma`는 통째로 되돌려진다 — 고쳐서 다시 실행하면 된다.
- 인스턴스 안에는 노드를 넣을 수 없다 → 아이콘·색이 다르면 변형(variant)으로 만든다(TodoTile·WeatherTile처럼).
- 텍스트 속성을 빈 글로 두면 인스턴스에서 그 글 레이어가 사라진다 → 빈 값 대신 내용을 넣는다.
- `layoutGrow`는 정수만 → 비율 나눔은 고정 폭으로.
- 텍스트 속성 연결(`componentPropertyReferences`)은 글 레이어가 컴포넌트 안에 들어간 뒤에 한다.
- 페이지 이동은 한 실행에 한 번(`usePage`). 다른 페이지 컴포넌트는 `component()`로 찾는다(그 페이지를 불러 온다).
- 예시 상태 칩·이름은 장식이며 실제 자료가 아니다(D-072). 판정 4단계 이름은 바꾸지 않는다.
