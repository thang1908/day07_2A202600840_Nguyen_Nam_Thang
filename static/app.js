const byId = (id) => document.getElementById(id);

const controls = {
  refreshBtn: byId("refreshBtn"),
  buildBtn: byId("buildBtn"),
  queryBtn: byId("queryBtn"),
  chatToggle: byId("chatToggle"),
  chatClose: byId("chatClose"),
  chatWidget: byId("chatWidget"),
  chatForm: byId("chatForm"),
  chatInput: byId("chatInput"),
  chatSendBtn: byId("chatSendBtn"),
  chunkMethod: byId("chunkMethod"),
  chunkSize: byId("chunkSize"),
  overlap: byId("overlap"),
  maxSentences: byId("maxSentences"),
  methodHint: byId("methodHint"),
  question: byId("question"),
  domainFilter: byId("domainFilter"),
  docFilter: byId("docFilter"),
  topK: byId("topK"),
  buildNotice: byId("buildNotice"),
  queryNotice: byId("queryNotice"),
  chatNotice: byId("chatNotice"),
  chatMessages: byId("chatMessages"),
  results: byId("results"),
  embeddingBackend: byId("embeddingBackend"),
  vectorDb: byId("vectorDb"),
  totalChunks: byId("totalChunks"),
  strategy: byId("strategy"),
};

const methodHints = {
  markdown: "Markdown structure uses document headings and only needs a max chunk size for long sections.",
  recursive: "Recursive chunking uses chunk size and splits through paragraph, line, sentence, then word boundaries.",
  fixed: "Fixed size chunking uses chunk size plus overlap to preserve context across adjacent chunks.",
  sentence: "Sentence chunking groups a fixed number of sentences; chunk size and overlap are not used.",
};

function setLoading(button, isLoading, label) {
  button.disabled = isLoading;
  button.textContent = isLoading ? "Working..." : label;
}

function setNotice(node, message, isError = false) {
  node.textContent = message;
  node.classList.toggle("error", isError);
}

function fillSelect(select, placeholder, values) {
  const previous = select.value;
  select.innerHTML = "";

  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = placeholder;
  select.appendChild(empty);

  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });

  if (values.includes(previous)) {
    select.value = previous;
  }
}

function renderStatus(status) {
  controls.embeddingBackend.textContent = status.embedding_backend;
  controls.vectorDb.textContent = status.vector_db;
  controls.totalChunks.textContent = status.total_chunks;
  controls.strategy.textContent = status.chunk_method;

  fillSelect(controls.domainFilter, "All domains", status.domains || []);
  fillSelect(controls.docFilter, "All documents", status.doc_ids || []);
}

function updateChunkSettings() {
  const selected = controls.chunkMethod.value;
  controls.methodHint.textContent = methodHints[selected] || "";

  document.querySelectorAll(".chunk-setting").forEach((setting) => {
    const methods = setting.dataset.methods.split(" ");
    const shouldShow = methods.includes(selected);
    setting.hidden = !shouldShow;

    setting.querySelectorAll("input, select, textarea").forEach((input) => {
      input.disabled = !shouldShow;
    });
  });
}

async function refreshStatus() {
  const response = await fetch("/api/status");
  renderStatus(await response.json());
}

async function buildIndex() {
  setLoading(controls.buildBtn, true, "Build Vector Index");
  setNotice(controls.buildNotice, "Loading, chunking, embedding, and writing vectors...");

  try {
    const response = await fetch("/api/index", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chunk_method: controls.chunkMethod.value,
        chunk_size: Number(controls.chunkSize.value),
        overlap: Number(controls.overlap.value),
        max_sentences: Number(controls.maxSentences.value),
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Indexing failed");
    }

    renderStatus(data);
    setNotice(controls.buildNotice, `Indexed ${data.total_chunks} chunks from ${data.total_files} files.`);
  } catch (error) {
    setNotice(controls.buildNotice, error.message, true);
  } finally {
    setLoading(controls.buildBtn, false, "Build Vector Index");
  }
}

async function queryIndex() {
  setLoading(controls.queryBtn, true, "Search");
  setNotice(controls.queryNotice, "Searching...");
  controls.results.innerHTML = "";

  try {
    const response = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: controls.question.value,
        top_k: Number(controls.topK.value),
        domain: controls.domainFilter.value || null,
        doc_id: controls.docFilter.value || null,
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Search failed");
    }

    setNotice(controls.queryNotice, `${data.results.length} results`);
    renderResults(data.results);
  } catch (error) {
    setNotice(controls.queryNotice, error.message, true);
  } finally {
    setLoading(controls.queryBtn, false, "Search");
  }
}

function toggleChat(forceOpen = null) {
  const shouldOpen = forceOpen === null ? controls.chatWidget.hidden : forceOpen;
  controls.chatWidget.hidden = !shouldOpen;
  controls.chatToggle.setAttribute("aria-expanded", String(shouldOpen));
  if (shouldOpen) {
    controls.chatInput.focus();
  }
}

async function sendChatMessage(event) {
  event.preventDefault();
  const message = controls.chatInput.value.trim();
  if (!message) return;

  addChatMessage("user", message);
  controls.chatInput.value = "";
  setLoading(controls.chatSendBtn, true, "Send");
  setNotice(controls.chatNotice, "Retrieving context and asking the LLM...");

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        top_k: Number(controls.topK.value),
        domain: controls.domainFilter.value || null,
        doc_id: controls.docFilter.value || null,
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Chat failed");
    }

    addChatMessage("assistant", data.answer, data.sources || []);
    setNotice(controls.chatNotice, "");
  } catch (error) {
    addChatMessage("assistant", error.message);
    setNotice(controls.chatNotice, error.message, true);
  } finally {
    setLoading(controls.chatSendBtn, false, "Send");
  }
}

function addChatMessage(role, text, sources = []) {
  const node = document.createElement("div");
  node.className = `chat-message ${role}`;

  const body = document.createElement("div");
  body.textContent = text;
  node.appendChild(body);

  if (sources.length) {
    const sourceList = document.createElement("div");
    sourceList.className = "chat-sources";
    sources.slice(0, 3).forEach((source) => {
      const sourceNode = document.createElement("div");
      sourceNode.className = "chat-source";
      sourceNode.textContent = `#${source.rank} ${source.source || source.doc_id || "source"} · ${source.section_title || ""}`;
      sourceList.appendChild(sourceNode);
    });
    node.appendChild(sourceList);
  }

  controls.chatMessages.appendChild(node);
  controls.chatMessages.scrollTop = controls.chatMessages.scrollHeight;
}

function renderResults(results) {
  controls.results.innerHTML = "";

  if (!results.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No chunks matched this query and filter.";
    controls.results.appendChild(empty);
    return;
  }

  results.forEach((item) => {
    const metadata = item.metadata || {};
    const card = document.createElement("article");
    card.className = "result-card";

    const title = metadata.section_title || metadata.heading_path || metadata.source || "Untitled chunk";
    card.innerHTML = `
      <div class="result-meta">
        <span class="pill">#${item.rank}</span>
        <span class="pill">score ${Number(item.score).toFixed(3)}</span>
        <span class="pill">${escapeHtml(metadata.domain || "no-domain")}</span>
        <span class="pill">${escapeHtml(metadata.doc_id || "no-doc")}</span>
      </div>
      <div class="result-title">${escapeHtml(title)}</div>
      <pre class="result-content"></pre>
    `;

    card.querySelector(".result-content").textContent = item.content;
    controls.results.appendChild(card);
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

controls.refreshBtn.addEventListener("click", refreshStatus);
controls.buildBtn.addEventListener("click", buildIndex);
controls.queryBtn.addEventListener("click", queryIndex);
controls.chunkMethod.addEventListener("change", updateChunkSettings);
controls.chatToggle.addEventListener("click", () => toggleChat());
controls.chatClose.addEventListener("click", () => toggleChat(false));
controls.chatForm.addEventListener("submit", sendChatMessage);

updateChunkSettings();
refreshStatus();
