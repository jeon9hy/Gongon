// 공온 · 웹 / 페이지 "기초": 색 견본 + 컴포넌트. _common.js 뒤에 붙여 실행한다.
// 없는 컴포넌트만 만든다(이미 있으면 그대로 둔다 — 고치려면 README '컴포넌트 바꾸기').
const page = await usePage('기초');

// 색 견본(매번 다시 그린다)
{
  const sec = section('색 · 공온 색', 0, 0);
  const at = replaceIn(sec, '색 견본');
  const sw = AL('VERTICAL', {name: '색 견본', itemSpacing: 12, paddingLeft: 24, paddingRight: 24, paddingTop: 24, paddingBottom: 24, cornerRadius: 16}); sw.fills = P('card'); sec.appendChild(sw); sw.x = at.x; sw.y = at.y;
  const groups = [['기본', ['accent', 'accent-strong', 'accent-soft', 'ink', 'text', 'muted', 'placeholder']], ['면·선', ['card', 'surface', 'backdrop', 'line', 'line-soft', 'dark', 'dark-2']], ['판정', ['go-bg', 'go-fg', 'go-mark', 'check-bg', 'check-fg', 'check-mark', 'stop-mark', 'stop-soft', 'stop-text', 'unknown-bg', 'unknown-fg']]];
  for (const [title, names] of groups) {
    sw.appendChild(T(title, 14, 'Bold', 'ink'));
    const row = AL('HORIZONTAL', {itemSpacing: 12}); sw.appendChild(row);
    for (const n of names) { const c = AL('VERTICAL', {itemSpacing: 6}); row.appendChild(c); const chip = figma.createRectangle(); chip.resize(88, 56); chip.cornerRadius = 10; chip.fills = P(n); chip.strokes = P('line-soft'); c.appendChild(chip); c.appendChild(T(n, 11, 'SemiBold', 'muted')); }
  }
  fitSection(sec); done.created.push(sw.id);
}

const sec = section('컴포넌트', 0, 520);
const exists = name => sec.children.find(n => n.name === name);
let cy = Math.max(80, ...sec.children.map(n => n.y + n.height + 60));
function place(n) { sec.appendChild(n); n.x = 60; n.y = cy; cy += n.height + 60; done.created.push(n.id); }
function asSet(comps, name, desc, dir = 'HORIZONTAL') { const s = figma.combineAsVariants(comps, page); s.name = name; s.layoutMode = dir; s.itemSpacing = 16; s.paddingTop = s.paddingBottom = s.paddingLeft = s.paddingRight = 16; s.fills = P('backdrop'); s.primaryAxisSizingMode = 'AUTO'; s.counterAxisSizingMode = 'AUTO'; s.description = desc; return s; }
function linkText(set, prop, def, layer) { const k = set.addComponentProperty(prop, 'TEXT', def); for (const v of set.children) { const t = v.findOne(n => n.name === layer); if (t) t.componentPropertyReferences = {characters: k}; } return k; }

// Button (Variant=주·보조·테두리) · Label
if (!exists('Button')) {
  const comps = [];
  for (const [v, fill, color, stroke] of [['주', 'accent', '#FFFFFF', null], ['보조', 'surface', 'ink', null], ['테두리', 'card', 'ink', 'line']]) {
    const c = figma.createComponent(); c.name = 'Variant=' + v; c.layoutMode = 'HORIZONTAL'; c.primaryAxisAlignItems = 'CENTER'; c.counterAxisAlignItems = 'CENTER'; c.paddingLeft = c.paddingRight = 18; c.paddingTop = c.paddingBottom = 11; c.cornerRadius = 12; c.primaryAxisSizingMode = 'AUTO'; c.counterAxisSizingMode = 'AUTO'; c.fills = P(fill); if (stroke) { c.strokes = P(stroke); c.strokeWeight = 1; }
    c.appendChild(T('버튼', 15, 'Bold', color, 'label')); comps.push(c);
  }
  const s = asSet(comps, 'Button', '버튼. 주(파랑)·보조(옅은 회색)·테두리.'); linkText(s, 'Label', '버튼', 'label'); place(s);
}
// VerdictBadge (Kind=진행·확인 필요·중지 검토·판정 불가) — 판정 4단계 이름은 바꾸지 않는다
if (!exists('VerdictBadge')) {
  const comps = [];
  for (const [k, bg, fg, mark] of [['진행', 'go-bg', 'go-fg', 'go-mark'], ['확인 필요', 'check-bg', 'check-fg', 'check-mark'], ['중지 검토', 'stop-soft', 'stop-text', 'stop-mark'], ['판정 불가', 'unknown-bg', 'unknown-fg', 'unknown-mark']]) {
    const c = figma.createComponent(); c.name = 'Kind=' + k; c.layoutMode = 'HORIZONTAL'; c.counterAxisAlignItems = 'CENTER'; c.itemSpacing = 6; c.paddingLeft = c.paddingRight = 10; c.paddingTop = c.paddingBottom = 4; c.cornerRadius = 999; c.primaryAxisSizingMode = 'AUTO'; c.counterAxisSizingMode = 'AUTO'; c.fills = P(bg);
    const d = figma.createEllipse(); d.resize(7, 7); d.fills = P(mark); c.appendChild(d); c.appendChild(T(k, 12.5, 'Bold', fg)); comps.push(c);
  }
  place(asSet(comps, 'VerdictBadge', '공온 판정 4단계 배지. 이름·색을 바꾸지 않는다(AGENTS.md).'));
}
// SegTab (Selected=true·false) · Label
if (!exists('SegTab')) {
  const comps = [];
  for (const on of [true, false]) { const c = figma.createComponent(); c.name = 'Selected=' + on; c.layoutMode = 'HORIZONTAL'; c.primaryAxisAlignItems = 'CENTER'; c.counterAxisAlignItems = 'CENTER'; c.paddingLeft = c.paddingRight = 14; c.paddingTop = c.paddingBottom = 8; c.cornerRadius = 999; c.primaryAxisSizingMode = 'AUTO'; c.counterAxisSizingMode = 'AUTO'; c.fills = on ? P('card') : []; if (on) { c.strokes = P('line-soft'); c.strokeWeight = 1; } c.appendChild(T('탭', 14, on ? 'Bold' : 'SemiBold', on ? 'ink' : 'muted', 'label')); comps.push(c); }
  const s = asSet(comps, 'SegTab', '회색 알약 안의 고르기(업체별·위치별 등).'); linkText(s, 'Label', '탭', 'label'); place(s);
}
// WeatherTile (Kind=바람·강수확률·습도·강수량) · Value
if (!exists('WeatherTile')) {
  const comps = [];
  for (const [k, ic] of [['바람', 'wind'], ['강수확률', 'rain'], ['습도', 'thermometer'], ['강수량', 'droplet']]) {
    const c = figma.createComponent(); c.name = 'Kind=' + k; c.layoutMode = 'HORIZONTAL'; c.counterAxisAlignItems = 'CENTER'; c.itemSpacing = 10; c.paddingLeft = c.paddingRight = 12; c.paddingTop = c.paddingBottom = 10; c.cornerRadius = 12; c.resize(170, 52); c.primaryAxisSizingMode = 'FIXED'; c.counterAxisSizingMode = 'AUTO'; c.fills = P('surface');
    const b = box(28, 8, P('card')); c.appendChild(b); b.appendChild(icon(ic, 16, '#1C60EF'));
    const col = AL('VERTICAL', {itemSpacing: 0}); c.appendChild(col); col.appendChild(T(k, 12, 'Regular', 'muted')); col.appendChild(T('–', 15, 'Bold', 'ink', 'value')); comps.push(c);
  }
  const s = asSet(comps, 'WeatherTile', '지금 날씨 네 칸. 값이 없으면 – (누락을 정상값으로 채우지 않는다).'); linkText(s, 'Value', '–', 'value'); place(s);
}
// CompanyRow · Name · Meta · Count · State
if (!exists('CompanyRow')) {
  const c = figma.createComponent(); c.name = 'CompanyRow'; c.layoutMode = 'HORIZONTAL'; c.counterAxisAlignItems = 'CENTER'; c.itemSpacing = 12; c.paddingLeft = c.paddingRight = 16; c.paddingTop = c.paddingBottom = 12; c.resize(560, 64); c.primaryAxisSizingMode = 'FIXED'; c.counterAxisSizingMode = 'AUTO'; c.cornerRadius = 14; c.fills = P('card'); c.strokes = P('line-soft'); c.strokeWeight = 1;
  const K = {name: c.addComponentProperty('Name', 'TEXT', '업체'), meta: c.addComponentProperty('Meta', 'TEXT', '업종 · 시간'), count: c.addComponentProperty('Count', 'TEXT', '1건'), state: c.addComponentProperty('State', 'TEXT', '진행 중')};
  const b = box(40, 12, P('accent-soft')); c.appendChild(b); b.appendChild(icon('building', 18, '#1C60EF'));
  const m = AL('VERTICAL', {itemSpacing: 2}); put(c, m, 'FILL'); const n1 = wrapText(m, T('업체', 16, 'Bold', 'ink'), true); n1.componentPropertyReferences = {characters: K.name}; const n2 = wrapText(m, T('업종', 13, 'Regular', 'muted'), true); n2.componentPropertyReferences = {characters: K.meta};
  const cnt = AL('HORIZONTAL', {paddingLeft: 10, paddingRight: 10, paddingTop: 4, paddingBottom: 4, cornerRadius: 999}); cnt.fills = P('surface'); c.appendChild(cnt); const ct = T('1건', 12.5, 'Bold', 'ink'); cnt.appendChild(ct); ct.componentPropertyReferences = {characters: K.count};
  const st = AL('HORIZONTAL', {paddingLeft: 10, paddingRight: 10, paddingTop: 4, paddingBottom: 4, cornerRadius: 999, name: 'state'}); st.fills = P('accent'); c.appendChild(st); const stt = T('진행 중', 12.5, 'Bold', '#FFFFFF', 'stateText'); st.appendChild(stt); stt.componentPropertyReferences = {characters: K.state};
  c.appendChild(icon('chevron-down', 16, '#5B6576'));
  c.description = '홈·일정의 업체별 묶음 한 줄. 누르면 그 업체 작업이 펼쳐진다.'; place(c);
}
// SiteHeader (State=로그인 전·로그인 후) — 서비스 사이트 머리줄: 기능 ▾ · 협업 · 소개 · 요금
if (!exists('SiteHeader')) {
  const btn = await (async () => sec.children.find(n => n.name === 'Button'))();
  const button = (v, label) => { const i = variantOf(btn, 'Variant=' + v).createInstance(); i.setProperties({[propKey(btn, 'Label')]: label}); return i; };
  const comps = [];
  for (const state of ['로그인 전', '로그인 후']) {
    const c = figma.createComponent(); c.name = 'State=' + state; c.layoutMode = 'HORIZONTAL'; c.counterAxisAlignItems = 'CENTER'; c.itemSpacing = 16; c.paddingLeft = c.paddingRight = 120; c.resize(1440, 72); c.primaryAxisSizingMode = 'FIXED'; c.counterAxisSizingMode = 'FIXED'; c.fills = P('#FFFFFF', 0.92); strokeOnly(c, 'bottom');
    const logo = AL('HORIZONTAL', {name: 'logo', itemSpacing: 8, counterAxisAlignItems: 'CENTER'}); c.appendChild(logo); logo.appendChild(img('logo', 32, 32)); logo.appendChild(T('공온', 20, 'ExtraBold', 'ink'));
    spacer(c);
    const nav = AL('HORIZONTAL', {name: 'nav', itemSpacing: 4, counterAxisAlignItems: 'CENTER'}); c.appendChild(nav);
    for (const [lab, dd] of [['기능', true], ['협업', false], ['소개', false], ['요금', false]]) { const it = AL('HORIZONTAL', {itemSpacing: 4, counterAxisAlignItems: 'CENTER', paddingLeft: 14, paddingRight: 14, paddingTop: 10, paddingBottom: 10, cornerRadius: 999, name: 'nav/' + lab}); nav.appendChild(it); it.appendChild(T(lab, 15, 'SemiBold', 'muted')); if (dd) it.appendChild(icon('chevron-down', 14, '#5B6576')); }
    spacer(c);
    const right = AL('HORIZONTAL', {name: 'actions', itemSpacing: 8, counterAxisAlignItems: 'CENTER'}); c.appendChild(right);
    if (state === '로그인 전') { right.appendChild(button('보조', '로그인')); right.appendChild(button('주', '시작하기')); }
    else { right.appendChild(button('주', '내 현장')); const av = box(36, 999, P('accent')); right.appendChild(av); av.appendChild(T('박', 14, 'Bold', '#FFFFFF', 'initial')); right.appendChild(icon('chevron-down', 14, '#5B6576')); }
    comps.push(c);
  }
  place(asSet(comps, 'SiteHeader', '서비스 사이트 머리줄(D-110). 메뉴는 각자 페이지: 기능 ▾ · 협업 · 소개 · 요금. 로그인 뒤엔 내 현장 + 이름 메뉴(로그아웃).', 'VERTICAL'));
}
// SiteRow · Mark · Name · Sub — 내 현장 고르기 한 줄
if (!exists('SiteRow')) {
  const c = figma.createComponent(); c.name = 'SiteRow'; c.layoutMode = 'HORIZONTAL'; c.counterAxisAlignItems = 'CENTER'; c.itemSpacing = 12; c.paddingTop = c.paddingBottom = 12; c.paddingLeft = c.paddingRight = 16; c.resize(720, 66); c.primaryAxisSizingMode = 'FIXED'; c.counterAxisSizingMode = 'AUTO'; c.cornerRadius = 16; c.fills = P('card'); c.strokes = P('line-soft'); c.strokeWeight = 1;
  const K = {mark: c.addComponentProperty('Mark', 'TEXT', '남'), name: c.addComponentProperty('Name', 'TEXT', '현장 이름'), sub: c.addComponentProperty('Sub', 'TEXT', '주소')};
  const mk = box(40, 12, P('accent-soft')); mk.name = 'mark'; c.appendChild(mk); const mt = T('남', 17, 'Bold', 'accent', 'markText'); mk.appendChild(mt); mt.componentPropertyReferences = {characters: K.mark};
  const m = AL('VERTICAL', {itemSpacing: 2}); put(c, m, 'FILL'); const a = wrapText(m, T('현장 이름', 16, 'SemiBold', 'ink'), true); a.componentPropertyReferences = {characters: K.name}; const b2 = wrapText(m, T('주소', 13, 'Regular', 'muted'), true); b2.componentPropertyReferences = {characters: K.sub};
  const o = AL('HORIZONTAL', {itemSpacing: 4, counterAxisAlignItems: 'CENTER'}); c.appendChild(o); o.appendChild(T('열기', 14, 'SemiBold', 'accent')); o.appendChild(icon('arrow-right', 16, '#1C60EF'));
  c.description = '내 현장 고르기 한 줄(D-110). 누르면 PC 앱이 새 탭(gongon-app)으로 그 현장을 연다. Mark는 빈 글로 두지 말 것(레이어가 사라짐).'; place(c);
}
// AppBar (Active=홈·일정·변경·조치·업체·대화) — PC 웹 앱 머리(소개 링크·바닥글 없음)
if (!exists('AppBar')) {
  const comps = [];
  for (const active of ['홈', '일정', '변경·조치', '업체', '대화']) {
    const c = figma.createComponent(); c.name = 'Active=' + active; c.layoutMode = 'HORIZONTAL'; c.counterAxisAlignItems = 'CENTER'; c.itemSpacing = 16; c.paddingLeft = c.paddingRight = 120; c.resize(1440, 64); c.primaryAxisSizingMode = 'FIXED'; c.counterAxisSizingMode = 'FIXED'; c.fills = P('card'); strokeOnly(c, 'bottom');
    const brand = AL('HORIZONTAL', {itemSpacing: 8, counterAxisAlignItems: 'CENTER', name: 'brand'}); c.appendChild(brand); brand.appendChild(img('logo', 32, 32)); brand.appendChild(T('공온', 20, 'ExtraBold', 'ink'));
    const chip = AL('HORIZONTAL', {name: 'siteChip', itemSpacing: 6, counterAxisAlignItems: 'CENTER', paddingLeft: 12, paddingRight: 10, paddingTop: 7, paddingBottom: 7, cornerRadius: 999}); chip.fills = P('card'); chip.strokes = P('line'); chip.strokeWeight = 1; brand.appendChild(chip); const d = figma.createEllipse(); d.resize(8, 8); d.fills = P('go-mark'); chip.appendChild(d); chip.appendChild(T('전체 현장', 13, 'SemiBold', 'ink', 'site')); chip.appendChild(icon('chevron-down', 14, '#0E1E45'));
    spacer(c);
    const nav = AL('HORIZONTAL', {name: 'nav', itemSpacing: 4, counterAxisAlignItems: 'CENTER'}); c.appendChild(nav);
    for (const lab of ['홈', '일정', '변경·조치', '업체', '대화']) { const on = lab === active; const it = AL('HORIZONTAL', {paddingLeft: 14, paddingRight: 14, paddingTop: 9, paddingBottom: 9, cornerRadius: 10, name: 'nav/' + lab}); it.fills = on ? P('accent') : []; nav.appendChild(it); it.appendChild(T(lab, 15, on ? 'Bold' : 'Medium', on ? '#FFFFFF' : 'muted')); }
    spacer(c);
    const me = AL('HORIZONTAL', {name: 'me', itemSpacing: 8, counterAxisAlignItems: 'CENTER'}); c.appendChild(me); const av = box(36, 999, P('accent')); me.appendChild(av); av.appendChild(T('박', 14, 'Bold', '#FFFFFF', 'initial')); me.appendChild(T('박서연 과장', 15, 'SemiBold', 'ink', 'name')); me.appendChild(icon('chevron-down', 14, '#5B6576'));
    comps.push(c);
  }
  const s = asSet(comps, 'AppBar', 'PC 웹 앱 머리(D-109·D-110): 로고 · 현장 칩 · 주 메뉴 5개 · 이름 메뉴(내 정보·가이드·로그아웃). 서비스 사이트 링크와 바닥글은 없다.', 'VERTICAL');
  linkText(s, 'Site', '전체 현장', 'site'); linkText(s, 'Name', '박서연 과장', 'name'); linkText(s, 'Initial', '박', 'initial'); place(s);
}
fitSection(sec);
return done;
