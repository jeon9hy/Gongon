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
  form.addEventListener("submit", async (e) => {
    if (!input.value.trim()) return;
    e.preventDefault();
    const res = await fetch(form.action, { method: "POST", body: new FormData(form) });
    if (res.ok || res.redirected) { input.value = ""; form.case_id.value = ""; input.style.height = ""; await poll(); toBottom(); }
    else { form.submit(); }
  });
  input.addEventListener("keydown", (e) => {
    // 앱 화면은 카톡처럼 Enter가 줄바꿈이고 보내기 버튼으로 보낸다
    if (document.documentElement.dataset.ui === "app") return;
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
  });
  input.addEventListener("input", () => { input.style.height = ""; input.style.height = Math.min(input.scrollHeight, 160) + "px"; });
})();
