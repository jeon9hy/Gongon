// 날짜·시간 입력(C04-4·C04-7, 개발자 요청). 스크립트가 없으면 브라우저 기본 입력이 그대로 보인다.
// - 날짜: 입력칸처럼 보이는 버튼 → 일 → (제목) 월 12칸 → 연 12칸. min/max 밖은 누를 수 없다.
// - 시간: 구글 캘린더처럼 직접 치거나(930 → 09:30) 30분 간격 목록에서 고른다.
//   data-after="start"인 종료 칸은 시작 뒤 시각만 보이고 걸리는 시간을 함께 적는다. 시작을 바꾸면 길이를 유지한다.
//   data-min="HH:MM"이면 그 시각까지(같은 분 포함)는 고를 수 없다(오늘 작업은 지금 이후 시작, D-064).
// 값 형식(YYYY-MM-DD, HH:MM)과 서버 검증은 그대로다.
(() => {
  const DOW = "월화수목금토일";
  const pad = (n) => String(n).padStart(2, "0");
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const parseDate = (s) => (/^\d{4}-\d{2}-\d{2}$/.test(s || "") ? new Date(s + "T00:00:00") : null);
  const toMin = (hm) => (/^\d{2}:\d{2}$/.test(hm || "") ? Number(hm.slice(0, 2)) * 60 + Number(hm.slice(3)) : null);
  const toHm = (m) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
  const span = (m) => (m < 60 ? `${m}분` : `${Math.floor(m / 60)}시간${m % 60 ? ` ${m % 60}분` : ""}`);
  const valueDesc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
  let openPop = null;

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const close = () => {
    if (!openPop) return;
    openPop.pop.remove();
    openPop.anchor.setAttribute("aria-expanded", "false");
    openPop = null;
  };
  // 입력칸 아래(자리가 없으면 위)에 띄운다. 모달 안이면 모달 위에 보이도록 모달에 붙인다.
  const place = () => {
    if (!openPop) return;
    const { pop, anchor } = openPop;
    const r = anchor.getBoundingClientRect();
    if (openPop.matchWidth) pop.style.width = `${Math.max(r.width, 180)}px`;
    const w = pop.offsetWidth, h = pop.offsetHeight;
    const left = Math.max(8, Math.min(r.left, innerWidth - w - 8));
    const below = r.bottom + 6 + h <= innerHeight - 8 || r.top - 6 - h < 8;
    pop.style.left = `${left}px`;
    pop.style.top = `${below ? r.bottom + 4 : r.top - 4 - h}px`;
  };
  const show = (anchor, cls, render, matchWidth = false) => {
    close();
    const pop = el("div", `pickpop ${cls}`);
    pop.addEventListener("mousedown", (e) => e.preventDefault()); // 입력칸 포커스를 잃지 않게
    pop.addEventListener("click", (e) => e.stopPropagation());
    (anchor.closest("dialog") || document.body).append(pop);
    openPop = { pop, anchor, matchWidth };
    anchor.setAttribute("aria-expanded", "true");
    render(pop);
    place();
    return pop;
  };
  const fire = (input) => {
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  };

  // ---------- 날짜 ----------
  const cell = (text, { selected = false, today = false, faded = false, disabled = false, label } = {}) => {
    const b = el("button", "pickpop__cell", text);
    b.type = "button";
    if (selected) b.setAttribute("aria-pressed", "true");
    if (today) b.classList.add("is-today");
    if (faded) b.classList.add("is-faded");
    if (label) b.setAttribute("aria-label", label);
    b.disabled = Boolean(disabled);
    return b;
  };
  const head = (title, onPrev, onNext, onTitle) => {
    const h = el("div", "pickpop__head");
    const mk = (txt, label, fn) => { const b = el("button", "pickpop__nav", txt); b.type = "button"; b.setAttribute("aria-label", label); b.addEventListener("click", fn); return b; };
    const t = el(onTitle ? "button" : "span", "pickpop__title", title);
    if (onTitle) { t.type = "button"; t.addEventListener("click", onTitle); }
    h.append(mk("‹", "이전", onPrev), t, mk("›", "다음", onNext));
    return h;
  };
  const dateText = (v) => {
    const d = parseDate(v);
    return d ? `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())} (${DOW[(d.getDay() + 6) % 7]})` : "날짜 고르기";
  };
  const drawDate = (pop, input, commit) => {
    const min = parseDate(input.min), max = parseDate(input.max), today = new Date();
    const chosen = parseDate(input.value);
    let cursor = new Date((chosen || today).getFullYear(), (chosen || today).getMonth(), 1);
    const days = () => {
      const y = cursor.getFullYear(), m = cursor.getMonth();
      pop.replaceChildren(head(`${y}년 ${m + 1}월`, () => { cursor = new Date(y, m - 1, 1); days(); },
        () => { cursor = new Date(y, m + 1, 1); days(); }, months));
      const grid = el("div", "pickpop__grid pickpop__grid--days");
      for (const w of DOW) grid.append(el("span", "pickpop__dow", w));
      const start = new Date(y, m, 1 - ((new Date(y, m, 1).getDay() + 6) % 7));
      for (let i = 0; i < 42; i += 1) {
        const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i);
        if (i >= 35 && d.getMonth() !== m) break;
        const b = cell(d.getDate(), { selected: chosen && iso(d) === iso(chosen), today: iso(d) === iso(today),
          faded: d.getMonth() !== m, disabled: (min && d < min) || (max && d > max), label: `${d.getMonth() + 1}월 ${d.getDate()}일` });
        b.addEventListener("click", () => { commit(iso(d)); close(); });
        grid.append(b);
      }
      pop.append(grid);
      place();
    };
    const months = () => {
      const y = cursor.getFullYear();
      pop.replaceChildren(head(`${y}년`, () => { cursor = new Date(y - 1, cursor.getMonth(), 1); months(); },
        () => { cursor = new Date(y + 1, cursor.getMonth(), 1); months(); }, years));
      const grid = el("div", "pickpop__grid pickpop__grid--wide");
      for (let m = 0; m < 12; m += 1) {
        const b = cell(`${m + 1}월`, { selected: m === cursor.getMonth(), today: y === today.getFullYear() && m === today.getMonth(),
          disabled: (min && new Date(y, m + 1, 0) < min) || (max && new Date(y, m, 1) > max) });
        b.addEventListener("click", () => { cursor = new Date(y, m, 1); days(); });
        grid.append(b);
      }
      pop.append(grid);
      place();
    };
    const years = () => {
      const base = Math.floor(cursor.getFullYear() / 10) * 10;
      pop.replaceChildren(head(`${base} – ${base + 9}`, () => { cursor = new Date(base - 10, cursor.getMonth(), 1); years(); },
        () => { cursor = new Date(base + 10, cursor.getMonth(), 1); years(); }));
      const grid = el("div", "pickpop__grid pickpop__grid--wide");
      for (let y = base - 1; y <= base + 10; y += 1) {
        const b = cell(y, { selected: y === cursor.getFullYear(), today: y === today.getFullYear(), faded: y < base || y > base + 9,
          disabled: (min && y < min.getFullYear()) || (max && y > max.getFullYear()) });
        b.addEventListener("click", () => { cursor = new Date(y, cursor.getMonth(), 1); months(); });
        grid.append(b);
      }
      pop.append(grid);
      place();
    };
    days();
  };
  const enhanceDate = (input) => {
    const button = el("button", "pickfield");
    button.type = "button";
    button.setAttribute("aria-haspopup", "dialog");
    button.setAttribute("aria-expanded", "false");
    const required = input.required;
    input.type = "hidden";
    input.after(button);
    const refresh = () => {
      const v = valueDesc.get.call(input);
      button.textContent = dateText(v);
      button.classList.toggle("is-empty", !v);
      if (v) button.removeAttribute("aria-invalid");
    };
    // 다른 스크립트가 value를 바꿔도(복사 등) 버튼 글자가 따라 바뀌게 한다.
    Object.defineProperty(input, "value", { get: () => valueDesc.get.call(input), set: (v) => { valueDesc.set.call(input, v); refresh(); } });
    refresh();
    button.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (openPop && openPop.anchor === button) { close(); return; }
      show(button, "pickpop--date", (pop) => drawDate(pop, input, (v) => { input.value = v; fire(input); button.focus(); }));
    });
    if (required && input.form) {
      input.form.addEventListener("submit", (e) => {
        if (input.value || input.closest("[hidden]")) return;
        e.preventDefault();
        button.setAttribute("aria-invalid", "true");
        button.click();
      });
    }
  };

  // ---------- 시간 ----------
  // "9" → 09:00, "930" → 09:30, "9:5" → 09:05, "17.30" → 17:30. 못 읽으면 null.
  const parseTime = (raw) => {
    const s = (raw || "").trim().replace(/[.\s시분]/g, ":").replace(/:+$/, "");
    let h, m;
    if (/^\d{1,2}$/.test(s)) { h = Number(s); m = 0; }
    else if (/^\d{3,4}$/.test(s)) { h = Number(s.slice(0, -2)); m = Number(s.slice(-2)); }
    else if (/^\d{1,2}:\d{1,2}$/.test(s)) { [h, m] = s.split(":").map(Number); }
    else return null;
    return h < 24 && m < 60 ? toHm(h * 60 + m) : null;
  };
  const enhanceTime = (input) => {
    input.type = "text";
    input.inputMode = "numeric";
    input.autocomplete = "off";
    input.placeholder = input.placeholder || "09:00";
    input.maxLength = 5;
    input.classList.add("timefield");
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-autocomplete", "list");
    const form = input.form;
    const startOf = () => (input.dataset.after && form ? form.elements[input.dataset.after] : null);
    const floor = () => {
      const start = startOf();
      return { after: start ? toMin(start.value) : null, min: toMin(input.dataset.min || "") };
    };
    const allowed = (m) => {
      const { after, min } = floor();
      return (after === null || m > after) && (min === null || m > min);
    };
    const set = (hm) => {
      input.value = hm;
      input.removeAttribute("aria-invalid");
      fire(input);
    };
    const render = () => {
      show(input, "pickpop--time", (pop) => {
        pop.setAttribute("role", "listbox");
        const { after } = floor();
        const current = toMin(input.value);
        let focusTarget = null;
        const from = after === null ? 0 : Math.ceil((after + 1) / 30) * 30;
        for (let m = from; m < 24 * 60; m += 30) {
          const b = el("button", "timeopt");
          b.type = "button";
          b.setAttribute("role", "option");
          b.append(el("span", "timeopt__hm", toHm(m)));
          if (after !== null) b.append(el("span", "timeopt__span", span(m - after)));
          b.disabled = !allowed(m);
          if (current === m) { b.setAttribute("aria-selected", "true"); focusTarget = b; }
          b.addEventListener("click", () => { set(toHm(m)); close(); });
          pop.append(b);
        }
        // 고른 값이 없으면 오전 8시(또는 처음 고를 수 있는 시각) 근처를 보여 준다
        const opts = [...pop.children];
        const fallback = opts.find((b) => !b.disabled && b.firstChild.textContent >= "08:00") || opts.find((b) => !b.disabled);
        requestAnimationFrame(() => {
          const target = focusTarget || fallback;
          if (target) pop.scrollTop = target.offsetTop - pop.clientHeight / 2 + target.offsetHeight / 2;
        });
      }, true);
    };
    const normalize = () => {
      if (!input.value.trim()) return;
      const hm = parseTime(input.value);
      if (hm && allowed(toMin(hm))) { if (hm !== input.value) set(hm); else input.removeAttribute("aria-invalid"); }
      else input.setAttribute("aria-invalid", "true");
    };
    let previous = input.value;
    input.addEventListener("focus", render);
    input.addEventListener("click", (e) => { e.stopPropagation(); if (!openPop || openPop.anchor !== input) render(); });
    input.addEventListener("blur", () => {
      normalize();
      if (openPop && openPop.anchor === input) close();
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); normalize(); close(); return; }
      if (e.key === "Tab") { close(); return; }
      if (!openPop || openPop.anchor !== input || !["ArrowDown", "ArrowUp"].includes(e.key)) return;
      e.preventDefault();
      const opts = [...openPop.pop.querySelectorAll(".timeopt:not(:disabled)")];
      const i = opts.findIndex((o) => o.classList.contains("is-active"));
      const next = opts[Math.max(0, Math.min(opts.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
      opts.forEach((o) => o.classList.toggle("is-active", o === next));
      if (next) { next.scrollIntoView({ block: "nearest" }); input.value = next.firstChild.textContent; }
    });
    // 시작이 바뀌면 종료를 같은 길이만큼 옮긴다(구글 캘린더와 같다). 길이를 모르면 그대로 둔다.
    if (!input.dataset.after) {
      input.addEventListener("change", () => {
        const ends = form ? [...form.querySelectorAll(`[data-after="${input.name}"]`)] : [];
        const before = toMin(previous), now = toMin(input.value);
        ends.forEach((end) => {
          const e = toMin(end.value);
          if (before !== null && now !== null && e !== null && e > before && now + (e - before) < 24 * 60) {
            end.value = toHm(now + (e - before));
            end.dispatchEvent(new Event("input", { bubbles: true }));
          }
        });
        previous = input.value;
      });
    }
  };

  const enhance = (root = document) => {
    root.querySelectorAll('input[type="date"]').forEach(enhanceDate);
    root.querySelectorAll('input[type="time"]').forEach(enhanceTime);
  };
  window.gongonPick = { enhance, parseTime, close };
  enhance();

  document.addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || !openPop) return;
    e.preventDefault(); // 모달 안에서도 판만 닫고 모달은 남긴다
    e.stopPropagation();
    const anchor = openPop.anchor;
    close();
    anchor.focus();
  }, true);
  addEventListener("resize", place);
  addEventListener("scroll", (e) => { if (!openPop || !openPop.pop.contains(e.target)) place(); }, true);
})();
