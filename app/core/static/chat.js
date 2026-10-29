// 현장 대화방(C12): 날짜 구분선, 4초마다 새 메시지 불러오기, 화면을 다시 그리지 않고 보내기.
// 웹·앱 대화방이 같이 쓴다. 스크립트가 없으면 일반 폼 전송으로 동작한다.
(() => {
  const list = document.querySelector("[data-chat-list]");
  const scroller = document.querySelector("[data-chat-scroll]");
  const form = document.querySelector("[data-chat-form]");
  const input = document.querySelector("[data-chat-input]");
  if (!list) return;
  const site = list.dataset.site;
  const toBottom = () => { scroller.scrollTop = scroller.scrollHeight; };
  // 날짜가 바뀌는 곳에 구분선을 넣는다
  const dividers = () => {
    list.querySelectorAll(".msgs__day").forEach((d) => d.remove());
    let prev = "";
    list.querySelectorAll(".msg").forEach((m) => {
      if (m.dataset.day !== prev) {
        const li = document.createElement("li");
        li.className = "msgs__day";
        li.textContent = m.dataset.day;
        m.before(li);
        prev = m.dataset.day;
      }
    });
  };
  dividers();
  toBottom();
  // 사진은 늦게 그려져 높이가 바뀐다. 맨 아래를 보던 중이면 다 그린 뒤 다시 맨 아래로
  list.addEventListener("load", (e) => {
    if (e.target.tagName !== "IMG") return;
    if (scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < e.target.height + 160) toBottom();
  }, true);
  let busy = false;
  const poll = async () => {
    if (busy || document.hidden) return;
    busy = true;
    try {
      const res = await fetch(`/chat/${site}/messages?after=${list.dataset.last}`, { headers: { Accept: "text/html" } });
      if (res.ok) {
        const html = (await res.text()).trim();
        if (html) {
          const near = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 120;
          const tmp = document.createElement("ol");
          tmp.innerHTML = html;
          const items = [...tmp.querySelectorAll(".msg")];
          items.forEach((li) => { if (!list.querySelector(`[data-id="${li.dataset.id}"]`)) list.append(li); });
          if (items.length) { list.dataset.last = items[items.length - 1].dataset.id; document.querySelector("[data-chat-empty]")?.remove(); }
          dividers();
          if (near) toBottom();
        }
      }
    } finally { busy = false; }
  };
  setInterval(poll, 4000);
  document.addEventListener("visibilitychange", poll);
  // 보내기: 화면을 다시 그리지 않고 보낸 뒤 새 메시지를 불러온다(스크립트가 없으면 일반 전송)
  // 첨부(D-111): + 메뉴에서 사진·연락처·변경 건·조치 중 하나. 고른 것은 입력칸 위 알약으로 보인다
  const box = form.querySelector("[data-attach]");
  const panel = form.querySelector("[data-attach-panel]");
  const opener = form.querySelector("[data-attach-open]");
  const photo = form.querySelector("[data-attach-photo]");
  const chip = form.querySelector("[data-attach-chip]");
  const fields = [...form.querySelectorAll("[data-attach-field]")];
  const showPanel = (open) => {
    panel.hidden = !open;
    opener.setAttribute("aria-expanded", String(open));
    form.querySelector("[data-attach-menu]").hidden = false;
    form.querySelectorAll("[data-attach-list]").forEach((l) => { l.hidden = true; });
  };
  const clearAttach = () => {
    fields.forEach((f) => { f.value = ""; });
    photo.value = "";
    chip.hidden = true;
  };
  const setChip = (text) => {
    form.querySelector("[data-attach-chip-text]").textContent = text;
    chip.hidden = false;
    showPanel(false);
  };
  const hasAttach = () => !!photo.files.length || fields.some((f) => f.value);
  opener.addEventListener("click", () => showPanel(panel.hidden));
  box.addEventListener("click", (e) => {
    const pick = e.target.closest("[data-attach-pick]");
    if (pick) {
      form.querySelector("[data-attach-menu]").hidden = true;
      form.querySelector(`[data-attach-list="${pick.dataset.attachPick}"]`).hidden = false;
      return;
    }
    if (e.target.closest("[data-attach-back]")) { showPanel(true); return; }
    const choice = e.target.closest("[data-attach-value]");
    if (choice) {
      const kind = choice.closest("[data-attach-list]").dataset.attachList;
      clearAttach();
      form.querySelector(`[data-attach-field="${kind}"]`).value = choice.dataset.attachValue;
      setChip(`${{ contact: "연락처", case: "변경 건", action: "조치" }[kind]} · ${choice.dataset.attachLabel}`);
    }
  });
  photo.addEventListener("change", () => {
    if (!photo.files.length) return;
    const file = photo.files[0];
    fields.forEach((f) => { f.value = ""; });
    setChip(`사진 · ${file.name}`);
  });
  form.querySelector("[data-attach-clear]").addEventListener("click", clearAttach);
  document.addEventListener("click", (e) => { if (!box.contains(e.target)) showPanel(false); });
  // 보내기: 글이나 첨부가 있을 때만. 화면을 다시 그리지 않고 보낸 뒤 새 메시지를 불러온다
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!input.value.trim() && !hasAttach()) return;
    const res = await fetch(form.action, { method: "POST", body: new FormData(form) });
    // 보내면 서버가 방으로 돌려보낸다(303). 아니면 오류 문구가 보이게 일반 전송으로 다시 보낸다
    if (res.redirected) { input.value = ""; clearAttach(); input.style.height = ""; await poll(); toBottom(); }
    else { form.submit(); }
  });
  input.addEventListener("keydown", (e) => {
    // 앱 화면은 카톡처럼 Enter가 줄바꿈이고 보내기 버튼으로 보낸다
    if (document.documentElement.dataset.ui === "app") return;
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
  });
  input.addEventListener("input", () => { input.style.height = ""; input.style.height = Math.min(input.scrollHeight, 160) + "px"; });
})();
