// 공온 Figma 공통 도우미(README 참고). 실행할 때 이 파일 내용을 각 스크립트 앞에 그대로 붙인다.
// 이름으로 찾고 이름으로 바꾼다: 색 변수는 컬렉션 "공온 색", 페이지·섹션·화면·컴포넌트도 이름으로 찾는다.

// gongon.css :root 토큰과 같은 이름·값. 앱 색을 바꾸면 여기도 고치고 기초 스크립트를 다시 실행한다.
const TOKENS = {
  'accent': '#1C60EF', 'accent-strong': '#1550CC', 'accent-fg': '#FFFFFF', 'accent-soft': '#EAF1FE',
  'ink': '#0E1E45', 'text': '#2B3445', 'muted': '#5B6576', 'placeholder': '#8A93A3',
  'surface': '#F2F6FC', 'card': '#FFFFFF', 'line': '#D3DCEA', 'line-soft': '#E6ECF5', 'backdrop': '#F5F8FD',
  'dark': '#0E1E45', 'dark-2': '#22396E',
  'verdict/go-bg': '#E3F5EA', 'verdict/go-fg': '#1D6B3A', 'verdict/go-mark': '#2E9E5B',
  'verdict/check-bg': '#FFF0D2', 'verdict/check-fg': '#874A00', 'verdict/check-mark': '#E89A00',
  'verdict/stop-bg': '#C9372C', 'verdict/stop-fg': '#FFFFFF', 'verdict/stop-mark': '#D9483B',
  'verdict/unknown-bg': '#EEF1F5', 'verdict/unknown-fg': '#5B6576', 'verdict/unknown-mark': '#A3ABB8',
  'stop-soft': '#FDECE9', 'stop-text': '#A82C22',
};
// app/core/templates/_macros.html 의 아이콘(같은 SVG 경로). 새 아이콘이 필요하면 거기서 옮겨 온다.
const ICONS = {
  'home': '<path d="M4 11l8-7 8 7"></path><path d="M6 9.5V20h12V9.5"></path><path d="M10 20v-5h4v5"></path>',
  'calendar': '<rect x="3" y="4" width="18" height="18" rx="2"></rect><path d="M16 2v4M8 2v4M3 10h18"></path>',
  'clipboard': '<rect x="5" y="4" width="14" height="17" rx="2"></rect><path d="M9 4V3h6v1"></path><path d="M8.5 12.5l2.2 2.2 4.8-5"></path>',
  'building': '<path d="M4 21V5a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v16"></path><path d="M15 10h4a1 1 0 0 1 1 1v10"></path><path d="M3 21h18"></path><path d="M8 8h3M8 12h3M8 16h3"></path>',
  'chat': '<path d="M5 18l-1.5 3 4-1.5A8.5 8.5 0 1 0 5 18z"></path><path d="M8.5 11h7M8.5 14h4"></path>',
  'check': '<path d="M5 12l5 5 9-10"></path>',
  'user': '<circle cx="12" cy="8" r="4"></circle><path d="M4 21a8 8 0 0 1 16 0"></path>',
  'history': '<circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path>',
  'image': '<rect x="3" y="3" width="18" height="18" rx="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><path d="M21 15l-5-5L5 21"></path>',
  'plus': '<path d="M12 5v14M5 12h14"></path>',
  'arrow-right': '<path d="M5 12h14M13 6l6 6-6 6"></path>',
  'arrow-left': '<path d="M19 12H5M11 6l-6 6 6 6"></path>',
  'chevron-right': '<path d="M9 6l6 6-6 6"></path>',
  'chevron-down': '<path d="M6 9l6 6 6-6"></path>',
  'cloud-sun': '<path d="M12 2v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="M20 12h2"></path><path d="m19.07 4.93-1.41 1.41"></path><path d="M15.947 12.65a4 4 0 0 0-5.925-4.128"></path><path d="M13 22H7a5 5 0 1 1 4.9-6H13a3 3 0 0 1 0 6Z"></path>',
  'hard-hat': '<path d="M10 10V5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v5"></path><path d="M14 6a6 6 0 0 1 6 6v3"></path><path d="M4 15v-3a6 6 0 0 1 6-6"></path><rect x="2" y="15" width="20" height="4" rx="1"></rect>',
  'info': '<circle cx="12" cy="12" r="9"></circle><path d="M12 11v6M12 7.5v.5"></path>',
  'user-plus': '<circle cx="9" cy="8" r="3.5"></circle><path d="M3 20c0-3.3 2.7-6 6-6 1.6 0 3 .6 4.1 1.6"></path><path d="M18 14v6M15 17h6"></path>',
  'phone': '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"></path>',
  'site': '<path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"></path><circle cx="12" cy="10" r="2.5"></circle>',
  'smartphone': '<rect x="6" y="2" width="12" height="20" rx="2.5"></rect><path d="M11 18h2"></path>',
  'wind': '<path d="M3 8h11a3 3 0 1 0-3-3"></path><path d="M3 12h15a3 3 0 1 1-3 3"></path><path d="M3 16h7"></path>',
  'rain': '<path d="M7 14h10a4 4 0 0 0 0-8 5.5 5.5 0 0 0-10.6 1.5A3.3 3.3 0 0 0 7 14z"></path><path d="M8 18l-1 2M12 18l-1 2M16 18l-1 2"></path>',
  'thermometer': '<path d="M14 4v10.54a4 4 0 1 1-4 0V4a2 2 0 0 1 4 0Z"></path>',
  'droplet': '<path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7z"></path>',
};
// 글꼴: 앱은 Pretendard인데 Figma에 없어 Gothic A1로 그린다.
const FONT = 'Gothic A1';
await Promise.all(['Regular', 'Medium', 'SemiBold', 'Bold', 'ExtraBold'].map(s => figma.loadFontAsync({family: FONT, style: s})));

const rgb = h => { const n = parseInt(h.slice(1), 16); return {r: (n >> 16 & 255) / 255, g: (n >> 8 & 255) / 255, b: (n & 255) / 255}; };
// 색 변수 컬렉션 "공온 색"을 찾거나 만들고, 토큰 값을 맞춘다.
const V = {};
{
  const cols = await figma.variables.getLocalVariableCollectionsAsync();
  let col = cols.find(c => c.name === '공온 색');
  if (!col) col = figma.variables.createVariableCollection('공온 색');
  const mode = col.modes[0].modeId;
  const have = {};
  for (const id of col.variableIds) { const v = await figma.variables.getVariableByIdAsync(id); have[v.name] = v; }
  for (const [name, hex] of Object.entries(TOKENS)) {
    let v = have[name];
    if (!v) { v = figma.variables.createVariable(name, col, 'COLOR'); v.scopes = ['FRAME_FILL', 'SHAPE_FILL', 'TEXT_FILL', 'STROKE_COLOR']; }
    v.setValueForMode(mode, {...rgb(hex), a: 1});
    V[name.replace('verdict/', '')] = v;
  }
}
// P('accent') = 변수 연결 칠, P('#FFFFFF', 0.5) = 고정 색
const P = (c, o = 1) => c.startsWith('#') ? [{type: 'SOLID', color: rgb(c), opacity: o}] : [figma.variables.setBoundVariableForPaint({type: 'SOLID', color: {r: 0, g: 0, b: 0}}, 'color', V[c])];
function T(s, size, style = 'Regular', color = 'ink', name) { const t = figma.createText(); t.fontName = {family: FONT, style}; t.characters = s; t.fontSize = size; t.fills = P(color); t.lineHeight = {unit: 'PERCENT', value: 140}; if (name) t.name = name; return t; }
function AL(dir, p = {}) { const f = figma.createAutoLayout(dir); f.fills = []; f.set(p); return f; }
function put(parent, child, h, v) { parent.appendChild(child); if (h) child.layoutSizingHorizontal = h; if (v) child.layoutSizingVertical = v; return child; }
function wrapText(parent, t, oneLine) { parent.appendChild(t); t.layoutSizingHorizontal = 'FILL'; t.textAutoResize = 'HEIGHT'; if (oneLine) { t.maxLines = 1; t.textTruncation = 'ENDING'; } return t; }
function icon(name, size, color, sw = 2) { const n = figma.createNodeFromSvg(`<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">${ICONS[name]}</svg>`); n.resize(size, size); n.name = 'icon/' + name; return n; }
function box(size, radius, fill) { const b = AL('HORIZONTAL', {primaryAxisAlignItems: 'CENTER', counterAxisAlignItems: 'CENTER', cornerRadius: radius}); b.resize(size, size); b.primaryAxisSizingMode = 'FIXED'; b.counterAxisSizingMode = 'FIXED'; b.fills = fill; return b; }
function spacer(parent) { const s = figma.createFrame(); s.name = 'spacer'; s.fills = []; put(parent, s, 'FILL'); s.resize(s.width, 1); return s; }
function strokeOnly(n, side, color = 'line-soft') { n.strokes = P(color); n.strokeTopWeight = side === 'top' ? 1 : 0; n.strokeBottomWeight = side === 'bottom' ? 1 : 0; n.strokeLeftWeight = 0; n.strokeRightWeight = 0; }
const shadow = (a = 0.08, y = 4, r = 12) => [{type: 'DROP_SHADOW', color: {r: 0.055, g: 0.118, b: 0.27, a}, offset: {x: 0, y}, radius: r, spread: 0, visible: true, blendMode: 'NORMAL'}];
const grad = (a, b, t = [[0, 1, 0], [-1, 0, 1]]) => [{type: 'GRADIENT_LINEAR', gradientTransform: t, gradientStops: [{position: 0, color: {...rgb(a), a: 1}}, {position: 1, color: {...rgb(b), a: 1}}]}];
const NAVY = [[0.8, 0.6, 0], [-0.6, 0.8, 0.3]];
// 그림 자리: 이름이 img/<파일 이름>인 빈 틀. 실행 뒤 upload_assets로 app/core/static/brand/<파일 이름>.png을 채운다(README).
const IMGS = {};
function img(name, w, h) { const f = figma.createFrame(); f.name = 'img/' + name; f.resize(w, h); f.fills = []; (IMGS[name] ||= []).push(f.id); return f; }

// 페이지: 있으면 그 페이지로, 없으면 만든다(Starter는 파일당 3쪽까지). 한 실행에 한 번만 부른다.
// 새 파일의 빈 "Page 1"은 지우지 않고 이름을 바꿔 쓴다(쪽 수 한도).
async function usePage(name) {
  let p = figma.root.children.find(x => x.name === name);
  if (!p) { const blank = figma.currentPage; p = /^Page \d+$/.test(blank.name) && blank.children.length === 0 ? blank : figma.createPage(); p.name = name; }
  await figma.setCurrentPageAsync(p); return p;
}
// 다른 페이지의 컴포넌트를 이름으로 찾는다(기초 페이지에 둔다).
async function component(name, pageName = '기초') { const p = figma.root.children.find(x => x.name === pageName); await p.loadAsync(); const c = p.findOne(n => (n.type === 'COMPONENT_SET' || n.type === 'COMPONENT') && n.name === name && n.parent.type !== 'COMPONENT_SET'); if (!c) throw new Error('컴포넌트 없음: ' + name + ' — 기초 스크립트를 먼저 실행'); return c; }
const variantOf = (set, prop) => set.children.find(c => c.name === prop);
const propKey = (node, name) => Object.keys((node.type === 'COMPONENT_SET' ? node : (node.parent?.type === 'COMPONENT_SET' ? node.parent : node)).componentPropertyDefinitions).find(k => k.split('#')[0] === name);
// 섹션: 이름으로 찾거나 만든다.
function section(name, x, y) { let s = figma.currentPage.children.find(n => n.type === 'SECTION' && n.name === name); if (!s) { s = figma.createSection(); s.name = name; s.x = x; s.y = y; } return s; }
// 화면을 다시 그릴 때: 같은 이름의 화면을 지우고 그 자리(x, y)를 돌려준다. 처음이면 오른쪽 끝 다음 자리.
function replaceIn(sec, name, gap = 80) { const old = sec.children.find(n => n.name === name); if (old) { const at = {x: old.x, y: old.y}; old.remove(); return at; } const right = Math.max(0, ...sec.children.map(n => n.x + n.width)); return {x: right ? right + gap : 60, y: 80}; }
function fitSection(sec, pad = 80) { const r = Math.max(...sec.children.map(n => n.x + n.width)); const b = Math.max(...sec.children.map(n => n.y + n.height)); sec.resizeWithoutConstraints(r + pad, b + pad); }
const done = {created: [], images: IMGS};
