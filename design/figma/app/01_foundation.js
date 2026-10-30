// 공온 · 앱 / 페이지 "기초": 색 견본 + 휴대폰 컴포넌트. _common.js 뒤에 붙여 실행한다.
// 없는 컴포넌트만 만든다(이미 있으면 그대로 둔다 — 고치려면 README '컴포넌트 바꾸기'). 휴대폰 화면 폭 390.
const page = await usePage('기초');
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

// TabBar (Active=오늘·일정·조치·업체·대화)
if (!exists('TabBar')) {
  const TABS = [['오늘', 'home'], ['일정', 'calendar'], ['조치', 'clipboard'], ['업체', 'building'], ['대화', 'chat']];
  const comps = [];
  for (const [active] of TABS) {
    const c = figma.createComponent(); c.name = 'Active=' + active; c.layoutMode = 'HORIZONTAL'; c.resize(390, 64); c.primaryAxisSizingMode = 'FIXED'; c.counterAxisSizingMode = 'FIXED'; c.fills = P('card'); strokeOnly(c, 'top');
    for (const [label, ic] of TABS) {
      const on = label === active;
      const it = AL('VERTICAL', {name: 'tab/' + label, itemSpacing: 3, primaryAxisAlignItems: 'CENTER', counterAxisAlignItems: 'CENTER'}); put(c, it, 'FILL', 'FILL');
      const pill = box(28, 999, on ? P('accent-soft') : []); it.appendChild(pill); pill.resize(44, 28); pill.appendChild(icon(ic, 22, on ? '#1C60EF' : '#8A93A3'));
      it.appendChild(T(label, 11, 'SemiBold', on ? 'accent' : 'placeholder'));
    }
    comps.push(c);
  }
  place(asSet(comps, 'TabBar', '휴대폰 아래 탭(오늘·일정·조치·업체·대화). 고른 탭은 파란 알약. 대화방 안에서는 숨긴다.', 'VERTICAL'));
}
function rowBase(name) { const c = figma.createComponent(); c.name = name; c.layoutMode = 'HORIZONTAL'; c.counterAxisAlignItems = 'CENTER'; c.itemSpacing = 12; c.paddingTop = c.paddingBottom = 9; c.paddingLeft = 14; c.paddingRight = 12; c.resize(358, 60); c.primaryAxisSizingMode = 'FIXED'; c.counterAxisSizingMode = 'AUTO'; c.minHeight = 56; c.fills = P('card'); strokeOnly(c, 'bottom'); return c; }
// ListRow · Title · Meta · Status — 한 줄 목록(줄 전체를 누른다, 큰 버튼 없음)
if (!exists('ListRow')) {
  const c = rowBase('ListRow');
  const K = {title: c.addComponentProperty('Title', 'TEXT', '제목'), meta: c.addComponentProperty('Meta', 'TEXT', '설명'), status: c.addComponentProperty('Status', 'TEXT', '상태')};
  const m = AL('VERTICAL', {name: 'main', itemSpacing: 2}); put(c, m, 'FILL');
  const t = wrapText(m, T('제목', 15, 'Bold', 'ink', 'title'), true); t.componentPropertyReferences = {characters: K.title};
  const s = wrapText(m, T('설명', 12.5, 'Regular', 'muted', 'meta'), true); s.componentPropertyReferences = {characters: K.meta};
  const end = AL('HORIZONTAL', {name: 'end', itemSpacing: 6, counterAxisAlignItems: 'CENTER'}); c.appendChild(end);
  const tag = AL('HORIZONTAL', {name: 'tag', paddingLeft: 7, paddingRight: 7, paddingTop: 4, paddingBottom: 4, cornerRadius: 7}); tag.fills = P('surface'); end.appendChild(tag);
  const tt = T('상태', 11.5, 'Bold', 'ink', 'tagText'); tag.appendChild(tt); tt.componentPropertyReferences = {characters: K.status};
  end.appendChild(icon('chevron-right', 16, '#8A93A3'));
  c.description = '휴대폰 한 줄 목록: 제목 · 설명(한 줄, 넘치면 말줄임) · 상태 · 화살표. 줄 전체를 누른다.'; place(c);
}
// JobRow · Start · End · Title · Meta · Phase — 오늘 작업 한 줄
if (!exists('JobRow')) {
  const c = rowBase('JobRow');
  const K = {start: c.addComponentProperty('Start', 'TEXT', '08:00'), end: c.addComponentProperty('End', 'TEXT', '17:00'), title: c.addComponentProperty('Title', 'TEXT', '철골 작업'), meta: c.addComponentProperty('Meta', 'TEXT', '102동 2층 보 · 우진철강'), phase: c.addComponentProperty('Phase', 'TEXT', '진행 중')};
  const time = AL('VERTICAL', {name: 'time', itemSpacing: 0}); c.appendChild(time); time.resize(40, 10); time.primaryAxisSizingMode = 'AUTO'; time.counterAxisSizingMode = 'FIXED';
  const ts = T('08:00', 12.5, 'Bold', 'ink', 'start'); time.appendChild(ts); ts.componentPropertyReferences = {characters: K.start};
  const te = T('17:00', 11, 'Regular', 'muted', 'end'); time.appendChild(te); te.componentPropertyReferences = {characters: K.end};
  const m = AL('VERTICAL', {name: 'main', itemSpacing: 2}); put(c, m, 'FILL');
  const tr = AL('HORIZONTAL', {name: 'titleRow', itemSpacing: 6, counterAxisAlignItems: 'CENTER'}); put(m, tr, 'FILL');
  const dot = figma.createEllipse(); dot.name = 'tradeDot'; dot.resize(8, 8); dot.fills = P('#EA580C'); tr.appendChild(dot);
  const tt = wrapText(tr, T('철골 작업', 15, 'Bold', 'ink', 'title'), true); tt.componentPropertyReferences = {characters: K.title};
  const ms = wrapText(m, T('설명', 12.5, 'Regular', 'muted', 'meta'), true); ms.componentPropertyReferences = {characters: K.meta};
  const ph = AL('HORIZONTAL', {name: 'phase', paddingLeft: 8, paddingRight: 8, paddingTop: 3, paddingBottom: 3, cornerRadius: 999}); ph.fills = P('accent'); c.appendChild(ph);
  const pt = T('진행 중', 11.5, 'Bold', '#FFFFFF', 'phaseText'); ph.appendChild(pt); pt.componentPropertyReferences = {characters: K.phase};
  c.description = '휴대폰 오늘 작업 한 줄: 시작·끝 시각 · 업종 점(업종 색) · 작업 · 위치·업체 · 진행 알약.'; place(c);
}
// TodoTile (Kind=변경 결정·할 일·확인 대기·보류) · Title · Count · Top — 먼저 챙길 것 2×2
if (!exists('TodoTile')) {
  const comps = [];
  for (const [kind, ic, col, bg] of [['변경 결정', 'clipboard', '#7C3AED', '#F1E9FF'], ['할 일', 'arrow-right', '#1C60EF', '#EAF1FE'], ['확인 대기', 'check', '#2E9E5B', '#E3F5EA'], ['보류', 'info', '#D9483B', '#FDECE9']]) {
    const t = figma.createComponent(); t.name = 'Kind=' + kind; t.layoutMode = 'VERTICAL'; t.itemSpacing = 6; t.paddingTop = t.paddingBottom = t.paddingLeft = t.paddingRight = 12; t.resize(175, 100); t.primaryAxisSizingMode = 'AUTO'; t.counterAxisSizingMode = 'FIXED'; t.cornerRadius = 16; t.fills = P('card'); t.strokes = P('line-soft'); t.strokeWeight = 1;
    const th = AL('HORIZONTAL', {name: 'head', itemSpacing: 6, counterAxisAlignItems: 'CENTER'}); put(t, th, 'FILL');
    const ib = box(24, 8, P(bg)); ib.name = 'iconBox'; th.appendChild(ib); ib.appendChild(icon(ic, 16, col));
    th.appendChild(T(kind, 13, 'Bold', 'ink', 'title'));
    const cnt = AL('HORIZONTAL', {name: 'count', itemSpacing: 2, counterAxisAlignItems: 'BASELINE'}); t.appendChild(cnt);
    const cn = T('0', 26, 'ExtraBold', col, 'countText'); cn.lineHeight = {unit: 'PERCENT', value: 110}; cnt.appendChild(cn); cnt.appendChild(T('건', 13, 'Bold', 'muted'));
    wrapText(t, T('맨 앞 한 건', 12, 'Regular', 'muted', 'top'), true);
    comps.push(t);
  }
  const s = asSet(comps, 'TodoTile', '오늘 · 먼저 챙길 것 2×2의 한 칸. 순서는 변경 결정 → 할 일 → 확인 대기 → 보류, 칸마다 다른 색. 0건은 숫자를 회색(placeholder)으로. 위 합계는 네 칸의 합.');
  for (const [prop, def, layer] of [['Title', '변경 결정', 'title'], ['Count', '0', 'countText'], ['Top', '맨 앞 한 건', 'top']]) { const k = s.addComponentProperty(prop, 'TEXT', def); for (const v of s.children) v.findOne(n => n.name === layer).componentPropertyReferences = {characters: k}; }
  place(s);
}
fitSection(sec);
return done;
