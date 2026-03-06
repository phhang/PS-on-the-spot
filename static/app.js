// --- State ---
let uploadedFile = null;
let originalWidth = 0;
let originalHeight = 0;
let presets = [];

// --- DOM refs ---
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const previewContainer = document.getElementById("preview-container");
const previewImg = document.getElementById("preview-img");
const imgDims = document.getElementById("img-dims");
const clearUpload = document.getElementById("clear-upload");
const presetSelect = document.getElementById("preset-select");
const savePreset = document.getElementById("save-preset");
const deletePreset = document.getElementById("delete-preset");
const promptEl = document.getElementById("prompt");
const countEl = document.getElementById("count");
const generateBtn = document.getElementById("generate-btn");
const resultsGrid = document.getElementById("results-grid");
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
  renderPresetOptions();
}

function renderPresetOptions() {
  presetSelect.innerHTML = '<option value="">— Select a preset —</option>';
  presets.forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = p.name;
    presetSelect.appendChild(opt);
  });
}

presetSelect.addEventListener("change", () => {
  const p = presets.find((x) => x.id === presetSelect.value);
  if (p) promptEl.value = p.prompt;
});

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
  const id = presetSelect.value;
  if (!id) return;
  if (!confirm("Delete this preset?")) return;
  await fetch(`/api/presets/${id}`, { method: "DELETE" });
  promptEl.value = "";
  await loadPresets();
});

// --- Generate ---
generateBtn.addEventListener("click", async () => {
  if (!uploadedFile) { alert("Please upload an image first."); return; }
  const prompt = promptEl.value.trim();
  if (!prompt) { alert("Please enter a prompt."); return; }

  const model = document.querySelector('input[name="model"]:checked').value;
  const { width, height } = getDimensions();
  const n = parseInt(countEl.value) || 4;

  // Show spinners
  resultsGrid.innerHTML = "";
  for (let i = 0; i < n; i++) {
    const div = document.createElement("div");
    div.className = "spinner-card";
    div.innerHTML = '<div class="spinner"></div>';
    resultsGrid.appendChild(div);
  }

  generateBtn.disabled = true;
  generateBtn.textContent = "Generating...";

  const form = new FormData();
  form.append("image", uploadedFile);
  form.append("model", model);
  form.append("prompt", prompt);
  form.append("width", width);
  form.append("height", height);
  form.append("n", n);

  try {
    const resp = await fetch("/api/generate", { method: "POST", body: form });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || "Generation failed");
    }
    const data = await resp.json();
    renderResults(data.images);
  } catch (e) {
    resultsGrid.innerHTML = `<p style="color:var(--danger)">Error: ${e.message}</p>`;
  } finally {
    generateBtn.disabled = false;
    generateBtn.textContent = "Generate";
  }
});

function renderResults(images) {
  resultsGrid.innerHTML = "";
  images.forEach((src, i) => {
    const card = document.createElement("div");
    card.className = "result-card";

    const img = document.createElement("img");
    img.src = src;
    img.alt = `Result ${i + 1}`;
    img.addEventListener("click", () => openModal(src));

    const actions = document.createElement("div");
    actions.className = "card-actions";
    const dl = document.createElement("a");
    dl.href = src;
    dl.download = `enhanced-${i + 1}.png`;
    dl.className = "btn-small";
    dl.textContent = "Download";
    actions.appendChild(dl);

    card.appendChild(img);
    card.appendChild(actions);
    resultsGrid.appendChild(card);
  });
}

// --- Modal ---
function openModal(src) {
  modalImg.src = src;
  modalDownload.href = src;
  modal.hidden = false;
}

modalClose.addEventListener("click", () => { modal.hidden = true; });
document.querySelector(".modal-backdrop").addEventListener("click", () => { modal.hidden = true; });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") modal.hidden = true; });

// --- Init ---
loadPresets();
