// JOB_ID is injected via a data attribute to avoid inline script requirements.
const JOB_ID  = document.getElementById('job-data').dataset.jobId;
const POLL_MS = 2000;

// ── Pipeline ───────────────────────────────────────────────────────────────
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
      <div class="step-dot w-9 h-9 rounded-full border-2 border-white/20 bg-white/[0.05]
                  flex items-center justify-center text-sm text-white/40
                  transition-all duration-400">${s.icon}</div>
      <span class="step-lbl text-[10px] text-white/40 font-medium transition-colors duration-400">
        ${s.label}
      </span>`;
    container.appendChild(node);
    if (i < PIPELINE_STEPS.length - 1) {
      const line = document.createElement('div');
      line.dataset.lineAfter = s.id;
      line.className = 'pipeline-line flex-1 h-px bg-white/[0.12] mt-4.5 mx-1 transition-all duration-400';
      container.appendChild(line);
    }
  });
}

function setPipelineStep(stepId, failed = false) {
  const container = document.getElementById('pipeline');
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
      dot.className = 'step-dot w-9 h-9 rounded-full border-2 border-red-500/70 bg-red-500/15 flex items-center justify-center text-sm text-red-400 transition-all duration-400';
      lbl.className = 'step-lbl text-[10px] text-red-400 font-semibold transition-colors duration-400';
    } else if (done) {
      dot.className = 'step-dot w-9 h-9 rounded-full border-2 border-violet-500/60 bg-violet-500/20 flex items-center justify-center text-sm text-violet-300 transition-all duration-400';
      lbl.className = 'step-lbl text-[10px] text-violet-400 font-medium transition-colors duration-400';
      if (lineEl) lineEl.className = 'pipeline-line flex-1 h-px bg-violet-500/40 mt-4.5 mx-1 transition-all duration-400';
    } else if (active) {
      dot.className = 'step-dot w-9 h-9 rounded-full border-2 border-violet-400 bg-violet-500/25 flex items-center justify-center text-sm text-violet-200 shadow-lg shadow-violet-500/30 scale-110 transition-all duration-400';
      lbl.className = 'step-lbl text-[10px] text-violet-300 font-bold transition-colors duration-400';
    } else {
      dot.className = 'step-dot w-9 h-9 rounded-full border-2 border-white/20 bg-white/[0.05] flex items-center justify-center text-sm text-white/40 transition-all duration-400';
      lbl.className = 'step-lbl text-[10px] text-white/40 font-medium transition-colors duration-400';
    }
  });
}

// ── DOM refs ───────────────────────────────────────────────────────────────
const badge       = document.getElementById('status-badge');
const filenameEl  = document.getElementById('filename');
const progressWrap= document.getElementById('progress-wrap');
const progressBar = document.getElementById('progress-bar');
const stepText    = document.getElementById('step-text');
const stepPct     = document.getElementById('step-pct');
const stepSpinner = document.getElementById('step-spinner');
const downloadBtn = document.getElementById('download-btn');
const errorBox    = document.getElementById('error-box');
const errorText   = document.getElementById('error-text');

const BADGE_STYLES = {
  pending:    'bg-amber-500/15 text-amber-300',
  processing: 'bg-blue-500/15 text-blue-300',
  completed:  'bg-emerald-500/15 text-emerald-300',
  failed:     'bg-red-500/15 text-red-300',
};

function progressStepToState(step) {
  if (!step) return { pipelineStep: 'analyze', label: 'Analyzing PDF…', pct: 20 };
  if (step === 'uploading')  return { pipelineStep: 'upload',  label: 'Uploading file…',  pct: 8  };
  if (step === 'analyzing')  return { pipelineStep: 'analyze', label: 'Analyzing PDF…',   pct: 22 };
  if (step === 'extracting') return { pipelineStep: 'extract', label: 'Extracting text…', pct: 55 };
  if (step === 'building')   return { pipelineStep: 'build',   label: 'Building EPUB…',   pct: 85 };
  if (step.startsWith('ocr_')) {
    const [, n, t] = step.split('_');
    const ratio = parseInt(n) / Math.max(1, parseInt(t));
    return { pipelineStep: 'extract', label: `OCR — page ${n} of ${t}`, pct: Math.round(22 + ratio * 58) };
  }
  return { pipelineStep: 'analyze', label: 'Processing…', pct: 35 };
}

let ticks = 0, pollTimer = null;

function render(job) {
  badge.textContent = job.status;
  badge.className   = `px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider flex-shrink-0 ${BADGE_STYLES[job.status] || 'bg-white/10 text-white/40'}`;
  filenameEl.textContent = job.original_filename || '';

  const active = job.status === 'pending' || job.status === 'processing';

  if (active) {
    ticks++;
    const state = progressStepToState(job.progress_step);
    const pct   = job.progress_step ? state.pct : Math.min(88, 10 + ticks * 5);

    setPipelineStep(state.pipelineStep);
    progressBar.style.width  = pct + '%';
    stepPct.textContent      = pct + '%';
    stepText.textContent     = state.label;
    stepSpinner.classList.remove('hidden');
  }

  if (job.status === 'completed' && job.epub_url) {
    setPipelineStep('done');
    progressBar.style.width = '100%';
    progressBar.className   = 'h-full rounded-full bg-emerald-500 transition-[width] duration-700 ease-out';
    stepText.textContent    = 'Conversion complete!';
    stepSpinner.classList.add('hidden');
    stepPct.textContent     = '100%';

    setTimeout(() => progressWrap.classList.add('hidden'), 1200);

    downloadBtn.href = job.epub_url;
    downloadBtn.classList.remove('hidden');
    downloadBtn.classList.add('flex');
  }

  if (job.status === 'failed') {
    setPipelineStep('build', true);
    progressBar.style.width  = '100%';
    progressBar.className    = 'h-full rounded-full bg-red-500 transition-[width] duration-700 ease-out';
    stepSpinner.classList.add('hidden');
    stepText.textContent     = 'Conversion failed';
    stepPct.textContent      = '';

    errorText.textContent = job.error || 'Conversion failed. Please try again.';
    errorBox.classList.remove('hidden');
    errorBox.classList.add('flex');
  }

  if (job.status === 'completed' || job.status === 'failed') {
    clearInterval(pollTimer);
  }
}

async function poll() {
  try {
    const r = await fetch(`/api/v1/jobs/${JOB_ID}`);
    if (r.ok) render(await r.json());
  } catch (_) {}
}

buildPipeline(document.getElementById('pipeline'));
setPipelineStep('upload');
poll();
pollTimer = setInterval(poll, POLL_MS);
