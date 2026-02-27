/**
 * explorer.js — Name Explorer tab logic
 */

import { getBabyFreq, getChangesByName, getCorrelation, getCurveSummary, getAllNames, getTransRateByYear } from './data.js';
import { renderBabyTrendChart, renderTransVsBabyChart } from './charts.js';

let _compareMode = false;
let _currentName = null;
let _compareName = null;

export function initExplorer() {
  setupSearch('explorer-search', 'explorer-autocomplete', name => loadName(name));
  setupSearch('compare-search', 'compare-autocomplete', name => {
    _compareName = name;
    if (_currentName) renderExplorer(_currentName);
  });

  document.getElementById('compare-toggle').addEventListener('click', () => {
    _compareMode = !_compareMode;
    const wrap = document.getElementById('compare-wrap');
    wrap.classList.toggle('hidden', !_compareMode);
    if (!_compareMode) {
      _compareName = null;
      if (_currentName) renderExplorer(_currentName);
    }
  });
}

function setupSearch(inputId, listId, onSelect) {
  const input = document.getElementById(inputId);
  const list = document.getElementById(listId);
  let debounceTimer;

  input.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      const q = input.value.trim().toUpperCase();
      if (!q) { closeList(list); return; }
      const matches = getAllNames().filter(n => n.startsWith(q)).slice(0, 10);
      renderList(list, matches, input, onSelect);
    }, 200);
  });

  input.addEventListener('keydown', e => {
    const items = list.querySelectorAll('li');
    let sel = [...items].findIndex(li => li.classList.contains('selected'));
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      sel = Math.min(sel + 1, items.length - 1);
      items.forEach((li, i) => li.classList.toggle('selected', i === sel));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      sel = Math.max(sel - 1, 0);
      items.forEach((li, i) => li.classList.toggle('selected', i === sel));
    } else if (e.key === 'Enter') {
      const selItem = list.querySelector('li.selected');
      if (selItem) { onSelect(selItem.textContent); input.value = selItem.textContent; closeList(list); }
    } else if (e.key === 'Escape') {
      closeList(list);
    }
  });

  document.addEventListener('click', e => {
    if (!input.contains(e.target) && !list.contains(e.target)) closeList(list);
  });
}

function renderList(list, items, input, onSelect) {
  if (!items.length) { closeList(list); return; }
  list.innerHTML = items.map(n => `<li>${n}</li>`).join('');
  list.classList.add('open');
  list.querySelectorAll('li').forEach(li => {
    li.addEventListener('click', () => {
      onSelect(li.textContent);
      input.value = li.textContent;
      closeList(list);
    });
  });
}

function closeList(list) {
  list.innerHTML = '';
  list.classList.remove('open');
}

export function loadName(name) {
  _currentName = name;
  document.getElementById('explorer-search').value = name;
  renderExplorer(name);
  // Update URL hash to include name
  history.replaceState(null, '', `#explorer?name=${encodeURIComponent(name)}`);
}

function renderExplorer(name) {
  const babyFreq = getBabyFreq(name);
  const allAppearances = getChangesByName(name);
  const transAppearances = allAppearances.filter(a => Math.abs(a.d) >= 0.7);

  // Baby trend chart — overlays show trans-only appearances
  const compareFreq = (_compareMode && _compareName) ? getBabyFreq(_compareName) : null;
  renderBabyTrendChart('explorer-chart', name, babyFreq, transAppearances, _compareName, compareFreq);

  // Stats panel (uses trans count)
  renderStatsPanel(name, transAppearances);

  // Gazette list (trans-only)
  renderGazetteList(transAppearances);

  // Trans vs baby popularity chart
  renderTransVsBabySection(name, babyFreq, transAppearances);

  // Show content, hide empty state
  document.getElementById('explorer-content').classList.remove('hidden');
  document.getElementById('explorer-empty').classList.add('hidden');
}

function renderStatsPanel(name, transAppearances) {
  const cs = getCurveSummary(name);
  const corr = getCorrelation(name);

  // Curve score
  const csEl = document.getElementById('explorer-curve-score');
  if (cs && cs.mean_cs != null) {
    const sign = cs.mean_cs > 0 ? '+' : '';
    const cls = cs.mean_cs > 0.05 ? 'positive' : cs.mean_cs < -0.05 ? 'negative' : 'neutral';
    csEl.innerHTML = `<span class="score-badge ${cls}">${sign}${cs.mean_cs.toFixed(3)}</span>
      <div class="text-muted" style="font-size:11px;margin-top:4px;">
        ${cs.dir} · ${cs.n} records scored
      </div>`;
  } else {
    csEl.innerHTML = `<span class="text-dim">No data in 2000–2018 window</span>`;
  }

  // Lag correlation
  const corrEl = document.getElementById('explorer-lag');
  if (corr) {
    const sig = corr.p < 0.05 ? ' ✓ p<0.05' : '';
    corrEl.innerHTML = `<strong>${corr.lag > 0 ? '+' : ''}${corr.lag}y</strong>
      <span class="text-muted"> lag · r=${corr.r.toFixed(3)} · p=${corr.p.toFixed(3)}${sig}</span>`;
  } else {
    corrEl.innerHTML = `<span class="text-dim">Insufficient data for lag analysis</span>`;
  }

  // Gazette count (trans-only)
  document.getElementById('explorer-count').textContent =
    `${transAppearances.length} trans gazette appearance${transAppearances.length !== 1 ? 's' : ''}`;
}

function renderGazetteList(transAppearances) {
  const el = document.getElementById('explorer-gazette-list');
  if (!transAppearances.length) {
    el.innerHTML = '<li style="color:var(--text-dim)">No trans gazette records</li>';
    return;
  }
  const sorted = [...transAppearances].sort((a, b) => a.y - b.y);
  el.innerHTML = sorted.map(app => {
    const dir = app.d >= 0.7 ? 'female' : 'male';
    const dirLabel = app.d >= 0.7 ? 'Female' : 'Male';
    const cs = app.cs != null ? ` · score ${app.cs > 0 ? '+' : ''}${app.cs.toFixed(2)}` : '';
    return `<li>
      <span>${app.y}${cs}</span>
      <span class="direction-badge ${dir}">${dirLabel}</span>
    </li>`;
  }).join('');
}

let _transChartName = null;
let _transChartBabyFreq = null;
let _transChartGender = null;
let _transSliderInitialized = false;

function _updateTransFill(s, e) {
  const MIN = 2000, MAX = 2024, RANGE = MAX - MIN;
  const fill      = document.getElementById('trans-year-fill');
  const fromLabel = document.getElementById('trans-year-from-label');
  const toLabel   = document.getElementById('trans-year-to-label');
  if (fromLabel) fromLabel.textContent = s;
  if (toLabel)   toLabel.textContent   = e;
  if (fill) {
    fill.style.left  = ((s - MIN) / RANGE * 100) + '%';
    fill.style.right = ((MAX - e) / RANGE * 100) + '%';
  }
}

function _initTransYearSlider() {
  if (_transSliderInitialized) return;
  _transSliderInitialized = true;
  const fromEl = document.getElementById('trans-year-from');
  const toEl   = document.getElementById('trans-year-to');
  fromEl.addEventListener('input', () => {
    if (parseInt(fromEl.value) > parseInt(toEl.value)) fromEl.value = toEl.value;
    const s = parseInt(fromEl.value), e = parseInt(toEl.value);
    _updateTransFill(s, e);
    if (!_transChartName) return;
    const transRate = getTransRateByYear(_transChartName, _transChartGender, s, e);
    renderTransVsBabyChart('explorer-trans-chart', _transChartName, transRate, _transChartBabyFreq, _transChartGender, s, e);
  });
  toEl.addEventListener('input', () => {
    if (parseInt(toEl.value) < parseInt(fromEl.value)) toEl.value = fromEl.value;
    const s = parseInt(fromEl.value), e = parseInt(toEl.value);
    _updateTransFill(s, e);
    if (!_transChartName) return;
    const transRate = getTransRateByYear(_transChartName, _transChartGender, s, e);
    renderTransVsBabyChart('explorer-trans-chart', _transChartName, transRate, _transChartBabyFreq, _transChartGender, s, e);
  });
}

function renderTransVsBabySection(name, babyFreq, transAppearances) {
  const section = document.getElementById('explorer-trans-chart-section');
  const cs = getCurveSummary(name);
  const gender = cs?.gender;

  // Only show for gendered names (F or M) that have trans records
  if (!gender || gender === 'N' || !transAppearances.length) {
    section.classList.add('hidden');
    return;
  }

  const transRate = getTransRateByYear(name, gender);
  const hasAnyRecords = transRate.some(([, n]) => n > 0);
  if (!hasAnyRecords) {
    section.classList.add('hidden');
    return;
  }

  _transChartName = name;
  _transChartBabyFreq = babyFreq;
  _transChartGender = gender;
  _initTransYearSlider();

  // Reset slider to full span when switching names
  const fromEl = document.getElementById('trans-year-from');
  const toEl   = document.getElementById('trans-year-to');
  fromEl.value = 2000;
  toEl.value   = 2024;
  _updateTransFill(2000, 2024);

  section.classList.remove('hidden');
  const dirLabel  = gender === 'F' ? 'Female trans' : 'Male trans';
  const dirLabel2 = gender === 'F' ? 'female-coded' : 'male-coded';
  document.getElementById('explorer-trans-label').textContent = dirLabel;
  const lbl2 = document.getElementById('explorer-trans-label2');
  if (lbl2) lbl2.textContent = dirLabel2;

  renderTransVsBabyChart('explorer-trans-chart', name, transRate, babyFreq, gender, 2000, 2024);
}

/** Called from main.js to restore name from URL */
export function restoreFromUrl() {
  const hash = location.hash;
  if (hash.startsWith('#explorer?name=')) {
    const name = decodeURIComponent(hash.split('=')[1]);
    if (name) setTimeout(() => loadName(name), 100);
  }
}
