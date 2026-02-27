/**
 * main.js — entry point, routing, tab rendering
 */

import { loadAll, getSummary, getCorrelationAll, getNameChanges, getCurveSummaryAll, getBabyFreq, getChangesByName } from './data.js';
import { renderLagBarOverview, renderLagScatter, renderViolinGroup, renderLineMulti, renderHistogramOverlay, renderDeltaVsCurve, renderDoseResponse, renderBarChart } from './charts.js';
import { initExplorer, loadName, restoreFromUrl } from './explorer.js';

// ──────────────────────────────────────────────
// Boot
// ──────────────────────────────────────────────

async function boot() {
  try {
    await loadAll((loaded, total) => {
      document.getElementById('loading-msg').textContent =
        `Loading data... (${loaded}/${total})`;
    });
  } catch (e) {
    document.getElementById('loading-msg').textContent =
      `Error loading data: ${e.message}. Make sure you are running via a local HTTP server.`;
    return;
  }

  document.getElementById('loading-overlay').classList.add('hidden');
  initRouter();
  initExplorer();
  initBrowse();
  initDataTable();
  initAbout();
  restoreFromUrl();
}

document.addEventListener('DOMContentLoaded', boot);

// ──────────────────────────────────────────────
// Routing
// ──────────────────────────────────────────────

const TABS = ['overview', 'explorer', 'browse', 'charts', 'data', 'about'];
let _activeTab = null;
let _vizRendered = {};

function initRouter() {
  window.addEventListener('hashchange', () => route());
  route();
}

function route() {
  const hash = location.hash.replace('#', '').split('?')[0] || 'overview';
  const tab = TABS.includes(hash) ? hash : 'overview';
  showTab(tab);
}

function showTab(tab) {
  if (_activeTab === tab && !location.hash.includes('?')) return;
  _activeTab = tab;

  TABS.forEach(t => {
    document.getElementById(`tab-${t}`)?.classList.toggle('active', t === tab);
    document.querySelector(`[data-tab="${t}"]`)?.classList.toggle('active', t === tab);
  });

  if (tab === 'overview' && !_vizRendered.overview) renderOverview();
  if (tab === 'charts') renderVizTab();
}

// ──────────────────────────────────────────────
// Overview Tab
// ──────────────────────────────────────────────

function renderOverview() {
  _vizRendered.overview = true;
  const s = getSummary();
  if (!s) return;

  // Stat cards
  document.getElementById('stat-total').textContent = s.total_scored.toLocaleString();
  document.getElementById('stat-trans').textContent = s.trans_records.toLocaleString();
  document.getElementById('stat-mtf').textContent = s.mtf_records.toLocaleString();
  document.getElementById('stat-ftm').textContent = s.ftm_records.toLocaleString();

  const lagSign = s.mean_lag_trans > 0 ? '+' : '';
  document.getElementById('stat-lag').textContent = lagSign + s.mean_lag_trans.toFixed(2) + 'y';
  document.getElementById('stat-curve').textContent = s.mean_curve_trans.toFixed(3);

  // Lag bar chart
  renderLagBarOverview('overview-lag-chart', s);

  // Chunk table
  const tbody = document.getElementById('chunk-tbody');
  if (tbody && s.chunk_breakdown) {
    tbody.innerHTML = s.chunk_breakdown.map(c => `
      <tr>
        <td>${c.period}</td>
        <td>${c.n.toLocaleString()}</td>
        <td style="color:${scoreColor(c.trans)}">${fmtScore(c.trans)}</td>
        <td style="color:${scoreColor(c.mtf)}">${fmtScore(c.mtf)}</td>
        <td style="color:${scoreColor(c.ftm)}">${fmtScore(c.ftm)}</td>
      </tr>`).join('');
  }
}

function scoreColor(v) {
  if (v == null) return 'var(--text-dim)';
  return v > 0.05 ? 'var(--positive)' : v < -0.05 ? 'var(--negative)' : 'var(--text-muted)';
}

function fmtScore(v) {
  if (v == null) return '—';
  return (v > 0 ? '+' : '') + v.toFixed(3);
}

// ──────────────────────────────────────────────
// Visualizations Tab
// ──────────────────────────────────────────────

function initVizSubnav() {
  document.querySelectorAll('.viz-subnav button').forEach(btn => {
    btn.addEventListener('click', () => {
      const panel = btn.dataset.panel;
      document.querySelectorAll('.viz-subnav button').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.viz-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`viz-${panel}`)?.classList.add('active');
      renderVizPanel(panel);
    });
  });
}

function renderVizTab() {
  if (!_vizRendered.subnav) {
    initVizSubnav();
    _vizRendered.subnav = true;
    // Activate first panel
    document.querySelector('.viz-subnav button')?.click();
  }
}

function renderVizPanel(panel) {
  if (_vizRendered[`viz-${panel}`]) return;
  _vizRendered[`viz-${panel}`] = true;

  const s = getSummary();
  const corr = getCorrelationAll();

  if (panel === 'lag') renderLagExplorerPanel(corr);
  if (panel === 'curve') renderCurvePanel();
  if (panel === 'dose') renderDoseResponse('viz-dose-chart', corr);
  if (panel === 'mtfftm') renderMtfFtm(corr);
  if (panel === 'pre2006') renderPre2006();
  if (panel === 'topnames') renderTopNames(s);
}

function renderLagExplorerPanel(corr) {
  const searchEl = document.getElementById('lag-search');
  const threshEl = document.getElementById('lag-threshold');
  const threshLabel = document.getElementById('lag-threshold-label');

  function redraw() {
    const q = (searchEl?.value || '').trim().toUpperCase();
    const thresh = parseFloat(threshEl?.value || '0');
    let data = thresh >= 0.7 ? corr.filter(c => c.is_trans) : corr;
    threshLabel && (threshLabel.textContent = thresh.toFixed(1));
    renderLagScatter('viz-lag-chart', data, q || null, name => {
      location.hash = 'explorer';
      setTimeout(() => loadName(name), 50);
    });
  }

  searchEl?.addEventListener('input', () => redraw());
  threshEl?.addEventListener('input', () => redraw());
  redraw();
}

function renderCurvePanel() {
  const changes = getNameChanges();

  // Panel 1: violin
  const mtfVals = changes.filter(r => r.d >= 0.7 && r.cs != null).map(r => r.cs);
  const ftmVals = changes.filter(r => r.d <= -0.7 && r.cs != null).map(r => r.cs);
  const nonVals = changes.filter(r => Math.abs(r.d) < 0.1 && r.cs != null).map(r => r.cs);
  renderViolinGroup('viz-curve-violin', [
    { label: 'Female (trans)', values: mtfVals, color: '#e45756' },
    { label: 'Male (trans)', values: ftmVals, color: '#4c78a8' },
    { label: 'Non-trans', values: nonVals, color: '#72b7b2' },
  ]);

  // Panel 2: mean by year
  const transByYear = _meanByYear(changes.filter(r => Math.abs(r.d) >= 0.7 && r.cs != null));
  const mtfByYear   = _meanByYear(changes.filter(r => r.d >= 0.7 && r.cs != null));
  const ftmByYear   = _meanByYear(changes.filter(r => r.d <= -0.7 && r.cs != null));
  renderLineMulti('viz-curve-year', [
    { name: 'All trans',     x: transByYear.x, y: transByYear.y, color: '#6366f1' },
    { name: 'Female (trans)', x: mtfByYear.x,   y: mtfByYear.y,   color: '#e45756', dash: 'dash' },
    { name: 'Male (trans)',   x: ftmByYear.x,   y: ftmByYear.y,   color: '#4c78a8', dash: 'dash' },
  ], 'Mean curve score by year (trans-coded records)', 'Year', 'Mean curve score (−1 behind curve, +1 ahead)',
  { yRange: [-0.5, 0.5] });

  // Panel 3: scatter vs delta
  renderDeltaVsCurve('viz-curve-scatter', changes);
}

function _meanByYear(records) {
  const byYear = {};
  for (const r of records) {
    if (!byYear[r.y]) byYear[r.y] = [];
    byYear[r.y].push(r.cs);
  }
  const years = Object.keys(byYear).map(Number).sort((a, b) => a - b);
  return {
    x: years,
    y: years.map(y => byYear[y].reduce((s, v) => s + v, 0) / byYear[y].length),
  };
}

function renderMtfFtm(corr) {
  const mtfLags = corr.filter(c => c.dir === 'MTF').map(c => c.lag);
  const ftmLags = corr.filter(c => c.dir === 'FTM').map(c => c.lag);
  renderHistogramOverlay('viz-mtfftm-chart', [
    { name: 'Female (trans)', values: mtfLags, color: '#e45756' },
    { name: 'Male (trans)',   values: ftmLags, color: '#4c78a8' },
  ], 'Lag distribution: female vs male trans names');

  // Stats box
  const mtfMean = mtfLags.reduce((s, v) => s + v, 0) / mtfLags.length;
  const ftmMean = ftmLags.reduce((s, v) => s + v, 0) / ftmLags.length;
  const statsEl = document.getElementById('viz-mtfftm-stats');
  if (statsEl) {
    statsEl.innerHTML = `
      <p><strong>Female (trans)</strong> n=${mtfLags.length}, mean lag=${mtfMean.toFixed(2)}y</p>
      <p><strong>Male (trans)</strong> n=${ftmLags.length}, mean lag=${ftmMean.toFixed(2)}y</p>
      <p class="text-muted" style="font-size:11px;margin-top:6px;">
        Note: Welch t-test p=0.21 (not significant). Female trans lead likely artifactual — see About tab.
      </p>`;
  }
}

function renderPre2006() {
  const changes = getNameChanges();
  const corr = getCorrelationAll();

  // Build year of first gazette appearance per name
  const firstYear = {};
  for (const r of changes) {
    if (!(r.n in firstYear) || r.y < firstYear[r.n]) firstYear[r.n] = r.y;
  }

  const pre  = corr.filter(c => (firstYear[c.name] || 2010) < 2006).map(c => c.lag);
  const post = corr.filter(c => (firstYear[c.name] || 2010) >= 2006).map(c => c.lag);

  renderHistogramOverlay('viz-pre2006-chart', [
    { name: 'Pre-2006', values: pre, color: '#f58518' },
    { name: 'Post-2006', values: post, color: '#4c78a8' },
  ], 'Lag distribution: pre vs post 2006 trans opt-out');

  const statsEl = document.getElementById('viz-pre2006-stats');
  if (statsEl && pre.length && post.length) {
    const preMean = pre.reduce((s, v) => s + v, 0) / pre.length;
    const postMean = post.reduce((s, v) => s + v, 0) / post.length;
    statsEl.innerHTML = `
      <p><strong>Pre-2006</strong> n=${pre.length}, mean lag=${preMean.toFixed(2)}y</p>
      <p><strong>Post-2006</strong> n=${post.length}, mean lag=${postMean.toFixed(2)}y</p>
      <p class="text-muted" style="font-size:11px;margin-top:6px;">
        Post-2006 data has trans opt-out bias — trans people can request non-publication.
      </p>`;
  }
}

function renderTopNames(s) {
  if (!s) return;
  const ahead = (s.top_ahead_names || []).map((n, i) => ({ name: n, score: 0.9 - i * 0.08 }));
  const behind = (s.top_behind_names || []).map((n, i) => ({ name: n, score: -0.9 + i * 0.05 }));

  renderBarChart('viz-topnames-ahead', ahead, 'Most ahead-of-curve trans names', name => {
    location.hash = 'explorer';
    setTimeout(() => loadName(name), 50);
  });
  renderBarChart('viz-topnames-behind', behind, 'Most behind-curve trans names', name => {
    location.hash = 'explorer';
    setTimeout(() => loadName(name), 50);
  });
}

// ──────────────────────────────────────────────
// Browse Tab
// ──────────────────────────────────────────────

let _browseData = [];
let _browseShown = 48;
const BROWSE_PAGE = 48;

function initBrowse() {
  const dirEl = document.getElementById('browse-dir');
  const sortEl = document.getElementById('browse-sort');
  const minEl = document.getElementById('browse-min');
  const searchEl = document.getElementById('browse-search');
  const loadMoreEl = document.getElementById('browse-loadmore');

  function refresh() {
    const dir = dirEl?.value || 'all';
    const sort = sortEl?.value || 'curve_desc';
    const minN = parseInt(minEl?.value || '3', 10);
    const q = (searchEl?.value || '').trim().toUpperCase();
    buildBrowseData(dir, sort, q, minN);
    _browseShown = BROWSE_PAGE;
    renderBrowseGrid();
  }

  dirEl?.addEventListener('change', refresh);
  sortEl?.addEventListener('change', refresh);
  minEl?.addEventListener('change', refresh);
  searchEl?.addEventListener('input', () => {
    clearTimeout(searchEl._t);
    searchEl._t = setTimeout(refresh, 200);
  });

  loadMoreEl?.addEventListener('click', () => {
    _browseShown += BROWSE_PAGE;
    renderBrowseGrid();
  });

  refresh();
}

function buildBrowseData(dir, sort, q, minN = 3) {
  let entries = getCurveSummaryAll(dir, minN);
  if (q) entries = entries.filter(([n]) => n.includes(q));

  entries.sort(([, a], [, b]) => {
    if (sort === 'curve_desc') return (b.mean_cs ?? -999) - (a.mean_cs ?? -999);
    if (sort === 'curve_asc')  return (a.mean_cs ?? 999) - (b.mean_cs ?? 999);
    if (sort === 'count_desc') return b.n - a.n;
    return a[0].localeCompare(b[0]); // alpha
  });

  _browseData = entries;
}

function renderBrowseGrid() {
  const grid = document.getElementById('browse-grid');
  const loadMoreEl = document.getElementById('browse-loadmore');
  if (!grid) return;

  const slice = _browseData.slice(0, _browseShown);
  grid.innerHTML = slice.map(([name, v]) => {
    const gLabel = v.gender === 'F' ? 'Female' : v.gender === 'M' ? 'Male' : 'Neutral';
    const gClass = v.gender === 'F' ? 'female' : v.gender === 'M' ? 'male' : 'neutral';
    const cs = v.mean_cs;
    const csSign = cs > 0 ? '+' : '';
    const csCls = cs > 0.05 ? 'positive' : cs < -0.05 ? 'negative' : 'neutral';
    return `<div class="name-card" data-name="${name}" title="Click to explore ${name}">
      <div class="name-text">${name}</div>
      <div class="name-meta">
        <span class="direction-badge ${gClass}">${gLabel}</span>
        <span class="curve-score-mini ${csCls}">${csSign}${cs.toFixed(2)}</span>
      </div>
      <div class="record-count">${v.n} record${v.n !== 1 ? 's' : ''}</div>
    </div>`;
  }).join('');

  grid.querySelectorAll('.name-card').forEach(card => {
    card.addEventListener('click', () => {
      location.hash = 'explorer';
      setTimeout(() => loadName(card.dataset.name), 50);
    });
  });

  if (loadMoreEl) {
    loadMoreEl.style.display = _browseShown < _browseData.length ? 'block' : 'none';
    loadMoreEl.textContent = `Load more (${_browseData.length - _browseShown} remaining)`;
  }

  const countEl = document.getElementById('browse-count');
  if (countEl) countEl.textContent = `${_browseData.length.toLocaleString()} names`;
}

// ──────────────────────────────────────────────
// Data Table Tab
// ──────────────────────────────────────────────

let _tableData = [];
let _tableSorted = [];
let _tablePage = 0;
const TABLE_PAGE = 50;
let _tableSort = { col: 'y', dir: 'desc' };
let _tableDir = 'all';
let _tableSearch = '';

function initDataTable() {
  const searchEl = document.getElementById('data-search');
  const dirEl = document.getElementById('data-dir');
  const csvBtn = document.getElementById('data-csv');

  searchEl?.addEventListener('input', () => {
    clearTimeout(searchEl._t);
    searchEl._t = setTimeout(() => {
      _tableSearch = (searchEl.value || '').trim().toUpperCase();
      applyTableFilters();
    }, 200);
  });

  dirEl?.addEventListener('change', () => {
    _tableDir = dirEl.value;
    applyTableFilters();
  });

  document.querySelectorAll('#data-table thead th[data-col]').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (_tableSort.col === col) {
        _tableSort.dir = _tableSort.dir === 'asc' ? 'desc' : 'asc';
      } else {
        _tableSort.col = col;
        _tableSort.dir = 'desc';
      }
      document.querySelectorAll('#data-table thead th').forEach(h => {
        h.classList.remove('sort-asc', 'sort-desc');
      });
      th.classList.add(_tableSort.dir === 'asc' ? 'sort-asc' : 'sort-desc');
      applyTableSort();
    });
  });

  csvBtn?.addEventListener('click', exportCSV);

  // Load data lazily on first visit
  _tableData = getNameChanges();
  applyTableFilters();
}

function applyTableFilters() {
  let data = getNameChanges(_tableDir, _tableSearch);
  _tableData = data;
  applyTableSort();
}

function applyTableSort() {
  const { col, dir } = _tableSort;
  const mult = dir === 'asc' ? 1 : -1;
  _tableSorted = [..._tableData].sort((a, b) => {
    const av = col === 'n' ? a.n : col === 'y' ? a.y : col === 'd' ? a.d : (a.cs ?? -999);
    const bv = col === 'n' ? b.n : col === 'y' ? b.y : col === 'd' ? b.d : (b.cs ?? -999);
    if (col === 'n') return mult * a.n.localeCompare(b.n);
    return mult * (av - bv);
  });
  _tablePage = 0;
  renderTablePage();
}

function renderTablePage() {
  const tbody = document.getElementById('data-tbody');
  if (!tbody) return;

  const start = _tablePage * TABLE_PAGE;
  const slice = _tableSorted.slice(start, start + TABLE_PAGE);

  tbody.innerHTML = slice.map(r => {
    const dirCls = r.d >= 0.7 ? 'mtf' : r.d <= -0.7 ? 'ftm' : 'neutral';
    const dirLabel = r.d >= 0.7 ? 'Female' : r.d <= -0.7 ? 'Male' : '—';
    const csCls = r.cs == null ? 'null' : r.cs > 0.05 ? 'positive' : r.cs < -0.05 ? 'negative' : 'neutral';
    const csText = r.cs == null ? '—' : (r.cs > 0 ? '+' : '') + r.cs.toFixed(3);
    return `<tr>
      <td><a href="#explorer?name=${r.n}" class="name-link" style="color:var(--accent);text-decoration:none">${r.n}</a></td>
      <td>${r.y}</td>
      <td><span class="delta-badge ${dirCls}">${dirLabel} ${r.d > 0 ? '+' : ''}${r.d.toFixed(2)}</span></td>
      <td class="cs-cell ${csCls}">${csText}</td>
    </tr>`;
  }).join('');

  // Wire name links
  tbody.querySelectorAll('.name-link').forEach(a => {
    a.addEventListener('click', e => {
      e.preventDefault();
      const name = a.textContent;
      location.hash = 'explorer';
      setTimeout(() => loadName(name), 50);
    });
  });

  // Pagination
  const total = _tableSorted.length;
  const totalPages = Math.ceil(total / TABLE_PAGE);
  document.getElementById('data-page-info').textContent =
    `${(start + 1).toLocaleString()}–${Math.min(start + TABLE_PAGE, total).toLocaleString()} of ${total.toLocaleString()}`;
  document.getElementById('data-prev').disabled = _tablePage === 0;
  document.getElementById('data-next').disabled = _tablePage >= totalPages - 1;
  document.getElementById('data-prev').onclick = () => { _tablePage--; renderTablePage(); };
  document.getElementById('data-next').onclick = () => { _tablePage++; renderTablePage(); };
}

function exportCSV() {
  const header = 'new_first_name,year,gender_delta,curve_score\n';
  const rows = _tableSorted.map(r =>
    `${r.n},${r.y},${r.d},${r.cs ?? ''}`
  ).join('\n');
  const blob = new Blob([header + rows], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'ontario_name_changes.csv';
  a.click();
}

// ──────────────────────────────────────────────
// About Tab
// ──────────────────────────────────────────────

async function initAbout() {
  const el = document.getElementById('about-content');
  if (!el) return;
  try {
    const resp = await fetch('report.md');
    if (!resp.ok) throw new Error('not found');
    const md = await resp.text();
    // marked.js is loaded via CDN in index.html
    el.innerHTML = typeof marked !== 'undefined'
      ? marked.parse(md)
      : `<pre style="white-space:pre-wrap">${md}</pre>`;
  } catch {
    el.innerHTML = '<p class="text-muted">Report not loaded — see <code>docs/REPORT.md</code>.</p>';
  }
}
