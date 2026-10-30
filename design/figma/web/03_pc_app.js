// 공온 · 웹 / 페이지 "PC 앱": 03 홈 · 현장 하나. _common.js 뒤에 붙여 실행.
// 앱 화면: app/features/judgments/templates/judgments/home.html. 날씨 칸은 현장 하나일 때만(D-110).
const appBar = await component('AppBar'); const segSet = await component('SegTab'); const wxSet = await component('WeatherTile'); const companyRow = await component('CompanyRow');
await usePage('PC 앱');
const seg = (label, on) => { const i = variantOf(segSet, 'Selected=' + on).createInstance(); i.setProperties({[propKey(segSet, 'Label')]: label}); return i; };
const sec = section('PC 앱 · 화면', 0, 0);
function screen(name, h) { const at = replaceIn(sec, name, 100); const f = figma.createFrame(); f.name = name; f.resize(1440, h); f.fills = P('backdrop'); f.clipsContent = true; sec.appendChild(f); f.x = at.x; f.y = at.y; done.created.push(f.id); return f; }

{
  const w = screen('03 홈 · 현장 하나', 1000);
  const ab = variantOf(appBar, 'Active=홈').createInstance(); w.appendChild(ab); ab.x = 0; ab.y = 0; ab.setProperties({[propKey(appBar, 'Site')]: '롯데마트 현장'});
  const pg = AL('VERTICAL', {name: 'page', itemSpacing: 22, paddingLeft: 120, paddingRight: 120, paddingTop: 28}); w.appendChild(pg); pg.resize(1440, 10); pg.primaryAxisSizingMode = 'AUTO'; pg.counterAxisSizingMode = 'FIXED'; pg.x = 0; pg.y = 64;
  const hrow = AL('HORIZONTAL', {name: 'greeting', counterAxisAlignItems: 'CENTER'}); put(pg, hrow, 'FILL');
  const hcol = AL('VERTICAL', {itemSpacing: 4}); put(hrow, hcol, 'FILL');
  hcol.appendChild(T('10월 29일(목) · 좋은 점심이에요', 14, 'SemiBold', 'accent'));
  const ht = T('박서연 과장님, 확인할 일 5건', 34, 'ExtraBold', 'ink'); ht.letterSpacing = {unit: 'PERCENT', value: -3}; hcol.appendChild(ht); ht.setRangeFills(ht.characters.indexOf('5건'), ht.characters.length, P('accent'));
  hcol.appendChild(T('오늘 필요한 정보만, 한눈에 확인하세요.', 15, 'Regular', 'muted'));
  const refresh = AL('HORIZONTAL', {name: 'refresh', itemSpacing: 12, counterAxisAlignItems: 'CENTER', paddingLeft: 14, paddingRight: 8, paddingTop: 8, paddingBottom: 8, cornerRadius: 999}); refresh.fills = P('card'); refresh.strokes = P('line-soft'); refresh.strokeWeight = 1; refresh.effects = shadow(0.08, 4, 12); hrow.appendChild(refresh);
  const tg = AL('HORIZONTAL', {counterAxisAlignItems: 'CENTER', primaryAxisAlignItems: 'MAX', paddingLeft: 3, paddingRight: 3, cornerRadius: 999, name: 'toggle'}); tg.fills = P('accent'); refresh.appendChild(tg); tg.resize(40, 24); tg.primaryAxisSizingMode = 'FIXED'; tg.counterAxisSizingMode = 'FIXED'; const knob = figma.createEllipse(); knob.resize(18, 18); knob.fills = P('#FFFFFF'); tg.appendChild(knob);
  const rt = AL('VERTICAL', {itemSpacing: 0}); refresh.appendChild(rt); rt.appendChild(T('공온 점검', 11, 'SemiBold', 'accent')); rt.appendChild(T('15:15 확인', 14, 'Bold', 'ink'));
  const rg = box(32, 999, P('accent')); refresh.appendChild(rg); rg.appendChild(icon('history', 16, '#FFFFFF'));
  const cards = AL('HORIZONTAL', {name: 'sumcards', itemSpacing: 16}); put(pg, cards, 'FILL');
  const hc = AL('VERTICAL', {name: 'firstThing', itemSpacing: 10, paddingLeft: 32, paddingRight: 32, paddingTop: 30, paddingBottom: 30, cornerRadius: 22}); hc.fills = grad('#24318C', '#1B2468', NAVY); hc.effects = shadow(0.25, 10, 28); cards.appendChild(hc); hc.resize(520, 10); hc.layoutSizingHorizontal = 'FIXED'; hc.layoutSizingVertical = 'FILL';
  hc.appendChild(T('먼저 확인할 일', 14, 'Bold', '#E3E8FF'));
  const pill = AL('HORIZONTAL', {itemSpacing: 6, counterAxisAlignItems: 'CENTER', paddingLeft: 12, paddingRight: 12, paddingTop: 6, paddingBottom: 6, cornerRadius: 999, name: 'pill'}); pill.fills = P('#FFE08A'); hc.appendChild(pill); pill.appendChild(icon('calendar', 15, '#874A00')); pill.appendChild(T('일정 겹침', 14, 'Bold', '#874A00'));
  hc.appendChild(T('철골 작업', 32, 'ExtraBold', '#FFFFFF')); hc.appendChild(T('102동 2층 보 · 롯데마트 현장', 16, 'Regular', '#C9D2FF'));
  const rule = figma.createRectangle(); rule.name = 'rule'; rule.fills = P('#FFFFFF', 0.18); hc.appendChild(rule); rule.resize(456, 1); rule.layoutSizingHorizontal = 'FILL';
  hc.appendChild(T('겹친 일정', 14, 'Bold', '#E3E8FF')); hc.appendChild(T('2건', 34, 'ExtraBold', '#FFFFFF'));
  const hb = AL('HORIZONTAL', {itemSpacing: 6, counterAxisAlignItems: 'CENTER', paddingLeft: 22, paddingRight: 18, paddingTop: 13, paddingBottom: 13, cornerRadius: 12, name: 'cta'}); hb.fills = P('#FFFFFF'); hc.appendChild(hb); hb.appendChild(T('일정 확인하기', 15, 'Bold', 'ink')); hb.appendChild(icon('chevron-right', 16, '#0E1E45'));
  const wc = AL('VERTICAL', {name: 'weatherNow', itemSpacing: 12, paddingLeft: 28, paddingRight: 28, paddingTop: 28, paddingBottom: 24, cornerRadius: 22}); wc.fills = P('card'); wc.strokes = P('line-soft'); wc.strokeWeight = 1; put(cards, wc, 'FILL', 'FILL');
  const wh = AL('HORIZONTAL', {itemSpacing: 8, counterAxisAlignItems: 'CENTER'}); wc.appendChild(wh); wh.appendChild(T('지금 날씨', 18, 'Bold', 'ink')); const wtag = AL('HORIZONTAL', {paddingLeft: 8, paddingRight: 8, paddingTop: 2, paddingBottom: 2, cornerRadius: 999}); wtag.fills = P('surface'); wh.appendChild(wtag); wtag.appendChild(T('예보', 12, 'SemiBold', 'muted'));
  wc.appendChild(T('롯데마트 현장', 14, 'Regular', 'muted'));
  const wm = AL('HORIZONTAL', {itemSpacing: 14, counterAxisAlignItems: 'CENTER'}); wc.appendChild(wm); const wi = box(56, 16, P('accent-soft')); wm.appendChild(wi); wi.appendChild(icon('cloud-sun', 30, '#1C60EF', 1.8)); wm.appendChild(T('13°', 44, 'ExtraBold', 'ink')); wm.appendChild(T('비', 16, 'SemiBold', 'muted'));
  const wg = AL('VERTICAL', {itemSpacing: 8}); put(wc, wg, 'FILL');
  for (const pair of [[['바람', '3.1 m/s'], ['강수확률', '60%']], [['습도', '65%'], ['강수량', '1mm 미만']]]) { const r = AL('HORIZONTAL', {itemSpacing: 8}); put(wg, r, 'FILL'); for (const [k, val] of pair) { const i = variantOf(wxSet, 'Kind=' + k).createInstance(); put(r, i, 'FILL'); i.setProperties({[propKey(wxSet, 'Value')]: val}); } }
  wc.appendChild(T('16시 예보 · 14:00 발표 · 기상청', 12, 'Regular', 'muted'));
  const tc2 = AL('VERTICAL', {name: 'tomorrow', itemSpacing: 12, counterAxisAlignItems: 'CENTER', paddingLeft: 28, paddingRight: 28, paddingTop: 28, paddingBottom: 24, cornerRadius: 22}); tc2.fills = P('card'); tc2.strokes = P('line-soft'); tc2.strokeWeight = 1; put(cards, tc2, 'FILL', 'FILL');
  const tch = AL('VERTICAL', {itemSpacing: 2}); put(tc2, tch, 'FILL'); tch.appendChild(T('내일 작업 전망', 18, 'Bold', 'ink')); tch.appendChild(T('10월 30일(금)', 14, 'Regular', 'muted'));
  const ringF = figma.createFrame(); ringF.name = 'indexRing'; ringF.fills = []; ringF.resize(116, 116); tc2.appendChild(ringF);
  const rbg = figma.createEllipse(); rbg.resize(116, 116); rbg.fills = []; rbg.strokes = P('line-soft'); rbg.strokeWeight = 10; ringF.appendChild(rbg);
  const rarc = figma.createEllipse(); rarc.resize(116, 116); rarc.fills = []; rarc.strokes = P('stop-mark'); rarc.strokeWeight = 10; rarc.strokeCap = 'ROUND'; rarc.arcData = {startingAngle: -Math.PI / 2, endingAngle: -Math.PI / 2 + Math.PI * 2 * 0.3, innerRadius: 1}; ringF.appendChild(rarc);
  const score = T('30', 32, 'ExtraBold', 'ink'); ringF.appendChild(score); score.textAlignHorizontal = 'CENTER'; score.resize(116, score.height); score.x = 0; score.y = (116 - score.height) / 2;
  tc2.appendChild(T('공온지수', 13, 'SemiBold', 'muted'));
  const tcols = AL('HORIZONTAL', {itemSpacing: 0, paddingTop: 14}); strokeOnly(tcols, 'top'); put(tc2, tcols, 'FILL');
  for (const [lab, n, col] of [['중지', '1', 'stop-mark'], ['확인', '0', 'check-mark'], ['진행', '6', 'go-mark']]) { const c = AL('VERTICAL', {itemSpacing: 4, counterAxisAlignItems: 'CENTER'}); put(tcols, c, 'FILL'); const d = figma.createEllipse(); d.resize(10, 10); d.fills = P(col); c.appendChild(d); c.appendChild(T(lab, 13, 'SemiBold', 'muted')); c.appendChild(T(n, 24, 'ExtraBold', 'ink')); }
  const lower = AL('HORIZONTAL', {name: 'lower', itemSpacing: 24}); put(pg, lower, 'FILL');
  const today = AL('VERTICAL', {name: 'today', itemSpacing: 12, paddingLeft: 24, paddingRight: 24, paddingTop: 22, paddingBottom: 22, cornerRadius: 22}); today.fills = P('card'); today.strokes = P('line-soft'); today.strokeWeight = 1; put(lower, today, 'FILL');
  const tdh = AL('HORIZONTAL', {itemSpacing: 8, counterAxisAlignItems: 'BASELINE'}); today.appendChild(tdh); tdh.appendChild(T('오늘', 20, 'Bold', 'ink')); tdh.appendChild(T('10월 29일(목) · 오늘 남은 작업 3건', 14, 'Regular', 'muted'));
  // 묶어 보기 줄: 회색 알약은 업체별·위치별만, 주의는 옆에
  const gb = AL('HORIZONTAL', {name: 'groupBar', itemSpacing: 8, counterAxisAlignItems: 'CENTER'}); today.appendChild(gb);
  const pillBg = AL('HORIZONTAL', {itemSpacing: 2, paddingLeft: 3, paddingRight: 3, paddingTop: 3, paddingBottom: 3, cornerRadius: 999, name: 'groupSeg'}); pillBg.fills = P('surface'); gb.appendChild(pillBg); pillBg.appendChild(seg('업체별', true)); pillBg.appendChild(seg('위치별', false)); gb.appendChild(T('주의', 14, 'SemiBold', 'muted'));
  const K = {name: propKey(companyRow, 'Name'), meta: propKey(companyRow, 'Meta'), count: propKey(companyRow, 'Count'), state: propKey(companyRow, 'State')};
  for (const [nm, meta, count, state] of [['우진철강', '철강구조물공사업 · 08:00–17:00', '2건', '진행 중'], ['한빛자재', '철근 · 콘크리트공사업 · 18:30–21:30', '1건', '시작 전']]) { const i = companyRow.createInstance(); put(today, i, 'FILL'); i.setProperties({[K.name]: nm, [K.meta]: meta, [K.count]: count, [K.state]: state}); if (state === '시작 전') { i.findOne(n => n.name === 'state').fills = P('surface'); i.findOne(n => n.name === 'stateText').fills = P('muted'); } }
  const chg = AL('VERTICAL', {name: 'changesActions', itemSpacing: 14, paddingLeft: 24, paddingRight: 24, paddingTop: 22, paddingBottom: 22, cornerRadius: 22}); chg.fills = P('card'); chg.strokes = P('line-soft'); chg.strokeWeight = 1; put(lower, chg, 'FILL');
  const ch1 = AL('HORIZONTAL', {counterAxisAlignItems: 'CENTER', itemSpacing: 4}); put(chg, ch1, 'FILL'); ch1.appendChild(T('변경·조치', 20, 'Bold', 'ink')); spacer(ch1); const sb = AL('HORIZONTAL', {itemSpacing: 2, paddingLeft: 3, paddingRight: 3, paddingTop: 3, paddingBottom: 3, cornerRadius: 999}); sb.fills = P('surface'); ch1.appendChild(sb); sb.appendChild(seg('공정별', true)); sb.appendChild(seg('위치별', false));
  const ctabs = AL('HORIZONTAL', {itemSpacing: 4, paddingLeft: 4, paddingRight: 4, paddingTop: 4, paddingBottom: 4, cornerRadius: 999}); ctabs.fills = P('surface'); put(chg, ctabs, 'FILL');
  for (const [lab, n, on] of [['확인 대기', '0', true], ['보류', '1', false], ['결정 대기', '2', false]]) { const t = AL('HORIZONTAL', {itemSpacing: 8, primaryAxisAlignItems: 'CENTER', counterAxisAlignItems: 'CENTER', paddingTop: 10, paddingBottom: 10, cornerRadius: 999}); t.fills = on ? P('card') : []; put(ctabs, t, 'FILL'); t.appendChild(T(lab, 14, 'SemiBold', on ? 'ink' : 'muted')); const nb = box(20, 999, P(on ? 'accent-soft' : 'check-bg')); t.appendChild(nb); nb.appendChild(T(n, 11, 'Bold', on ? 'accent' : 'check-fg')); }
  chg.appendChild(T('협력업체가 끝냈다고 보고했어요', 14, 'Regular', 'muted'));
  const empty = AL('HORIZONTAL', {itemSpacing: 8, counterAxisAlignItems: 'CENTER'}); chg.appendChild(empty); empty.appendChild(icon('check', 16, '#2E9E5B', 2.4)); empty.appendChild(T('지금은 없어요', 15, 'Regular', 'muted'));
  w.resize(1440, Math.ceil(pg.y + pg.height + 48));
}
fitSection(sec);
return done;
