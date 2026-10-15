const DEFAULT_MODEL = "qwen2.5-coder:7b";

const DEFAULT_SYSTEM = `You are a senior cybersecurity expert specializing in ethical red teaming and authorized penetration testing.

Mission:
- Think like an attacker to find weaknesses in systems the user is authorized to assess.
- Always frame work as ethical hacking / authorized security assessment.
- Be direct, technical, and thorough.
- Pair every offensive insight with remediation and detection guidance.
- Prefer conceptual methodology, checklists, and defensive validation over ready-to-run exploit payloads or malware.
- Assume the user owns the target or has explicit written authorization unless they clearly say otherwise.
- If a request is clearly for unauthorized intrusion against a third party, refuse actionable attack help and offer only high-level defensive education.

Tools you can use:
- write_file / read_file / list_files — create and manage projects inside the local files/ workspace.
- search_web — search the internet when asked.
- remember / forget / list_memory — lasting memory across chats. Save important durable facts when asked or when clearly useful.

Style:
- Red-team mindset for impact analysis.
- Blue-team mindset for fixes and monitoring.
- Clear structure: finding → why it matters → how to validate safely → how to remediate.

Stay professional and ethical.`;

const els = {
  status: document.getElementById("status"),
  model: document.getElementById("model"),
  system: document.getElementById("system"),
  messages: document.getElementById("messages"),
  activity: document.getElementById("activity"),
  form: document.getElementById("composer"),
  input: document.getElementById("input"),
  send: document.getElementById("send"),
  stop: document.getElementById("stop"),
  chatTitle: document.getElementById("chatTitle"),
  chatList: document.getElementById("chatList"),
  newChat: document.getElementById("newChat"),
  deleteChat: document.getElementById("deleteChat"),
  openSettings: document.getElementById("openSettings"),
  closeSettings: document.getElementById("closeSettings"),
  settingsModal: document.getElementById("settingsModal"),
  saveSettings: document.getElementById("saveSettings"),
  resetPrompt: document.getElementById("resetPrompt"),
  openFiles: document.getElementById("openFiles"),
  closeFiles: document.getElementById("closeFiles"),
  filesModal: document.getElementById("filesModal"),
  filesList: document.getElementById("filesList"),
  filesCount: document.getElementById("filesCount"),
  refreshFiles: document.getElementById("refreshFiles"),
  openMemory: document.getElementById("openMemory"),
  closeMemory: document.getElementById("closeMemory"),
  memoryModal: document.getElementById("memoryModal"),
  memoryList: document.getElementById("memoryList"),
  memoryForm: document.getElementById("memoryForm"),
  memoryInput: document.getElementById("memoryInput"),
};

let history = [];
let currentChatId = null;
let busy = false;
let abortController = null;
let savedModel = DEFAULT_MODEL;

function loadSettings() {
  savedModel = localStorage.getItem("rtc_model") || DEFAULT_MODEL;
  els.system.value = localStorage.getItem("rtc_system") || DEFAULT_SYSTEM;
  currentChatId = localStorage.getItem("rtc_chat_id") || null;
}

function saveSettings() {
  savedModel = els.model.value || savedModel || DEFAULT_MODEL;
  localStorage.setItem("rtc_model", savedModel);
  localStorage.setItem("rtc_system", els.system.value);
}

function setCurrentChatId(id) {
  currentChatId = id;
  if (id) localStorage.setItem("rtc_chat_id", id);
  else localStorage.removeItem("rtc_chat_id");
}

function showEmpty() {
  els.messages.innerHTML = "";
  const empty = document.createElement("div");
  empty.className = "msg empty";
  empty.innerHTML =
    "<strong>Red Team Console</strong>New chat ready. History is on the left. Use Memory for lasting facts across chats.";
  els.messages.appendChild(empty);
}

function renderHistory() {
  els.messages.innerHTML = "";
  if (!history.length) {
    showEmpty();
    return;
  }
  for (const m of history) {
    if (m.role === "tool-note") appendBubble("tool-note", m.content, false, "Tool");
    else appendBubble(m.role, m.content, false);
  }
}

function appendBubble(role, content, animate = true, roleLabel) {
  if (els.messages.querySelector(".empty")) els.messages.innerHTML = "";
  const div = document.createElement("div");
  div.className = `msg ${role === "tool-note" ? "tool-note" : role}`;
  if (!animate) div.style.animation = "none";
  const label = document.createElement("span");
  label.className = "role";
  label.textContent =
    roleLabel ||
    (role === "user" ? "You" : role === "tool-note" ? "Tool" : "Assistant");
  const body = document.createElement("div");
  body.className = "body";
  body.textContent = content;
  div.append(label, body);
  els.messages.appendChild(div);
  els.messages.scrollTop = els.messages.scrollHeight;
  return body;
}

function fillModels(models, preferred) {
  const list = Array.isArray(models) ? [...models] : [];
  list.sort((a, b) => a.localeCompare(b));
  els.model.innerHTML = "";
  if (!list.length) {
    const opt = document.createElement("option");
    opt.value = preferred || DEFAULT_MODEL;
    opt.textContent = preferred || DEFAULT_MODEL;
    els.model.appendChild(opt);
    els.model.value = opt.value;
    return;
  }
  for (const name of list) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    els.model.appendChild(opt);
  }
  els.model.value = list.includes(preferred) ? preferred : list[0];
  savedModel = els.model.value;
}

function setBusy(state) {
  busy = state;
  els.send.disabled = state;
  els.stop.hidden = !state;
  if (!state) {
    els.activity.hidden = true;
    els.activity.textContent = "";
  }
}

function setActivity(text) {
  if (!text) {
    els.activity.hidden = true;
    els.activity.textContent = "";
    return;
  }
  els.activity.hidden = false;
  els.activity.textContent = text;
}

function openModal(el) {
  el.hidden = false;
}
function closeModal(el) {
  el.hidden = true;
}

async function checkHealth() {
  try {
    const r = await fetch("/api/health");
    const data = await r.json();
    if (data.ok) {
      els.status.textContent = `Ollama · ${data.models?.length || 0} models`;
      els.status.className = "status ok";
      fillModels(data.models || [], savedModel);
    } else {
      els.status.textContent = "Ollama offline";
      els.status.className = "status bad";
      fillModels([], savedModel);
    }
  } catch {
    els.status.textContent = "Server unreachable";
    els.status.className = "status bad";
  }
}

async function refreshFiles() {
  try {
    const r = await fetch("/api/files");
    const data = await r.json();
    const entries = data.entries || [];
    els.filesCount.textContent = `${entries.length} item(s)`;
    els.filesList.innerHTML = "";
    if (!entries.length) {
      const li = document.createElement("li");
      li.className = "empty-files";
      li.textContent = "Empty — ask the model to create a project.";
      els.filesList.appendChild(li);
      return;
    }
    for (const entry of entries) {
      const li = document.createElement("li");
      li.textContent = entry;
      els.filesList.appendChild(li);
    }
  } catch {
    els.filesCount.textContent = "Failed to load";
  }
}

async function refreshChatList() {
  const r = await fetch("/api/chats");
  const data = await r.json();
  const chats = data.chats || [];
  els.chatList.innerHTML = "";
  if (!chats.length) {
    const li = document.createElement("li");
    li.innerHTML = '<span class="hint" style="padding:0.4rem">No chats yet</span>';
    els.chatList.appendChild(li);
    return;
  }
  for (const chat of chats) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chat-item" + (chat.id === currentChatId ? " active" : "");
    btn.textContent = chat.title || "Untitled";
    btn.title = chat.title || "Untitled";
    btn.addEventListener("click", () => loadChat(chat.id));
    li.appendChild(btn);
    els.chatList.appendChild(li);
  }
}

async function ensureChat() {
  if (currentChatId) return currentChatId;
  const r = await fetch("/api/chats", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "New chat", messages: [] }),
  });
  const chat = await r.json();
  setCurrentChatId(chat.id);
  els.chatTitle.textContent = chat.title || "New chat";
  await refreshChatList();
  return chat.id;
}

async function persistChat() {
  if (!currentChatId) await ensureChat();
  const r = await fetch(`/api/chats/${currentChatId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages: history }),
  });
  const chat = await r.json();
  els.chatTitle.textContent = chat.title || "Chat";
  await refreshChatList();
}

async function loadChat(id) {
  if (busy) return;
  const r = await fetch(`/api/chats/${id}`);
  if (!r.ok) return;
  const chat = await r.json();
  setCurrentChatId(chat.id);
  history = chat.messages || [];
  els.chatTitle.textContent = chat.title || "Chat";
  renderHistory();
  await refreshChatList();
}

async function createNewChat() {
  if (busy) return;
  const r = await fetch("/api/chats", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "New chat", messages: [] }),
  });
  const chat = await r.json();
  setCurrentChatId(chat.id);
  history = [];
  els.chatTitle.textContent = "New chat";
  showEmpty();
  await refreshChatList();
  els.input.focus();
}

async function deleteCurrentChat() {
  if (!currentChatId || busy) return;
  if (!confirm("Delete this chat?")) return;
  await fetch(`/api/chats/${currentChatId}`, { method: "DELETE" });
  setCurrentChatId(null);
  history = [];
  const list = await (await fetch("/api/chats")).json();
  const chats = list.chats || [];
  if (chats.length) {
    await loadChat(chats[0].id);
  } else {
    await createNewChat();
  }
}

async function refreshMemory() {
  const r = await fetch("/api/memory");
  const data = await r.json();
  const items = data.items || [];
  els.memoryList.innerHTML = "";
  if (!items.length) {
    const li = document.createElement("li");
    li.className = "empty-mem";
    li.textContent = "No memories yet. Add one, or ask the model to remember something.";
    els.memoryList.appendChild(li);
    return;
  }
  for (const item of items) {
    const li = document.createElement("li");
    const text = document.createElement("span");
    text.textContent = item.text;
    const del = document.createElement("button");
    del.type = "button";
    del.className = "ghost compact danger";
    del.textContent = "Forget";
    del.addEventListener("click", async () => {
      await fetch(`/api/memory/${item.id}`, { method: "DELETE" });
      refreshMemory();
    });
    li.append(text, del);
    els.memoryList.appendChild(li);
  }
}

async function bootstrap() {
  loadSettings();
  await checkHealth();
  await refreshChatList();

  // migrate old single localStorage history once
  const legacy = localStorage.getItem("rtc_history");
  if (legacy && !(await (await fetch("/api/chats")).json()).chats?.length) {
    try {
      const msgs = JSON.parse(legacy);
      if (Array.isArray(msgs) && msgs.length) {
        const r = await fetch("/api/chats", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: "Imported chat", messages: msgs }),
        });
        const chat = await r.json();
        setCurrentChatId(chat.id);
        localStorage.removeItem("rtc_history");
      }
    } catch {
      /* ignore */
    }
  }

  if (currentChatId) {
    const r = await fetch(`/api/chats/${currentChatId}`);
    if (r.ok) {
      await loadChat(currentChatId);
      return;
    }
  }
  const list = await (await fetch("/api/chats")).json();
  if (list.chats?.length) await loadChat(list.chats[0].id);
  else await createNewChat();
}

async function sendMessage(text) {
  if (busy) return;
  setBusy(true);
  abortController = new AbortController();
  await ensureChat();

  history.push({ role: "user", content: text });
  appendBubble("user", text);
  await persistChat();

  const assistantBody = appendBubble("assistant", "");
  let full = "";

  const messages = [
    { role: "system", content: els.system.value.trim() || DEFAULT_SYSTEM },
    ...history.filter((m) => m.role === "user" || m.role === "assistant"),
  ];

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: abortController.signal,
      body: JSON.stringify({
        model: savedModel || DEFAULT_MODEL,
        messages,
        stream: true,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() || "";

      for (const chunk of chunks) {
        const line = chunk.trim();
        if (!line.startsWith("data:")) continue;
        const data = line.slice(5).trim();
        if (!data || data === "[DONE]") continue;
        let parsed;
        try {
          parsed = JSON.parse(data);
        } catch {
          continue;
        }

        if (parsed.type === "status") {
          setActivity(parsed.text || "");
        } else if (parsed.type === "tool") {
          const note = `Using ${parsed.name}${parsed.args?.path ? ` → ${parsed.args.path}` : ""}${parsed.args?.query ? ` → ${parsed.args.query}` : ""}${parsed.args?.text ? ` → ${parsed.args.text}` : ""}`;
          appendBubble("tool-note", note, true, "Tool");
          history.push({ role: "tool-note", content: note });
          setActivity(`Tool: ${parsed.name}`);
        } else if (parsed.type === "file_written") {
          setActivity(`Wrote files/${parsed.path}`);
        } else if (parsed.type === "memory_updated") {
          setActivity("Memory updated");
        } else if (parsed.type === "token") {
          full += parsed.content || "";
          assistantBody.textContent = full;
          els.messages.scrollTop = els.messages.scrollHeight;
        } else if (parsed.type === "error") {
          throw new Error(parsed.error || "Unknown error");
        }
      }
    }

    if (!full) full = "(no response — check that the selected Ollama model supports tools)";
    assistantBody.textContent = full;
    history.push({ role: "assistant", content: full });
    await persistChat();
    refreshFiles();
  } catch (err) {
    if (err.name === "AbortError") {
      const stopped = `${full}\n\n[stopped]`.trim();
      assistantBody.textContent = stopped;
      history.push({ role: "assistant", content: stopped });
      await persistChat();
    } else {
      const msg = `Error: ${err.message}`;
      assistantBody.textContent = msg;
      history.push({ role: "assistant", content: msg });
      await persistChat();
    }
  } finally {
    abortController = null;
    setBusy(false);
    els.input.focus();
  }
}

els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = els.input.value.trim();
  if (!text) return;
  els.input.value = "";
  sendMessage(text);
});

els.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    els.form.requestSubmit();
  }
});

els.stop.addEventListener("click", () => {
  if (abortController) abortController.abort();
});

els.newChat.addEventListener("click", createNewChat);
els.deleteChat.addEventListener("click", deleteCurrentChat);

els.openSettings.addEventListener("click", async () => {
  await checkHealth();
  els.model.value = savedModel;
  openModal(els.settingsModal);
});
els.closeSettings.addEventListener("click", () => closeModal(els.settingsModal));
els.saveSettings.addEventListener("click", () => {
  saveSettings();
  closeModal(els.settingsModal);
});
els.resetPrompt.addEventListener("click", () => {
  els.system.value = DEFAULT_SYSTEM;
});

els.openFiles.addEventListener("click", async () => {
  await refreshFiles();
  openModal(els.filesModal);
});
els.closeFiles.addEventListener("click", () => closeModal(els.filesModal));
els.refreshFiles.addEventListener("click", refreshFiles);

els.openMemory.addEventListener("click", async () => {
  await refreshMemory();
  openModal(els.memoryModal);
});
els.closeMemory.addEventListener("click", () => closeModal(els.memoryModal));
els.memoryForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = els.memoryInput.value.trim();
  if (!text) return;
  await fetch("/api/memory", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  els.memoryInput.value = "";
  refreshMemory();
});

els.settingsModal.addEventListener("click", (e) => {
  if (e.target === els.settingsModal) closeModal(els.settingsModal);
});
els.filesModal.addEventListener("click", (e) => {
  if (e.target === els.filesModal) closeModal(els.filesModal);
});
els.memoryModal.addEventListener("click", (e) => {
  if (e.target === els.memoryModal) closeModal(els.memoryModal);
});

bootstrap();
setInterval(checkHealth, 20000);
