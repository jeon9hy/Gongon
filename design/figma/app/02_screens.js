// 공온 · 앱 / 페이지 "화면": 01 오늘 · 02 내 조치 · 03 대화방 · 첨부. _common.js 뒤에 붙여 실행.
// 앱 화면: judgments/app/home.html · actions/app/my.html · chat/app/room.html (D-109·D-111). 다시 실행하면 같은 이름의 화면을 지우고 그 자리에 다시 그린다.
const tabSet = await component('TabBar'); const listRow = await component('ListRow'); const jobRow = await component('JobRow'); const tileSet = await component('TodoTile');
await usePage('화면');
const sec = section('휴대폰 · 화면', 0, 0);
function screen(name) { const at = replaceIn(sec, name, 80); const f = figma.createFrame(); f.name = name; f.resize(390, 844); f.fills = P('backdrop'); f.clipsContent = true; sec.appendChild(f); f.x = at.x; f.y = at.y; done.created.push(f.id); return f; }
function header(scr, title, chip) {
  const h = AL('HORIZONTAL', {name: 'header', itemSpacing: 10, counterAxisAlignItems: 'CENTER', paddingLeft: 16, paddingRight: 16}); h.fills = P('card'); strokeOnly(h, 'bottom');
  scr.appendChild(h); h.resize(390, 56); h.primaryAxisSizingMode = 'FIXED'; h.counterAxisSizingMode = 'FIXED'; h.x = 0; h.y = 0;
  h.appendChild(T(title, 20, 'ExtraBold', 'ink', 'title')); spacer(h);
  const ch = AL('HORIZONTAL', {name: 'siteChip', itemSpacing: 6, counterAxisAlignItems: 'CENTER', paddingLeft: 12, paddingRight: 10, paddingTop: 7, paddingBottom: 7, cornerRadius: 999}); ch.fills = P('card'); ch.strokes = P('line'); ch.strokeWeight = 1; h.appendChild(ch);
  const d = figma.createEllipse(); d.resize(8, 8); d.fills = P('go-mark'); ch.appendChild(d); ch.appendChild(T(chip, 13, 'SemiBold', 'ink')); ch.appendChild(icon('chevron-down', 14, '#0E1E45'));
  const av = box(36, 999, P('ink')); h.appendChild(av); av.appendChild(T('박', 14, 'Bold', '#FFFFFF'));
}
function body(scr, y) { const b = AL('VERTICAL', {name: 'body', itemSpacing: 12, paddingLeft: 16, paddingRight: 16, paddingTop: 16, paddingBottom: 90}); scr.appendChild(b); b.resize(390, 10); b.primaryAxisSizingMode = 'AUTO'; b.counterAxisSizingMode = 'FIXED'; b.x = 0; b.y = y; return b; }
function tabbar(scr, active) { const i = variantOf(tabSet, 'Active=' + active).createInstance(); scr.appendChild(i); i.x = 0; i.y = 844 - 64; }
function secHead(parent, title, small, link) { const r = AL('HORIZONTAL', {name: 'secHead', counterAxisAlignItems: 'CENTER', itemSpacing: 6}); put(parent, r, 'FILL'); r.appendChild(T(title, 15, 'ExtraBold', 'ink')); if (small) r.appendChild(T(small, 12.5, 'SemiBold', 'muted')); spacer(r); if (link) r.appendChild(T(link, 13, 'SemiBold', 'accent')); return r; }
function list(parent) { const l = AL('VERTICAL', {name: 'list', itemSpacing: 0, cornerRadius: 14, clipsContent: true}); l.fills = P('card'); l.strokes = P('line-soft'); l.strokeWeight = 1; put(parent, l, 'FILL'); return l; }
const LR = {title: propKey(listRow, 'Title'), meta: propKey(listRow, 'Meta'), status: propKey(listRow, 'Status')};
const JR = {start: propKey(jobRow, 'Start'), end: propKey(jobRow, 'End'), title: propKey(jobRow, 'Title'), meta: propKey(jobRow, 'Meta'), phase: propKey(jobRow, 'Phase')};
const TT = {title: propKey(tileSet, 'Title'), count: propKey(tileSet, 'Count'), top: propKey(tileSet, 'Top')};

// 01 오늘
{
  const s = screen('01 오늘 · 현장 하나'); header(s, '오늘', '롯데마트 현장'); const b = body(s, 56);
  const sum = AL('VERTICAL', {name: 'summaryCard', itemSpacing: 8, paddingLeft: 14, paddingRight: 14, paddingTop: 14, paddingBottom: 12, cornerRadius: 18}); put(b, sum, 'FILL'); sum.fills = grad('#24318C', '#1B2468', NAVY); sum.effects = shadow(0.2, 10, 24);
  const top = AL('HORIZONTAL', {name: 'top', itemSpacing: 8, counterAxisAlignItems: 'CENTER'}); put(sum, top, 'FILL'); top.appendChild(T('10월 29일(목)', 12.5, 'Medium', '#C9D2FF'));
  const wx = AL('HORIZONTAL', {name: 'weather', itemSpacing: 4, counterAxisAlignItems: 'CENTER', paddingLeft: 9, paddingRight: 9, paddingTop: 4, paddingBottom: 4, cornerRadius: 999}); wx.fills = P('#FFFFFF', 0.12); top.appendChild(wx); wx.appendChild(icon('cloud-sun', 14, '#FFFFFF')); wx.appendChild(T('13° 비', 12.5, 'SemiBold', '#FFFFFF'));
  const mid = AL('HORIZONTAL', {name: 'greetingRow', itemSpacing: 8, counterAxisAlignItems: 'CENTER'}); put(sum, mid, 'FILL');
  const g = T('좋은 점심이에요,\n박서연 과장님', 19, 'ExtraBold', '#FFFFFF', 'greeting'); g.lineHeight = {unit: 'PERCENT', value: 130}; put(mid, g, 'FILL'); g.textAutoResize = 'HEIGHT';
  mid.appendChild(img('mascot-3d-card', 100, 81));
  const stats = AL('HORIZONTAL', {name: 'stats', itemSpacing: 6}); put(sum, stats, 'FILL');
  for (const [ic, lab, n, red] of [['clipboard', '챙길 일', '3', false], ['hard-hat', '남은 작업', '3', false], ['cloud-sun', '내일 중지', '1', true]]) {
    const st = AL('VERTICAL', {name: 'stat/' + lab, itemSpacing: 2, paddingLeft: 10, paddingRight: 10, paddingTop: 8, paddingBottom: 8, cornerRadius: 12}); st.fills = P('#FFFFFF', 0.08); st.strokes = P('#FFFFFF', 0.12); st.strokeWeight = 1; put(stats, st, 'FILL');
    const l = AL('HORIZONTAL', {itemSpacing: 5, counterAxisAlignItems: 'CENTER', name: 'label'}); st.appendChild(l); l.appendChild(icon(ic, 15, '#C9D2FF')); l.appendChild(T(lab, 11.5, 'SemiBold', '#C9D2FF'));
    const num = T(n, 22, 'ExtraBold', red ? '#FFB4A8' : '#FFFFFF'); num.lineHeight = {unit: 'PERCENT', value: 110}; st.appendChild(num);
  }
  secHead(b, '먼저 챙길 것', '3건', '내 조치');
  const grid = AL('VERTICAL', {name: 'todoGrid', itemSpacing: 8}); put(b, grid, 'FILL');
  const TILES = [['변경 결정', '2', '타설 시간 두 시간 앞당기기'], ['할 일', '0', '답할 요청이 없어요'], ['확인 대기', '0', '확인할 보고가 없어요'], ['보류', '1', '옥상 배수구 주변 재시공']];
  for (let r = 0; r < 2; r++) { const row = AL('HORIZONTAL', {name: 'row', itemSpacing: 8}); put(grid, row, 'FILL'); for (let c = 0; c < 2; c++) { const [kind, count, topText] = TILES[r * 2 + c]; const i = variantOf(tileSet, 'Kind=' + kind).createInstance(); put(row, i, 'FILL', 'FILL'); i.setProperties({[TT.title]: kind, [TT.count]: count, [TT.top]: topText}); if (count === '0') i.findOne(n => n.name === 'countText').fills = P('placeholder'); } }
  const alert = AL('HORIZONTAL', {name: 'scheduleAlert', itemSpacing: 10, counterAxisAlignItems: 'CENTER', paddingLeft: 12, paddingRight: 12, paddingTop: 10, paddingBottom: 10, cornerRadius: 14}); alert.fills = P('check-bg'); put(b, alert, 'FILL');
  const at = AL('HORIZONTAL', {paddingLeft: 8, paddingRight: 8, paddingTop: 4, paddingBottom: 4, cornerRadius: 7, name: 'tag'}); at.fills = P('#FFFFFF'); alert.appendChild(at); at.appendChild(T('겹침', 11.5, 'Bold', 'check-fg'));
  wrapText(alert, T('오늘 작업 점검 2건 · 겹침', 13, 'SemiBold', 'check-fg'), true); alert.appendChild(icon('chevron-right', 16, '#874A00'));
  secHead(b, '오늘 작업', '10월 29일(목) · 10건', '+ 추가');
  const l1 = list(b);
  for (const [st, en, t, m, ph] of [['08:00', '17:00', '철골 작업', '102동 2층 보 · 우진철강', '진행 중'], ['08:00', '17:00', '철골 작업', '102동 2층 보 · 우진철강', '진행 중'], ['18:30', '21:30', '아스팔트 포장', '한빛자재', '예정']]) {
    const i = jobRow.createInstance(); put(l1, i, 'FILL'); i.setProperties({[JR.start]: st, [JR.end]: en, [JR.title]: t, [JR.meta]: m, [JR.phase]: ph});
    if (ph === '예정') { i.findOne(n => n.name === 'phase').fills = P('surface'); i.findOne(n => n.name === 'phaseText').fills = P('muted'); i.findOne(n => n.name === 'tradeDot').fills = P('#0D9488'); }
  }
  const more = AL('HORIZONTAL', {name: 'more', counterAxisAlignItems: 'CENTER', paddingLeft: 14, paddingRight: 12, paddingTop: 12, paddingBottom: 12}); put(l1, more, 'FILL'); wrapText(more, T('7건 더 보기', 14, 'SemiBold', 'accent'), true); more.appendChild(icon('chevron-right', 16, '#1C60EF'));
  tabbar(s, '오늘');
}
// 02 내 조치
{
  const s = screen('02 내 조치');
  const bg = figma.createRectangle(); bg.name = 'headerBg'; s.appendChild(bg); bg.resize(390, 62); bg.fills = P('card'); bg.x = 0; bg.y = 56;
  header(s, '내 조치', '전체 현장');
  const seg = AL('HORIZONTAL', {name: 'subMenu', itemSpacing: 4, paddingLeft: 4, paddingRight: 4, paddingTop: 4, paddingBottom: 4, cornerRadius: 12}); seg.fills = P('surface'); s.appendChild(seg); seg.resize(358, 44); seg.primaryAxisSizingMode = 'FIXED'; seg.counterAxisSizingMode = 'AUTO'; seg.x = 16; seg.y = 64;
  for (const [lab, on] of [['변경 건', false], ['내 조치', true]]) { const it = AL('HORIZONTAL', {primaryAxisAlignItems: 'CENTER', counterAxisAlignItems: 'CENTER', cornerRadius: 9, paddingTop: 9, paddingBottom: 9, name: 'seg/' + lab}); it.fills = on ? P('card') : []; if (on) it.effects = shadow(0.12, 1, 3); put(seg, it, 'FILL'); it.appendChild(T(lab, 14, 'Bold', on ? 'ink' : 'muted')); }
  const b = body(s, 118);
  const chips = AL('HORIZONTAL', {name: 'groupChips', itemSpacing: 6}); put(b, chips, 'FILL');
  for (const [lab, n, col] of [['할 일', '3', '#0E1E45'], ['확인 대기', '3', '#1C60EF'], ['보류', '0', '#D9483B']]) { const c = AL('HORIZONTAL', {itemSpacing: 5, primaryAxisAlignItems: 'CENTER', counterAxisAlignItems: 'CENTER', paddingTop: 7, paddingBottom: 7, cornerRadius: 999, name: 'chip/' + lab}); c.fills = P('card'); c.strokes = P('line'); c.strokeWeight = 1; put(chips, c, 'FILL'); const d = figma.createEllipse(); d.resize(8, 8); d.fills = P(col); c.appendChild(d); c.appendChild(T(lab, 13, 'SemiBold', 'ink')); c.appendChild(T(n, 13, 'Bold', 'accent')); }
  const sh = secHead(b, '할 일', '3건 · 기한 지난 것부터', null);
  const dl = AL('HORIZONTAL', {itemSpacing: 4, counterAxisAlignItems: 'CENTER', name: 'handOver'}); sh.appendChild(dl); dl.appendChild(icon('user-plus', 15, '#1C60EF')); dl.appendChild(T('잠시 맡기기', 13, 'SemiBold', 'accent'));
  const l2 = list(b);
  for (const site of ['이천 물류센터 신축공사', '해운대 오피스텔', '대전 초등학교']) { const i = listRow.createInstance(); put(l2, i, 'FILL'); i.setProperties({[LR.title]: '철골 자재 반입 일정 다시 확인', [LR.meta]: '10/25(일) 17:00까지 · 기한 지남 · ' + site, [LR.status]: '요청 대기'}); }
  secHead(b, '확인 대기', '3건 · 기한 지난 것부터', null);
  const l3 = list(b);
  for (const site of ['롯데마트 현장', '리버뷰 아파트', '판교 지식산업센터']) { const i = listRow.createInstance(); put(l3, i, 'FILL'); i.setProperties({[LR.title]: '크레인 위치 변경 계획 제출', [LR.meta]: '10/30(금) 12:00까지 · ' + site, [LR.status]: '확인 대기'}); i.findOne(n => n.name === 'tag').fills = P('accent-soft'); i.findOne(n => n.name === 'tagText').fills = P('accent'); }
  secHead(b, '보류', '0건', null); b.appendChild(T('보류 중인 조치가 없어요', 12.5, 'Regular', 'muted'));
  tabbar(s, '조치');
}
// 03 대화방 · 첨부(+ 메뉴 열림)
{
  const s = screen('03 대화방 · 첨부'); s.fills = P('#E9EFF8');
  const h = AL('HORIZONTAL', {name: 'header', itemSpacing: 8, counterAxisAlignItems: 'CENTER', paddingLeft: 8, paddingRight: 16}); h.fills = P('card'); strokeOnly(h, 'bottom'); s.appendChild(h); h.resize(390, 56); h.primaryAxisSizingMode = 'FIXED'; h.counterAxisSizingMode = 'FIXED'; h.x = 0; h.y = 0;
  h.appendChild(icon('arrow-left', 24, '#0E1E45')); wrapText(h, T('판교 지식산업센터 신축공사', 17, 'ExtraBold', 'ink'), true); h.appendChild(icon('calendar', 22, '#5B6576'));
  const msgs = AL('VERTICAL', {name: 'messages', itemSpacing: 14, paddingLeft: 16, paddingRight: 16, paddingTop: 16, paddingBottom: 16}); s.appendChild(msgs); msgs.resize(390, 10); msgs.counterAxisSizingMode = 'FIXED'; msgs.primaryAxisSizingMode = 'AUTO'; msgs.x = 0; msgs.y = 56;
  const other = (initial, who, company, text, extra) => { const r = AL('HORIZONTAL', {name: 'msg/' + who, itemSpacing: 8}); put(msgs, r, 'FILL'); const av = box(32, 10, P('card')); r.appendChild(av); av.appendChild(T(initial, 13, 'Bold', 'ink')); const col = AL('VERTICAL', {itemSpacing: 4, name: 'main'}); r.appendChild(col); const w = AL('HORIZONTAL', {itemSpacing: 4}); col.appendChild(w); w.appendChild(T(who, 12, 'Bold', 'ink')); w.appendChild(T('· ' + company, 12, 'Regular', 'muted')); const bub = AL('VERTICAL', {itemSpacing: 8, paddingLeft: 14, paddingRight: 14, paddingTop: 10, paddingBottom: 10, cornerRadius: 16, name: 'bubble'}); bub.fills = P('card'); col.appendChild(bub); bub.appendChild(T(text, 14, 'Regular', 'text')); if (extra) bub.appendChild(extra); };
  const cc = AL('HORIZONTAL', {itemSpacing: 8, counterAxisAlignItems: 'CENTER', paddingLeft: 10, paddingRight: 10, paddingTop: 8, paddingBottom: 8, cornerRadius: 8, name: 'caseCard'}); cc.fills = P('surface'); cc.appendChild(icon('history', 14, '#0E1E45')); const ccc = AL('VERTICAL', {itemSpacing: 1}); cc.appendChild(ccc); ccc.appendChild(T('타설 시간 두 시간 앞당기기', 13, 'Bold', 'ink')); ccc.appendChild(T('지금 v1 영향 검토', 12, 'SemiBold', 'check-fg'));
  other('김', '김정현', '산군', '타설 시간 앞당기는 변경 올렸어요.\n후속 조치 확인 부탁드려요.', cc);
  other('오', '오상훈 기사', '서해펌프', '네 봤습니다. 바뀐 시간으로 반장님께\n전달하고 조치 수락해 둘게요.');
  const mine = AL('VERTICAL', {name: 'msg/mine', counterAxisAlignItems: 'MAX', itemSpacing: 4}); put(msgs, mine, 'FILL');
  const mb = AL('VERTICAL', {itemSpacing: 8, paddingLeft: 14, paddingRight: 14, paddingTop: 10, paddingBottom: 10, cornerRadius: 16, name: 'bubble'}); mb.fills = P('accent'); mine.appendChild(mb); mb.appendChild(T('이분께 연락 부탁해요', 14, 'Medium', '#FFFFFF'));
  // 연락처 카드: 전화번호는 조정자·담당자에게만 보인다(열람자에게 숨김, D-111)
  const ct = AL('HORIZONTAL', {itemSpacing: 8, counterAxisAlignItems: 'CENTER', paddingLeft: 10, paddingRight: 10, paddingTop: 8, paddingBottom: 8, cornerRadius: 8, name: 'contactCard'}); ct.fills = P('#FFFFFF'); mb.appendChild(ct);
  const ca = box(28, 999, P('#FFF3E0')); ct.appendChild(ca); ca.appendChild(T('강', 13, 'ExtraBold', '#E65100'));
  const ci = AL('VERTICAL', {itemSpacing: 1}); ct.appendChild(ci); ci.appendChild(T('강석구 현장대리인', 13, 'Bold', 'ink')); ci.appendChild(T('한빛자재', 12, 'Regular', 'muted'));
  const tel = AL('HORIZONTAL', {itemSpacing: 4, counterAxisAlignItems: 'CENTER', paddingLeft: 10, paddingRight: 10, paddingTop: 4, paddingBottom: 4, cornerRadius: 999, name: 'tel'}); tel.fills = P('accent-soft'); ct.appendChild(tel); tel.appendChild(icon('phone', 13, '#1C60EF')); tel.appendChild(T('010-2345-6789', 12, 'Bold', 'accent'));
  mine.appendChild(T('15:30', 11, 'Regular', 'placeholder'));
  const comp = AL('HORIZONTAL', {name: 'composer', itemSpacing: 8, counterAxisAlignItems: 'CENTER', paddingLeft: 10, paddingRight: 10}); comp.fills = P('card'); strokeOnly(comp, 'top'); s.appendChild(comp); comp.resize(390, 60); comp.primaryAxisSizingMode = 'FIXED'; comp.counterAxisSizingMode = 'FIXED'; comp.x = 0; comp.y = 844 - 60;
  const plus = box(40, 999, P('accent-soft')); plus.name = 'attachOpen'; comp.appendChild(plus); plus.appendChild(icon('plus', 20, '#1C60EF'));
  const inp = AL('HORIZONTAL', {counterAxisAlignItems: 'CENTER', paddingLeft: 14, paddingRight: 14, cornerRadius: 20, name: 'input'}); inp.fills = P('surface'); put(comp, inp, 'FILL'); inp.resize(inp.width, 40); inp.counterAxisSizingMode = 'FIXED'; inp.appendChild(T('메시지 보내기', 15, 'Regular', 'placeholder'));
  const send = box(40, 999, P('accent')); comp.appendChild(send); send.appendChild(icon('arrow-right', 20, '#FFFFFF'));
  const panel = AL('HORIZONTAL', {name: 'attachMenu', itemSpacing: 6, paddingLeft: 12, paddingRight: 12, paddingTop: 12, paddingBottom: 12, cornerRadius: 16}); panel.fills = P('card'); panel.strokes = P('line-soft'); panel.strokeWeight = 1; panel.effects = shadow(0.16, 8, 24); s.appendChild(panel); panel.resize(320, 10); panel.primaryAxisSizingMode = 'FIXED'; panel.counterAxisSizingMode = 'AUTO';
  for (const [lab, ic, bgc, col] of [['사진', 'image', '#E8F5E9', '#2E7D32'], ['연락처', 'user', '#FFF3E0', '#E65100'], ['변경 건', 'history', '#F1E9FF', '#7C3AED'], ['조치', 'check', '#EAF1FE', '#1C60EF']]) { const it = AL('VERTICAL', {itemSpacing: 6, counterAxisAlignItems: 'CENTER', paddingTop: 8, paddingBottom: 8, name: 'attach/' + lab}); put(panel, it, 'FILL'); const bx = box(44, 14, P(bgc)); it.appendChild(bx); bx.appendChild(icon(ic, 20, col)); it.appendChild(T(lab, 12.5, 'SemiBold', 'ink')); }
  panel.x = 10; panel.y = 844 - 60 - 8 - panel.height;
}
fitSection(sec);
return done;
