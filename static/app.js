// --- State ---
let uploadedFile = null;
let originalWidth = 0;
let originalHeight = 0;
let presets = [];
let recentRefreshTimer = null;

// --- DOM refs ---
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const previewContainer = document.getElementById("preview-container");
const previewImg = document.getElementById("preview-img");
const imgDims = document.getElementById("img-dims");
const clearUpload = document.getElementById("clear-upload");
const presetList = document.getElementById("preset-list");
const savePreset = document.getElementById("save-preset");
const deletePreset = document.getElementById("delete-preset");
const promptEl = document.getElementById("prompt");
const countEl = document.getElementById("count");
const generateBtn = document.getElementById("generate-btn");
const resultsGrid = document.getElementById("results-grid");
const queueStatus = document.getElementById("queue-status");
const refreshRecentBtn = document.getElementById("refresh-recent");
const modal = document.getElementById("modal");
const modalImg = document.getElementById("modal-img");
const modalDownload = document.getElementById("modal-download");
const modalClose = document.getElementById("modal-close");
const customDims = document.getElementById("custom-dims");
const customW = document.getElementById("custom-w");
const customH = document.getElementById("custom-h");

// --- Upload ---
dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.classList.add("drag-over"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => { if (fileInput.files.length) handleFile(fileInput.files[0]); });

clearUpload.addEventListener("click", () => {
  uploadedFile = null;
  originalWidth = 0;
  originalHeight = 0;
  previewContainer.hidden = true;
  dropZone.hidden = false;
  fileInput.value = "";
});

function handleFile(file) {
  if (!file.type.startsWith("image/")) return;
  uploadedFile = file;
  const url = URL.createObjectURL(file);
  previewImg.src = url;
  const img = new Image();
  img.onload = () => {
    originalWidth = img.naturalWidth;
    originalHeight = img.naturalHeight;
    imgDims.textContent = `${originalWidth} x ${originalHeight}`;
  };
  img.src = url;
  previewContainer.hidden = false;
  dropZone.hidden = true;
}

// --- Dimensions ---
document.querySelectorAll('input[name="dims"]').forEach((r) => {
  r.addEventListener("change", () => {
    customDims.hidden = r.value !== "custom";
  });
});

function getDimensions() {
  const val = document.querySelector('input[name="dims"]:checked').value;
  if (val === "original") return { width: originalWidth || 1024, height: originalHeight || 1024 };
  if (val === "custom") return { width: parseInt(customW.value) || 1024, height: parseInt(customH.value) || 1024 };
  const [w, h] = val.split("x").map(Number);
  return { width: w, height: h };
}

// --- Presets ---
async function loadPresets() {
  const resp = await fetch("/api/presets");
  presets = await resp.json();
  renderPresetList();
}

function renderPresetList() {
  presetList.innerHTML = "";

  if (!presets.length) {
    presetList.innerHTML = '<p class="empty-state">No saved presets yet.</p>';
    return;
  }

  presets.forEach((preset) => {
    const label = document.createElement("label");
    label.className = "preset-item";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = preset.id;
    checkbox.dataset.prompt = preset.prompt;

    const text = document.createElement("div");
    text.className = "preset-item-text";

    const name = document.createElement("strong");
    name.textContent = preset.name;

    const prompt = document.createElement("span");
    prompt.textContent = preset.prompt;

    text.appendChild(name);
    text.appendChild(prompt);
    label.appendChild(checkbox);
    label.appendChild(text);
    presetList.appendChild(label);
  });
}

savePreset.addEventListener("click", async () => {
  const prompt = promptEl.value.trim();
  if (!prompt) return;
  const name = window.prompt("Preset name:");
  if (!name) return;
  await fetch("/api/presets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, prompt }),
  });
  await loadPresets();
});

deletePreset.addEventListener("click", async () => {
  const selectedIds = getSelectedPresetIds();
  if (!selectedIds.length) return;
  if (!confirm(`Delete ${selectedIds.length} selected preset(s)?`)) return;

  await Promise.all(selectedIds.map((id) => fetch(`/api/presets/${id}`, { method: "DELETE" })));
  await loadPresets();
});

function getSelectedPresetIds() {
  return Array.from(presetList.querySelectorAll('input[type="checkbox"]:checked')).map((el) => el.value);
}

function getSelectedPresetPrompts() {
  return Array.from(presetList.querySelectorAll('input[type="checkbox"]:checked')).map((el) => {
    const preset = presets.find((item) => item.id === el.value);
    return preset ? { name: preset.name, prompt: preset.prompt } : null;
  }).filter(Boolean);
}

function buildPromptQueue() {
  const customPrompt = promptEl.value.trim();
  const queued = [];
  const seen = new Set();

  getSelectedPresetPrompts().forEach((item) => {
    const key = `${item.name}:${item.prompt}`;
    if (!seen.has(key)) {
      seen.add(key);
      queued.push(item);
    }
  });

  if (customPrompt) {
    const key = `custom:${customPrompt}`;
    if (!seen.has(key)) {
      queued.push({ name: "Custom prompt", prompt: customPrompt });
    }
  }

  return queued;
}

async function loadRecentGenerations() {
  try {
    const resp = await fetch("/api/generations/recent");
    if (!resp.ok) throw new Error("Failed to load recent generations");
    const data = await resp.json();
    renderRecentResults(data.items || []);
  } catch (error) {
    resultsGrid.innerHTML = `<p style="color:var(--danger)">Error: ${error.message}</p>`;
  }
}

function renderRecentResults(items) {
  resultsGrid.innerHTML = "";

  if (!items.length) {
    resultsGrid.innerHTML = '<p class="empty-state">No generated images yet.</p>';
    return;
  }

  items.forEach((item, index) => {
    const card = document.createElement("div");
    card.className = "result-card";

    const img = document.createElement("img");
    img.src = item.url;
    img.alt = item.prompt || `Recent result ${index + 1}`;
    img.loading = "lazy";
    img.addEventListener("click", () => openModal(item.url));

    const body = document.createElement("div");
    body.className = "result-card-body";

    const prompt = document.createElement("p");
    prompt.className = "result-prompt";
    prompt.textContent = item.prompt;

    const meta = document.createElement("p");
    meta.className = "result-meta";
    meta.textContent = formatResultMeta(item);

    const actions = document.createElement("div");
    actions.className = "card-actions";
    const dl = document.createElement("a");
    dl.href = item.url;
    dl.download = item.filename || `enhanced-${index + 1}.png`;
    dl.className = "btn-small";
    dl.textContent = "Download";
    actions.appendChild(dl);

    body.appendChild(prompt);
    body.appendChild(meta);
    card.appendChild(img);
    card.appendChild(body);
    card.appendChild(actions);
    resultsGrid.appendChild(card);
  });
}

function formatResultMeta(item) {
  const parts = [];
  if (item.model) parts.push(item.model);
  if (item.created_at) {
    const date = new Date(item.created_at);
    if (!Number.isNaN(date.getTime())) {
      parts.push(date.toLocaleString());
    }
  }
  return parts.join(" • ");
}

function scheduleRecentRefresh() {
  window.clearTimeout(recentRefreshTimer);
  recentRefreshTimer = window.setTimeout(() => {
    loadRecentGenerations();
  }, 8000);
}

// --- Generate ---
generateBtn.addEventListener("click", async () => {
  if (!uploadedFile) { alert("Please upload an image first."); return; }
  const promptQueue = buildPromptQueue();
  if (!promptQueue.length) { alert("Select at least one preset or enter a custom prompt."); return; }

  const model = document.querySelector('input[name="model"]:checked').value;
  const { width, height } = getDimensions();
  const n = parseInt(countEl.value) || 1;

  generateBtn.disabled = true;
  generateBtn.textContent = "Uploading...";
  queueStatus.textContent = `Uploading ${promptQueue.length} request(s)...`;

  try {
    const responses = await Promise.all(promptQueue.map(async ({ prompt }) => {
      const form = new FormData();
      form.append("image", uploadedFile);
      form.append("model", model);
      form.append("prompt", prompt);
      form.append("width", width);
      form.append("height", height);
      form.append("n", n);

      const resp = await fetch("/api/generate", { method: "POST", body: form });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || "Queueing failed");
      }
      return resp.json();
    }));

    queueStatus.textContent = `${responses.length} request(s) queued. You can close the browser once uploads finish and check Recent Generations later.`;
    scheduleRecentRefresh();
  } catch (e) {
    queueStatus.textContent = `Error: ${e.message}`;
  } finally {
    generateBtn.disabled = false;
    generateBtn.textContent = "Generate";
  }
});

// --- Modal ---
function openModal(src) {
  modalImg.src = src;
  modalDownload.href = src;
  modal.hidden = false;
}

modalClose.addEventListener("click", () => { modal.hidden = true; });
document.querySelector(".modal-backdrop").addEventListener("click", () => { modal.hidden = true; });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") modal.hidden = true; });
refreshRecentBtn.addEventListener("click", () => { loadRecentGenerations(); });

// --- Init ---
loadPresets();
loadRecentGenerations();
window.setInterval(loadRecentGenerations, 30000);
