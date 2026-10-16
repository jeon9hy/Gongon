// 날짜·시간 고르기(C04-4, 개발자 요청). 브라우저 기본 date/time 입력 대신 누르기 쉬운 판을 띄운다.
// - 날짜: 일 → (제목을 누르면) 월 12칸 → 연 12칸. min/max 밖의 날은 누를 수 없다.
// - 시간: 시 24칸 + 분 5분 단위 12칸. 시를 고르면 분이 남고, 분을 고르면 닫힌다.
// 스크립트가 없으면 원래 입력이 그대로 보인다. 값 형식(YYYY-MM-DD, HH:MM)은 서버 검증과 같다.
(() => {
  const DOW = "월화수목금토일";
  const pad = (n) => String(n).padStart(2, "0");
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const parse = (s) => (/^\d{4}-\d{2}-\d{2}$/.test(s || "") ? new Date(s + "T00:00:00") : null);
  const valueDesc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
  let openPop = null;

  const close = () => {
    if (!openPop) return;
    openPop.pop.remove();
    openPop.button.setAttribute("aria-expanded", "false");
    openPop = null;
  };

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const cell = (text, { selected = false, today = false, faded = false, disabled = false, label } = {}) => {
    const b = el("button", "pickpop__cell", text);
    b.type = "button";
    if (selected) b.setAttribute("aria-pressed", "true");
    if (today) b.classList.add("is-today");
    if (faded) b.classList.add("is-faded");
    if (label) b.setAttribute("aria-label", label);
    b.disabled = disabled;
    return b;
  };

  // 버튼 아래(자리가 없으면 위)에 둔다. 모달 안이면 모달 위에 보이도록 모달에 붙인다.
  const place = () => {
    if (!openPop) return;
    const { pop, button } = openPop;
    const r = button.getBoundingClientRect();
    const w = pop.offsetWidth, h = pop.offsetHeight;
    const left = Math.max(8, Math.min(r.left, innerWidth - w - 8));
    const below = r.bottom + 6 + h <= innerHeight - 8 || r.top - 6 - h < 8;
    pop.style.left = `${left}px`;
    pop.style.top = `${below ? r.bottom + 6 : r.top - 6 - h}px`;
  };

  const show = (button, render) => {
    close();
    const pop = el("div", "pickpop");
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-label", button.dataset.title);
    pop.addEventListener("click", (e) => e.stopPropagation());
    (button.closest("dialog") || document.body).append(pop);
    openPop = { pop, button };
    button.setAttribute("aria-expanded", "true");
    render(pop);
    place();
    (pop.querySelector("[aria-pressed=true]") || pop.querySelector(".pickpop__cell:not(:disabled)"))?.focus();
  };

  const head = (title, onPrev, onNext, onTitle) => {
    const h = el("div", "pickpop__head");
    const prev = el("button", "pickpop__nav", "‹");
    prev.type = "button";
    prev.setAttribute("aria-label", "이전");
    prev.addEventListener("click", onPrev);
    const t = el(onTitle ? "button" : "span", "pickpop__title", title);
    if (onTitle) { t.type = "button"; t.addEventListener("click", onTitle); }
    const next = el("button", "pickpop__nav", "›");
    next.type = "button";
    next.setAttribute("aria-label", "다음");
    next.addEventListener("click", onNext);
    h.append(prev, t, next);
    return h;
  };

  // 숨긴 입력의 value를 다른 스크립트가 바꿔도(최근 쓴 시간·복사) 버튼 글자가 따라 바뀌게 한다.
  const enhance = (input, label, renderPop) => {
    const button = el("button", "pickfield");
    button.type = "button";
    button.dataset.title = label;
    button.setAttribute("aria-haspopup", "dialog");
    button.setAttribute("aria-expanded", "false");
    const required = input.required;
    input.type = "hidden";
    input.after(button);
    const commit = (v) => {
      input.value = v;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    };
    const refresh = () => {
      button.textContent = input.dataset.display || "";
      button.classList.toggle("is-empty", !valueDesc.get.call(input));
      if (valueDesc.get.call(input)) button.removeAttribute("aria-invalid");
    };
    Object.defineProperty(input, "value", {
      get: () => valueDesc.get.call(input),
      set: (v) => { valueDesc.set.call(input, v); input.dataset.display = renderPop.text(v); refresh(); },
    });
    input.value = valueDesc.get.call(input);
    button.addEventListener("click", (e) => {
      e.preventDefault(); // 라벨 안 버튼이라 클릭이 다시 버튼으로 오지 않게
      e.stopPropagation();
      if (openPop && openPop.button === button) { close(); return; }
      show(button, (pop) => renderPop.draw(pop, input.value, commit));
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

  const datePop = (input) => ({
    text: (v) => {
      const d = parse(v);
      return d ? `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())} (${DOW[(d.getDay() + 6) % 7]})` : "날짜 고르기";
    },
    draw: (pop, value, commit) => {
      const min = parse(input.min), max = parse(input.max), today = new Date();
      const chosen = parse(value);
      let cursor = new Date((chosen || today).getFullYear(), (chosen || today).getMonth(), 1);
      const monthOut = (y, m) => (min && new Date(y, m + 1, 0) < min) || (max && new Date(y, m, 1) > max);
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
          const b = cell(d.getDate(), {
            selected: chosen && iso(d) === iso(chosen), today: iso(d) === iso(today), faded: d.getMonth() !== m,
            disabled: (min && d < min) || (max && d > max), label: `${d.getMonth() + 1}월 ${d.getDate()}일`,
          });
          b.addEventListener("click", () => { const btn = openPop?.button; commit(iso(d)); close(); btn?.focus(); });
          grid.append(b);
        }
        const foot = el("div", "pickpop__foot");
        const t = el("button", "btn btn--soft btn--sm", "오늘");
        t.type = "button";
        t.disabled = Boolean((min && iso(today) < iso(min)) || (max && iso(today) > iso(max)));
        t.addEventListener("click", () => { commit(iso(today)); close(); });
        foot.append(t);
        pop.append(grid, foot);
        place();
      };
      const months = () => {
        const y = cursor.getFullYear();
        pop.replaceChildren(head(`${y}년`, () => { cursor = new Date(y - 1, cursor.getMonth(), 1); months(); },
          () => { cursor = new Date(y + 1, cursor.getMonth(), 1); months(); }, years));
        const grid = el("div", "pickpop__grid pickpop__grid--wide");
        for (let m = 0; m < 12; m += 1) {
          const b = cell(`${m + 1}월`, {
            selected: m === cursor.getMonth(), today: y === today.getFullYear() && m === today.getMonth(),
            disabled: monthOut(y, m),
          });
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
          const b = cell(y, {
            selected: y === cursor.getFullYear(), today: y === today.getFullYear(), faded: y < base || y > base + 9,
            disabled: (min && y < min.getFullYear()) || (max && y > max.getFullYear()),
          });
          b.addEventListener("click", () => { cursor = new Date(y, cursor.getMonth(), 1); months(); });
          grid.append(b);
        }
        pop.append(grid);
        place();
      };
      days();
    },
  });

  const timePop = {
    text: (v) => (/^\d{2}:\d{2}$/.test(v || "") ? v : "시간 고르기"),
    draw: (pop, value, commit) => {
      let [h, m] = /^\d{2}:\d{2}$/.test(value || "") ? value.split(":").map(Number) : [null, 0];
      const draw = () => {
        pop.replaceChildren();
        const hourHead = el("p", "pickpop__label", "시");
        const hours = el("div", "pickpop__grid pickpop__grid--time");
        for (let i = 0; i < 24; i += 1) {
          const b = cell(pad(i), { selected: i === h, faded: i < 6 || i > 20, label: `${i}시` });
          b.addEventListener("click", () => { h = i; commit(`${pad(h)}:${pad(m)}`); draw(); pop.querySelector(".pickpop__grid--min [aria-pressed=true]")?.focus(); });
          hours.append(b);
        }
        const minHead = el("p", "pickpop__label", "분");
        const mins = el("div", "pickpop__grid pickpop__grid--time pickpop__grid--min");
        for (let i = 0; i < 60; i += 5) {
          const b = cell(pad(i), { selected: h !== null && i === m, disabled: h === null, label: `${i}분` });
          b.addEventListener("click", () => { m = i; commit(`${pad(h)}:${pad(m)}`); const btn = openPop?.button; close(); btn?.focus(); });
          mins.append(b);
        }
        pop.append(hourHead, hours, minHead, mins);
        place();
      };
      draw();
    },
  };

  const labelOf = (input) => (input.closest("label")?.firstChild?.textContent || "").trim() || "고르기";
  document.querySelectorAll('input[type="date"]').forEach((i) => enhance(i, `${labelOf(i)} 날짜`, datePop(i)));
  document.querySelectorAll('input[type="time"]').forEach((i) => enhance(i, `${labelOf(i)} 시간`, timePop));

  document.addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || !openPop) return;
    e.preventDefault(); // 모달 안에서도 판만 닫고 모달은 남긴다
    e.stopPropagation();
    const btn = openPop.button;
    close();
    btn.focus();
  }, true);
  addEventListener("resize", place);
  addEventListener("scroll", place, true);
})();
