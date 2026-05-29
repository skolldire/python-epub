// ── Pipeline step definitions ─────────────────────────────────────────────
const PIPELINE_STEPS = [
  { id: 'upload',  icon: '↑', label: 'Upload'  },
  { id: 'analyze', icon: '⚡', label: 'Analyze' },
  { id: 'extract', icon: '✦', label: 'Extract' },
  { id: 'build',   icon: '◈', label: 'Build'   },
  { id: 'done',    icon: '✓', label: 'Done'    },
];

function buildPipeline(container) {
  container.innerHTML = '';
  PIPELINE_STEPS.forEach((s, i) => {
    const node = document.createElement('div');
    node.dataset.step = s.id;
    node.className = 'pipeline-node flex flex-col items-center gap-1 flex-1';
    node.innerHTML = `
      <div class="step-dot w-8 h-8 rounded-full border-2 border-white/20 bg-white/[0.05]
                  flex items-center justify-center text-xs text-white/40
                  transition-all duration-400">${s.icon}</div>
      <span class="step-lbl text-[10px] text-white/40 font-medium transition-colors duration-400">
        ${s.label}
      </span>`;
    container.appendChild(node);
    if (i < PIPELINE_STEPS.length - 1) {
      const line = document.createElement('div');
      line.dataset.lineAfter = s.id;
      line.className = 'pipeline-line flex-1 h-px bg-white/[0.12] mt-4 mx-1 transition-all duration-400';
      container.appendChild(line);
    }
  });
}

function setPipelineStep(container, stepId, failed = false) {
  const order = ['upload', 'analyze', 'extract', 'build', 'done'];
  const idx   = order.indexOf(stepId);
  PIPELINE_STEPS.forEach((s, i) => {
    const node   = container.querySelector(`[data-step="${s.id}"]`);
    if (!node) return;
    const dot    = node.querySelector('.step-dot');
    const lbl    = node.querySelector('.step-lbl');
    const lineEl = container.querySelector(`[data-line-after="${s.id}"]`);
    const done   = i < idx;
    const active = i === idx;
    if (failed && active) {
      dot.className = 'step-dot w-8 h-8 rounded-full border-2 border-red-500/70 bg-red-500/15 flex items-center justify-center text-xs text-red-400 transition-all duration-400';
      lbl.className = 'step-lbl text-[10px] text-red-400 font-bold transition-colors duration-400';
    } else if (done) {
      dot.className = 'step-dot w-8 h-8 rounded-full border-2 border-violet-500/60 bg-violet-500/20 flex items-center justify-center text-xs text-violet-300 transition-all duration-400';
      lbl.className = 'step-lbl text-[10px] text-violet-400 font-medium transition-colors duration-400';
      if (lineEl) lineEl.className = 'pipeline-line flex-1 h-px bg-violet-500/40 mt-4 mx-1 transition-all duration-400';
    } else if (active) {
      dot.className = 'step-dot w-8 h-8 rounded-full border-2 border-violet-400 bg-violet-500/25 flex items-center justify-center text-xs text-violet-200 shadow-md shadow-violet-500/40 scale-110 transition-all duration-400';
      lbl.className = 'step-lbl text-[10px] text-violet-300 font-bold transition-colors duration-400';
    } else {
      dot.className = 'step-dot w-8 h-8 rounded-full border-2 border-white/20 bg-white/[0.05] flex items-center justify-center text-xs text-white/40 transition-all duration-400';
      lbl.className = 'step-lbl text-[10px] text-white/40 font-medium transition-colors duration-400';
    }
  });
}

// ── State ─────────────────────────────────────────────────────────────────
let currentTab    = 'single';
let singleFile    = null;
let multiQueue    = [];
let completedJobs = [];

// ── Tab switching ─────────────────────────────────────────────────────────
function switchTab(name) {
  currentTab = name;
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
  document.getElementById(`tab-${name}`).classList.remove('hidden');
  document.querySelectorAll('.tab-btn').forEach(btn => {
    const active = btn.dataset.tab === name;
    btn.className = `tab-btn flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl
      text-sm font-semibold transition-all duration-200 ${
      active
        ? 'bg-violet-600 text-white shadow-lg shadow-violet-900/40'
        : 'text-white/65 hover:text-white hover:bg-white/[0.05]'
    }`;
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────
function fmtBytes(b) {
  return b < 1048576 ? (b / 1024).toFixed(1) + ' KB' : (b / 1048576).toFixed(1) + ' MB';
}

function progressStepToState(step) {
  if (!step) return { pipelineStep: 'analyze', label: 'Analyzing PDF…', pct: 20, spinner: true };
  if (step === 'uploading')  return { pipelineStep: 'upload',  label: 'Uploading file…',  pct: 8,  spinner: true };
  if (step === 'analyzing')  return { pipelineStep: 'analyze', label: 'Analyzing PDF…',   pct: 22, spinner: true };
  if (step === 'extracting') return { pipelineStep: 'extract', label: 'Extracting text…', pct: 55, spinner: true };
  if (step === 'building')   return { pipelineStep: 'build',   label: 'Building EPUB…',   pct: 85, spinner: true };
  if (step.startsWith('ocr_')) {
    const [, n, t] = step.split('_');
    const ratio = parseInt(n) / Math.max(1, parseInt(t));
    return { pipelineStep: 'extract', label: `OCR — page ${n} of ${t}`, pct: Math.round(22 + ratio * 58), spinner: true };
  }
  return { pipelineStep: 'analyze', label: 'Processing…', pct: 35, spinner: true };
}

// ── Completion modal ──────────────────────────────────────────────────────
function openModal() {
  const modal = document.getElementById('done-modal');
  const list  = document.getElementById('modal-downloads');
  const title = document.getElementById('modal-title');
  const sub   = document.getElementById('modal-subtitle');

  list.innerHTML = '';
  const ok = completedJobs.filter(j => j.dlUrl);
  if (ok.length === 0) return;

  if (ok.length === 1) {
    title.textContent = 'Conversion complete!';
    sub.textContent   = ok[0].epubName + ' is ready to download.';
  } else {
    title.textContent = `${ok.length} books ready!`;
    sub.textContent   = 'All conversions finished successfully.';
  }

  ok.forEach(({ epubName, dlUrl }) => {
    const a = document.createElement('a');
    a.href      = dlUrl;
    a.className = 'flex items-center gap-3 px-4 py-3 rounded-xl bg-white/[0.06] border border-white/[0.14] hover:bg-white/[0.10] transition-all group/dl';
    a.innerHTML = `
      <svg class="w-4 h-4 text-emerald-400 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
        <path fill-rule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clip-rule="evenodd"/>
      </svg>
      <span class="text-sm font-semibold text-white/85 truncate flex-1 group-hover/dl:text-white">${epubName}</span>
      <span class="text-xs text-emerald-400 font-bold flex-shrink-0">Download</span>`;
    list.appendChild(a);
  });

  modal.classList.remove('hidden');
  modal.classList.add('flex');
}

function closeModal() {
  document.getElementById('done-modal').classList.add('hidden');
  document.getElementById('done-modal').classList.remove('flex');
  resetApp();
}

function resetApp() {
  singleFile = null;
  document.getElementById('single-state-empty').classList.remove('hidden');
  const sel = document.getElementById('single-state-selected');
  sel.classList.add('hidden');
  sel.classList.remove('flex');
  document.getElementById('single-filename').textContent = '';
  document.getElementById('single-fileinfo').textContent = '';
  document.getElementById('single-title').value  = '';
  document.getElementById('single-author').value = '';
  document.getElementById('single-cover-name').textContent = 'Choose cover image';
  document.getElementById('single-meta').classList.add('hidden');
  singleBtn.disabled = true;
  singleBtnLbl.textContent = 'Convert to EPUB';

  multiQueue = [];
  multiList.innerHTML = '';
  multiList.classList.add('hidden');
  multiDropLbl.textContent = 'Drag & drop PDFs here, or click to browse';
  multiBtn.disabled = true;
  document.getElementById('multi-btn-label').textContent = 'Convert to EPUB';

  document.getElementById('progress-section').classList.add('hidden');
  document.getElementById('progress-list').innerHTML = '';
  doneCount     = 0;
  totalCount    = 0;
  completedJobs = [];
  updateProgressSummary();
}

// ── Progress section ──────────────────────────────────────────────────────
let doneCount = 0, totalCount = 0;

function ensureProgressSection() {
  document.getElementById('progress-section').classList.remove('hidden');
}

function updateProgressSummary() {
  const el = document.getElementById('progress-summary');
  if (totalCount === 0) { el.textContent = ''; return; }
  el.textContent = doneCount < totalCount
    ? `${doneCount} / ${totalCount} done`
    : `All ${totalCount} converted`;
}

function addProgressRow(jobId, filename) {
  ensureProgressSection();
  const tpl   = document.getElementById('progress-row-tpl');
  const clone = tpl.content.cloneNode(true);
  const row   = clone.firstElementChild;
  row.dataset.job = jobId;
  row.querySelector('.pr-name').textContent    = filename;
  row.querySelector('.pr-badge').textContent   = 'uploading';
  row.querySelector('.pr-badge').className     =
    'pr-badge px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider bg-amber-500/20 text-amber-300 flex-shrink-0';
  buildPipeline(row.querySelector('.pr-pipeline'));
  setPipelineStep(row.querySelector('.pr-pipeline'), 'upload');
  row.querySelector('.pr-bar').style.width       = '8%';
  row.querySelector('.pr-pct').textContent       = '8%';
  row.querySelector('.pr-step-text').textContent = 'Uploading file…';
  row.querySelector('.pr-step-spinner').classList.remove('hidden');
  document.getElementById('progress-list').prepend(row);
  totalCount++;
  updateProgressSummary();
  return document.querySelector(`[data-job="${jobId}"]`);
}

function getProgressRow(jobId) {
  return document.querySelector(`[data-job="${jobId}"]`);
}

const BADGE_STYLES = {
  uploading:  'bg-amber-500/20 text-amber-300',
  processing: 'bg-blue-500/20 text-blue-300',
  done:       'bg-emerald-500/20 text-emerald-300',
  failed:     'bg-red-500/20 text-red-300',
};

function updateProgressRow(row, { badge, pipelineStep, label, pct, spinner, done, dlUrl, filename, failed }) {
  if (badge) {
    const b = row.querySelector('.pr-badge');
    b.textContent = badge;
    b.className   = `pr-badge px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider flex-shrink-0 ${BADGE_STYLES[badge] || 'bg-white/15 text-white/65'}`;
  }
  if (pipelineStep) setPipelineStep(row.querySelector('.pr-pipeline'), pipelineStep, !!failed);
  if (label !== undefined) row.querySelector('.pr-step-text').textContent = label;
  if (spinner !== undefined) row.querySelector('.pr-step-spinner').classList.toggle('hidden', !spinner);
  if (pct !== undefined) {
    row.querySelector('.pr-pct').textContent = pct + '%';
    const bar = row.querySelector('.pr-bar');
    bar.style.width = pct + '%';
    bar.className = `pr-bar h-full rounded-full transition-[width] duration-700 ease-out ${
      failed ? 'bg-red-500' : pct >= 100 ? 'bg-emerald-500' : 'bg-violet-500'
    }`;
  }
  if (done && dlUrl) {
    const dl = row.querySelector('.pr-dl');
    dl.href = dlUrl;
    if (filename) dl.setAttribute('download', filename);
    dl.classList.remove('hidden');
    dl.classList.add('flex');
  }
}

// ── Job polling ───────────────────────────────────────────────────────────
function startPolling(jobId, filename, onDone) {
  const row = getProgressRow(jobId);
  updateProgressRow(row, { badge: 'processing', pipelineStep: 'analyze', label: 'Analyzing PDF…', pct: 20, spinner: true });

  const timer = setInterval(async () => {
    try {
      const res = await fetch(`/api/v1/jobs/${jobId}`);
      if (!res.ok) {
        clearInterval(timer);
        doneCount++;
        updateProgressSummary();
        const msg = res.status === 404 ? 'Job not found — the server may have restarted' : `Server error (${res.status})`;
        updateProgressRow(row, { badge: 'failed', pipelineStep: 'build', label: '✗ ' + msg, pct: 100, spinner: false, failed: true });
        if (onDone) onDone(false, null);
        return;
      }
      const d = await res.json();

      if (d.status === 'completed') {
        clearInterval(timer);
        doneCount++;
        updateProgressSummary();
        updateProgressRow(row, { badge: 'done', pipelineStep: 'done', label: 'Conversion complete!', pct: 100, spinner: false, done: true, dlUrl: d.epub_url, filename });
        if (onDone) onDone(true, d.epub_url);

      } else if (d.status === 'failed') {
        clearInterval(timer);
        doneCount++;
        updateProgressSummary();
        updateProgressRow(row, { badge: 'failed', pipelineStep: 'build', label: '✗ ' + (d.error || 'Conversion failed'), pct: 100, spinner: false, failed: true });
        if (onDone) onDone(false, null);

      } else if (d.progress_step) {
        const state = progressStepToState(d.progress_step);
        updateProgressRow(row, { badge: 'processing', pipelineStep: state.pipelineStep, label: state.label, pct: state.pct, spinner: state.spinner });
      }
    } catch (_) {}
  }, 1500);
}

// ── Submit a job ──────────────────────────────────────────────────────────
async function submitJob(file, title, author, cover, onDone) {
  const fd = new FormData();
  fd.append('file', file);
  if (title)  fd.append('title',  title);
  if (author) fd.append('author', author);
  if (cover)  fd.append('cover',  cover);

  const placeholderKey = 'uploading_' + Date.now();
  const row = addProgressRow(placeholderKey, file.name);

  try {
    const res  = await fetch('/api/v1/jobs', { method: 'POST', body: fd });
    const json = await res.json();
    if (!res.ok) throw new Error(json?.error?.message || `HTTP ${res.status}`);
    row.dataset.job = json.id;
    startPolling(json.id, file.name, onDone);
  } catch (err) {
    doneCount++;
    updateProgressSummary();
    updateProgressRow(row, { badge: 'failed', pipelineStep: 'upload', label: '✗ ' + err.message, pct: 0, spinner: false, failed: true });
    if (onDone) onDone(false, null);
  }
}

// ══════════════════════════════════════════════════════════════════════════
// INDIVIDUAL MODE
// ══════════════════════════════════════════════════════════════════════════
const singleDropzone = document.getElementById('single-dropzone');
const singleInput    = document.getElementById('single-input');
const singleMeta     = document.getElementById('single-meta');
const singleBtn      = document.getElementById('single-btn');
const singleBtnLbl   = document.getElementById('single-btn-label');

function selectSingleFile(file) {
  if (!file || !file.name.toLowerCase().endsWith('.pdf')) return;
  singleFile = file;
  document.getElementById('single-state-empty').classList.add('hidden');
  const sel = document.getElementById('single-state-selected');
  sel.classList.remove('hidden');
  sel.classList.add('flex');
  document.getElementById('single-filename').textContent = file.name;
  document.getElementById('single-fileinfo').textContent = fmtBytes(file.size);
  singleMeta.classList.remove('hidden');
  singleBtn.disabled = false;
  (async () => {
    const fd = new FormData(); fd.append('file', file);
    try {
      const m = await fetch('/api/v1/jobs/peek', { method: 'POST', body: fd }).then(r => r.json());
      if (m.page_count > 0)
        document.getElementById('single-fileinfo').textContent = fmtBytes(file.size) + ` · ${m.page_count} pages`;
      if (m.title)  document.getElementById('single-title').value  = m.title;
      if (m.author) document.getElementById('single-author').value = m.author;
    } catch (_) {}
  })();
}

singleDropzone.addEventListener('dragover', e => { e.preventDefault(); singleDropzone.classList.add('border-violet-500/60', 'bg-violet-500/[0.05]'); });
['dragleave', 'dragend'].forEach(ev => singleDropzone.addEventListener(ev, () => singleDropzone.classList.remove('border-violet-500/60', 'bg-violet-500/[0.05]')));
singleDropzone.addEventListener('drop', e => { e.preventDefault(); singleDropzone.classList.remove('border-violet-500/60', 'bg-violet-500/[0.05]'); selectSingleFile(e.dataTransfer.files[0]); });
singleInput.addEventListener('change', () => { selectSingleFile(singleInput.files[0]); singleInput.value = ''; });

document.getElementById('single-cover').addEventListener('change', function () {
  document.getElementById('single-cover-name').textContent = this.files[0]?.name || 'Choose cover image';
});

singleBtn.addEventListener('click', async () => {
  if (!singleFile) return;
  singleBtn.disabled = true;
  singleBtnLbl.textContent = 'Converting…';
  const capturedFile = singleFile;

  await submitJob(
    capturedFile,
    document.getElementById('single-title').value.trim(),
    document.getElementById('single-author').value.trim(),
    document.getElementById('single-cover').files[0],
    (ok, dlUrl) => {
      singleBtn.disabled = false;
      singleBtnLbl.textContent = 'Convert to EPUB';
      if (ok && dlUrl) {
        completedJobs = [{ epubName: capturedFile.name.replace(/\.pdf$/i, '.epub'), dlUrl }];
        openModal();
      }
    }
  );
});

// ══════════════════════════════════════════════════════════════════════════
// MULTIPLE MODE
// ══════════════════════════════════════════════════════════════════════════
const multiDropzone = document.getElementById('multi-dropzone');
const multiInput    = document.getElementById('multi-input');
const multiList     = document.getElementById('multi-list');
const multiBtn      = document.getElementById('multi-btn');
const multiDropLbl  = document.getElementById('multi-drop-label');
const multiRowTpl   = document.getElementById('multi-row-tpl');

function addMultiFiles(files) {
  for (const f of files) {
    if (!f.name.toLowerCase().endsWith('.pdf')) continue;
    const idx   = Date.now() + Math.random();
    const clone = multiRowTpl.content.cloneNode(true);
    const row   = clone.firstElementChild;
    row.dataset.idx = idx;
    row.querySelector('.row-name').textContent = f.name;
    row.querySelector('.row-info').textContent = fmtBytes(f.size);
    row.querySelector('.row-del').addEventListener('click', () => {
      multiQueue = multiQueue.filter(e => e.idx !== idx);
      row.remove();
      syncMulti();
    });
    multiList.appendChild(clone);
    multiQueue.push({ idx, file: f, done: false });
    (async () => {
      const fd = new FormData(); fd.append('file', f);
      try {
        const m  = await fetch('/api/v1/jobs/peek', { method: 'POST', body: fd }).then(r => r.json());
        const r2 = multiList.querySelector(`[data-idx="${idx}"] .row-info`);
        if (r2 && m.page_count > 0) r2.textContent = fmtBytes(f.size) + ` · ${m.page_count} pages`;
      } catch (_) {}
    })();
  }
  syncMulti();
}

function syncMulti() {
  const fresh = multiQueue.filter(e => !e.started);
  multiList.classList.toggle('hidden', multiQueue.length === 0);
  multiDropLbl.textContent = multiQueue.length > 0
    ? `${multiQueue.length} file${multiQueue.length > 1 ? 's' : ''} queued — drop more to add`
    : 'Drag & drop PDFs here, or click to browse';
  multiBtn.disabled = fresh.length === 0;
  document.getElementById('multi-btn-label').textContent = fresh.length > 0
    ? `Convert ${fresh.length} book${fresh.length > 1 ? 's' : ''} to EPUB`
    : 'Convert to EPUB';
}

multiDropzone.addEventListener('dragover', e => { e.preventDefault(); multiDropzone.classList.add('border-violet-500/60', 'bg-violet-500/[0.04]'); });
['dragleave', 'dragend'].forEach(ev => multiDropzone.addEventListener(ev, () => multiDropzone.classList.remove('border-violet-500/60', 'bg-violet-500/[0.04]')));
multiDropzone.addEventListener('drop', e => { e.preventDefault(); multiDropzone.classList.remove('border-violet-500/60', 'bg-violet-500/[0.04]'); addMultiFiles(Array.from(e.dataTransfer.files)); });
multiInput.addEventListener('change', () => { addMultiFiles(Array.from(multiInput.files)); multiInput.value = ''; });

multiBtn.addEventListener('click', () => {
  const fresh = multiQueue.filter(e => !e.started);
  if (!fresh.length) return;
  completedJobs = [];
  let remaining = fresh.length;
  fresh.forEach(entry => {
    entry.started = true;
    const capturedFile = entry.file;
    submitJob(capturedFile, '', '', null, (ok, dlUrl) => {
      entry.done = true;
      if (ok && dlUrl) completedJobs.push({ epubName: capturedFile.name.replace(/\.pdf$/i, '.epub'), dlUrl });
      remaining--;
      if (remaining === 0) {
        syncMulti();
        if (completedJobs.length > 0) openModal();
      }
    });
  });
  syncMulti();
});
