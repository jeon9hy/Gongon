// 공온 · 웹 / 페이지 "서비스 사이트": 01 첫 화면(로그인 전) · 02 내 현장 고르기(로그인 뒤). _common.js 뒤에 붙여 실행.
// 앱 화면: app/features/intro/templates/intro/home.html · launch.html (D-110). 다시 실행하면 같은 이름의 화면을 지우고 그 자리에 다시 그린다.
const headSet = await component('SiteHeader'); const btnSet = await component('Button'); const siteRow = await component('SiteRow');
await usePage('서비스 사이트');
const button = (v, label) => { const i = variantOf(btnSet, 'Variant=' + v).createInstance(); i.setProperties({[propKey(btnSet, 'Label')]: label}); return i; };
const header = state => variantOf(headSet, 'State=' + state).createInstance();
const sec = section('서비스 사이트 · 화면', 0, 0);
function screen(name, h) { const at = replaceIn(sec, name, 100); const f = figma.createFrame(); f.name = name; f.resize(1440, h); f.fills = P('backdrop'); f.clipsContent = true; sec.appendChild(f); f.x = at.x; f.y = at.y; done.created.push(f.id); return f; }

// 01 첫 화면
{
  const w = screen('01 첫 화면 · 로그인 전', 900);
  w.fills = [{type: 'GRADIENT_RADIAL', gradientTransform: [[0.6, 0, 0.55], [0, 0.6, 0]], gradientStops: [{position: 0, color: {...rgb('#CFE0FF'), a: 1}}, {position: 1, color: {...rgb('#F5F8FD'), a: 1}}]}];
  const hd = header('로그인 전'); w.appendChild(hd); hd.x = 0; hd.y = 0;
  const hero = AL('HORIZONTAL', {name: 'hero', itemSpacing: 32, counterAxisAlignItems: 'CENTER', paddingLeft: 120, paddingRight: 120}); w.appendChild(hero); hero.resize(1440, 828); hero.primaryAxisSizingMode = 'FIXED'; hero.counterAxisSizingMode = 'FIXED'; hero.x = 0; hero.y = 72;
  const copy = AL('VERTICAL', {name: 'copy', itemSpacing: 22}); put(hero, copy, 'FILL');
  const eb = AL('HORIZONTAL', {name: 'eyebrow', paddingLeft: 12, paddingRight: 12, paddingTop: 6, paddingBottom: 6, cornerRadius: 999}); eb.fills = P('card'); copy.appendChild(eb); eb.appendChild(T('공사 + ON', 13, 'Bold', 'accent'));
  const title = T('변경 뒤 남은 조치는\n무엇인가요?', 58, 'ExtraBold', 'ink', 'title'); title.lineHeight = {unit: 'PERCENT', value: 118}; title.letterSpacing = {unit: 'PERCENT', value: -4}; copy.appendChild(title);
  title.setRangeFills(title.characters.indexOf('무엇'), title.characters.length, P('accent'));
  const lead = T('공사 계획이 바뀔 때 함께 바꿔야 할 일을 업체와 담당자에게 잇고,\n실제로 처리됐는지 근거와 확인까지 남겨요.', 18, 'Regular', 'muted'); lead.lineHeight = {unit: 'PERCENT', value: 160}; copy.appendChild(lead);
  const acts = AL('HORIZONTAL', {name: 'actions', itemSpacing: 12}); copy.appendChild(acts); acts.appendChild(button('주', '가입하고 시작하기')); acts.appendChild(button('테두리', '로그인'));
  const art = figma.createFrame(); art.name = 'art'; art.fills = []; art.resize(560, 460); hero.appendChild(art); art.clipsContent = false;
  const orb = figma.createEllipse(); orb.name = 'orb'; orb.resize(340, 340); orb.x = 110; orb.y = 60; orb.fills = [{type: 'GRADIENT_RADIAL', gradientTransform: [[1, 0, 0], [0, 1, 0]], gradientStops: [{position: 0, color: {r: 1, g: 1, b: 1, a: 1}}, {position: 1, color: {...rgb('#8FB3FF'), a: 1}}]}]; orb.opacity = 0.75; art.appendChild(orb);
  const ring = figma.createEllipse(); ring.name = 'ring'; ring.resize(420, 420); ring.x = 70; ring.y = 20; ring.fills = []; ring.strokes = P('accent', 0.2); ring.strokeWeight = 2; ring.dashPattern = [8, 8]; art.appendChild(ring);
  const m = img('mascot-3d-card', 400, 324); art.appendChild(m); m.x = 80; m.y = 70;
  // 예시 상태 칩은 장식이며 실제 자료가 아니다(D-072)
  for (const [txt, col, x, y] of [['펌프카 예약 변경 · 검증 완료', '#2E9E5B', 0, 50], ['변경 v2 · 필수 조치 2건 남음', '#E89A00', 300, 330], ['가상골조 · 완료 보고 대기', '#1C60EF', 40, 410]]) {
    const chip = AL('HORIZONTAL', {name: 'statusChip', itemSpacing: 8, counterAxisAlignItems: 'CENTER', paddingLeft: 16, paddingRight: 16, paddingTop: 10, paddingBottom: 10, cornerRadius: 999}); chip.fills = P('#FFFFFF', 0.92); chip.effects = shadow(0.12, 8, 24); art.appendChild(chip);
    const d = figma.createEllipse(); d.resize(10, 10); d.fills = P(col); chip.appendChild(d); chip.appendChild(T(txt, 14, 'SemiBold', 'ink')); chip.x = x; chip.y = y;
  }
}

// 02 내 현장 고르기
{
  const w = screen('02 내 현장 고르기 · 로그인 뒤', 1100);
  const hd = header('로그인 후'); w.appendChild(hd); hd.x = 0; hd.y = 0;
  const band = AL('VERTICAL', {name: 'welcomeBand', itemSpacing: 10, counterAxisAlignItems: 'CENTER', paddingTop: 40}); band.fills = grad('#E1EBFF', '#F5F8FD'); w.appendChild(band); band.resize(1440, 300); band.primaryAxisSizingMode = 'FIXED'; band.counterAxisSizingMode = 'FIXED'; band.x = 0; band.y = 72;
  band.appendChild(img('mascot-3d-card', 120, 97)); band.appendChild(T('다시 만나서 반가워요, 박서연 과장님', 38, 'ExtraBold', 'ink')); band.appendChild(T('현장을 골라 시작하세요.', 16, 'Regular', 'muted'));
  const cols = AL('HORIZONTAL', {name: 'columns', itemSpacing: 24}); w.appendChild(cols); cols.resize(1200, 10); cols.primaryAxisSizingMode = 'FIXED'; cols.counterAxisSizingMode = 'AUTO'; cols.x = 120; cols.y = 300;
  const left = AL('VERTICAL', {name: 'mySites', itemSpacing: 12}); cols.appendChild(left); left.resize(784, 10); left.layoutSizingHorizontal = 'FIXED'; left.layoutSizingVertical = 'HUG';
  const lh = AL('HORIZONTAL', {itemSpacing: 8, counterAxisAlignItems: 'CENTER', name: 'label'}); left.appendChild(lh); lh.appendChild(icon('site', 18, '#0E1E45')); lh.appendChild(T('내 현장', 16, 'Bold', 'ink'));
  const card = AL('VERTICAL', {name: 'siteCard', itemSpacing: 12, paddingLeft: 24, paddingRight: 24, paddingTop: 8, cornerRadius: 24}); card.fills = P('card'); card.strokes = P('line-soft'); card.strokeWeight = 1; card.effects = shadow(0.1, 16, 40); put(left, card, 'FILL');
  const tabs = AL('HORIZONTAL', {name: 'tabs', itemSpacing: 4}); strokeOnly(tabs, 'bottom'); put(card, tabs, 'FILL');
  for (const [lab, on] of [['참여 중 4', true], ['코드로 참여', false]]) { const tb = AL('HORIZONTAL', {paddingLeft: 14, paddingRight: 14, paddingTop: 14, paddingBottom: 14, name: 'tab/' + lab}); if (on) { tb.strokes = P('accent'); tb.strokeTopWeight = 0; tb.strokeLeftWeight = 0; tb.strokeRightWeight = 0; tb.strokeBottomWeight = 2; } tabs.appendChild(tb); tb.appendChild(T(lab, 15, 'SemiBold', on ? 'ink' : 'muted')); }
  const rows = AL('VERTICAL', {name: 'sites', itemSpacing: 8}); put(card, rows, 'FILL');
  const K = {mark: propKey(siteRow, 'Mark'), name: propKey(siteRow, 'Name'), sub: propKey(siteRow, 'Sub')};
  for (const [mark, name, sub, all] of [['전', '전체 현장', '4곳 함께 보기', true], ['남', '남산공원 xx공사 현장', '서울 용산구 남산공원길 123', false], ['롯', '롯데마트 현장', '서울 금천구 시흥대로100길 7', false], ['리', '리버뷰 아파트 신축공사', '서울 중구 세종대로 110', false], ['판', '판교 지식산업센터 신축공사', '경기 성남시 분당구 판교역로 166', false]]) {
    const r = siteRow.createInstance(); put(rows, r, 'FILL'); r.setProperties({[K.mark]: mark, [K.name]: name, [K.sub]: sub});
    if (all) { r.findOne(n => n.name === 'mark').fills = P('accent'); r.findOne(n => n.name === 'markText').fills = P('#FFFFFF'); }
  }
  const foot = AL('HORIZONTAL', {name: 'foot', counterAxisAlignItems: 'CENTER', paddingTop: 16, paddingBottom: 16}); strokeOnly(foot, 'top'); put(card, foot, 'FILL');
  const nw = AL('HORIZONTAL', {itemSpacing: 6, counterAxisAlignItems: 'CENTER'}); foot.appendChild(nw); nw.appendChild(icon('plus', 16, '#1C60EF')); nw.appendChild(T('새 현장 만들기', 14, 'SemiBold', 'accent'));
  spacer(foot); foot.appendChild(T('현장이 보이지 않나요? ', 14, 'Regular', 'muted')); foot.appendChild(T('다른 계정으로 로그인', 14, 'SemiBold', 'accent'));
  const right = AL('VERTICAL', {name: 'side', itemSpacing: 16}); put(cols, right, 'FILL');
  const rh = AL('HORIZONTAL', {itemSpacing: 8, counterAxisAlignItems: 'CENTER', name: 'label'}); right.appendChild(rh); const rav = box(24, 999, P('accent')); rh.appendChild(rav); rav.appendChild(T('박', 12, 'Bold', '#FFFFFF')); rh.appendChild(T('산군', 16, 'Bold', 'ink'));
  for (const [ttl, sub, btn, ic] of [['처음이라면 가이드부터', '메뉴와 판정 읽는 법을 한곳에 모았어요.', '가이드 보기', 'info'], ['업체 담당자를 불러요', '현장 코드를 보내면 담당자가 스스로 들어와요.', '업체 보기', 'user-plus']]) {
    const tc = AL('HORIZONTAL', {name: 'tip', itemSpacing: 16, counterAxisAlignItems: 'CENTER', paddingLeft: 24, paddingRight: 24, paddingTop: 22, paddingBottom: 22, cornerRadius: 20}); tc.fills = P('card'); tc.strokes = P('line-soft'); tc.strokeWeight = 1; put(right, tc, 'FILL');
    const tx = AL('VERTICAL', {itemSpacing: 6}); put(tc, tx, 'FILL'); tx.appendChild(T(ttl, 16, 'Bold', 'ink')); wrapText(tx, T(sub, 14, 'Regular', 'muted')); tx.appendChild(button('보조', btn));
    const ti = box(64, 999, P('accent-soft')); tc.appendChild(ti); ti.appendChild(icon(ic, 26, '#1C60EF'));
  }
  const more = AL('VERTICAL', {name: 'learnMore', itemSpacing: 12}); w.appendChild(more); more.resize(1200, 10); more.primaryAxisSizingMode = 'AUTO'; more.counterAxisSizingMode = 'FIXED'; more.x = 120;
  const mh = AL('HORIZONTAL', {itemSpacing: 8, counterAxisAlignItems: 'CENTER', name: 'label'}); more.appendChild(mh); mh.appendChild(icon('arrow-right', 18, '#0E1E45')); mh.appendChild(T('더 알아보기', 16, 'Bold', 'ink'));
  const mrow = AL('HORIZONTAL', {itemSpacing: 16}); put(more, mrow, 'FILL');
  for (const [ttl, sub, ic] of [['기능 둘러보기', '변경 관리부터 현장 대화까지 다섯 가지 기능이에요.', 'clipboard'], ['휴대폰으로 쓰기', '현장에서는 휴대폰 화면으로 내 할 일부터 봐요.', 'smartphone'], ['공온 이야기', '왜 시작했고 무엇을 지키는지 적었어요.', 'history']]) {
    const mc = AL('HORIZONTAL', {name: 'moreCard', itemSpacing: 12, counterAxisAlignItems: 'MAX', paddingLeft: 24, paddingRight: 20, paddingTop: 24, paddingBottom: 20, cornerRadius: 20}); mc.fills = P('backdrop'); mc.strokes = P('line-soft'); mc.strokeWeight = 1; put(mrow, mc, 'FILL');
    const tx = AL('VERTICAL', {itemSpacing: 6}); put(mc, tx, 'FILL'); tx.appendChild(T(ttl, 17, 'Bold', 'ink')); wrapText(tx, T(sub, 14, 'Regular', 'muted'));
    const ti = box(56, 999, P('card')); mc.appendChild(ti); ti.appendChild(icon(ic, 26, '#1C60EF'));
  }
  more.y = cols.y + cols.height + 48; w.resize(1440, Math.ceil(more.y + more.height + 64));
}
fitSection(sec);
return done;
