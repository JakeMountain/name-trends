/**
 * charts.js — Plotly wrapper functions
 *
 * All functions accept a DOM element ID and data, render via Plotly.
 */

const LAYOUT_BASE = {
  paper_bgcolor: '#1a1d27',
  plot_bgcolor: '#1a1d27',
  font: { color: '#e2e8f0', family: 'system-ui, -apple-system, sans-serif', size: 12 },
  margin: { t: 36, r: 20, b: 50, l: 60 },
  legend: { bgcolor: 'rgba(0,0,0,0)', bordercolor: '#2e3044', borderwidth: 1 },
  xaxis: { gridcolor: '#2e3044', zerolinecolor: '#52596e', zerolinewidth: 1.5 },
  yaxis: { gridcolor: '#2e3044', zerolinecolor: '#52596e', zerolinewidth: 1.5 },
};

const CONFIG = {
  displayModeBar: true,
  modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
  displaylogo: false,
  responsive: true,
};

const COLORS = {
  mtf: '#e45756',
  ftm: '#4c78a8',
  neutral: '#72b7b2',
  accent: '#6366f1',
  muted: '#5a6478',
  positive: '#54a24b',
  negative: '#e45756',
};

function layout(overrides = {}) {
  // Deep-clone LAYOUT_BASE so merging overrides never mutates the base object.
  return mergeDeep(JSON.parse(JSON.stringify(LAYOUT_BASE)), overrides);
}

function mergeDeep(target, ...sources) {
  for (const src of sources) {
    for (const [k, v] of Object.entries(src)) {
      if (v && typeof v === 'object' && !Array.isArray(v) && target[k] && typeof target[k] === 'object') {
        mergeDeep(target[k], v);
      } else {
        target[k] = v;
      }
    }
  }
  return target;
}

/**
 * Line chart: baby name frequency over time, with gazette appearance overlays.
 * @param {string} elId
 * @param {string} name
 * @param {[number, number][]} babyFreq  - [[year, rel_freq], ...]
 * @param {{y: number, d: number}[]} appearances - gazette appearances
 * @param {string} compareName  - optional second name
 * @param {[number, number][]} compareFreq - optional second series
 */
export function renderBabyTrendChart(elId, name, babyFreq, appearances, compareName, compareFreq) {
  const traces = [];

  if (babyFreq.length) {
    traces.push({
      x: babyFreq.map(r => r[0]),
      y: babyFreq.map(r => r[1] * 1000),
      type: 'scatter', mode: 'lines',
      name: name,
      line: { color: COLORS.accent, width: 2 },
      hovertemplate: '%{x}: %{y:.2f} per 1,000<extra>' + name + '</extra>',
    });
  }

  if (compareName && compareFreq && compareFreq.length) {
    traces.push({
      x: compareFreq.map(r => r[0]),
      y: compareFreq.map(r => r[1] * 1000),
      type: 'scatter', mode: 'lines',
      name: compareName,
      line: { color: COLORS.neutral, width: 2, dash: 'dash' },
      hovertemplate: '%{x}: %{y:.2f} per 1,000<extra>' + compareName + '</extra>',
    });
  }

  // Gazette appearance markers as vertical shapes
  const shapes = appearances.map(app => {
    const color = app.d >= 0.7 ? COLORS.mtf : app.d <= -0.7 ? COLORS.ftm : COLORS.muted;
    return {
      type: 'line', x0: app.y, x1: app.y, yref: 'paper', y0: 0, y1: 1,
      line: { color, width: 1.5, dash: 'dot' },
    };
  });

  const l = layout({
    title: { text: `Baby name frequency: ${name}`, font: { size: 14 } },
    xaxis: { title: 'Year', range: [1913, 2024] },
    yaxis: { title: 'Births per 1,000', tickformat: '.2f' },
    shapes,
    showlegend: compareName ? true : false,
  });

  Plotly.react(elId, traces, l, CONFIG);
}

/**
 * Lag scatter: x=best_lag, y=name (sorted), coloured by trans/non-trans.
 * @param {string} elId
 * @param {object[]} corrData - [{name, lag, r, p, is_trans, dir}]
 * @param {string} highlightName - name to highlight (others dimmed)
 * @param {function} onClick - called with (name) when a point is clicked
 */
export function renderLagScatter(elId, corrData, highlightName, onClick) {
  const sorted = [...corrData].sort((a, b) => a.lag - b.lag);
  const names = sorted.map(d => d.name);
  const lags = sorted.map(d => d.lag);
  const sig = sorted.map(d => d.p < 0.05);

  const opacity = highlightName
    ? sorted.map(d => d.name === highlightName ? 1 : 0.2)
    : sorted.map((d, i) => sig[i] ? 0.85 : 0.3);

  const size = sorted.map((d, i) => sig[i] ? 8 : 5);
  const color = sorted.map(d => {
    if (d.dir === 'MTF') return COLORS.mtf;
    if (d.dir === 'FTM') return COLORS.ftm;
    return d.is_trans ? COLORS.neutral : COLORS.muted;
  });

  const trace = {
    x: lags, y: names,
    type: 'scatter', mode: 'markers',
    marker: { color, size, opacity },
    text: sorted.map(d => `${d.name} | lag=${d.lag}y | r=${d.r.toFixed(3)} | p=${d.p.toFixed(3)}`),
    hovertemplate: '%{text}<extra></extra>',
    customdata: sorted.map(d => d.name),
  };

  const l = layout({
    title: { text: 'Cross-correlation lag by name', font: { size: 13 } },
    xaxis: { title: 'Best lag (years)', zeroline: true },
    yaxis: { visible: false },
    height: Math.max(400, sorted.length * 5 + 80),
    margin: { l: 20, r: 20, t: 36, b: 50 },
    showlegend: false,
  });

  const el = document.getElementById(elId);
  Plotly.react(el, [trace], l, CONFIG);

  if (onClick) {
    el.removeAllListeners && el.removeAllListeners('plotly_click');
    el.on('plotly_click', e => {
      if (e.points && e.points[0]) onClick(e.points[0].customdata);
    });
  }
}

/**
 * Horizontal bar chart for top/bottom names.
 * @param {string} elId
 * @param {{name: string, score: number}[]} data - sorted
 * @param {string} title
 * @param {function} onClick
 */
export function renderBarChart(elId, data, title, onClick) {
  const color = data.map(d => d.score >= 0 ? COLORS.positive : COLORS.negative);
  const trace = {
    x: data.map(d => d.score),
    y: data.map(d => d.name),
    type: 'bar', orientation: 'h',
    marker: { color },
    text: data.map(d => d.score.toFixed(3)),
    textposition: 'outside',
    hovertemplate: '%{y}: %{x:.4f}<extra></extra>',
    customdata: data.map(d => d.name),
  };

  const l = layout({
    title: { text: title, font: { size: 13 } },
    xaxis: { title: 'Mean curve score', range: [-1.1, 1.1] },
    yaxis: { autorange: 'reversed', showticklabels: true, tickfont: { color: '#e2e8f0' } },
    margin: { l: 160, r: 70, t: 36, b: 50 },
    height: Math.max(300, data.length * 24 + 80),
  });

  const el = document.getElementById(elId);
  Plotly.react(el, [trace], l, CONFIG);

  if (onClick) {
    el.on('plotly_click', e => {
      if (e.points && e.points[0]) onClick(e.points[0].customdata);
    });
  }
}

/**
 * Violin plot for curve score distributions.
 * @param {string} elId
 * @param {{label: string, values: number[], color: string}[]} groups
 */
export function renderViolinGroup(elId, groups) {
  const traces = groups.map(g => ({
    type: 'violin', y: g.values,
    name: g.label,
    fillcolor: g.color,
    line: { color: g.color },
    opacity: 0.7,
    meanline: { visible: true },
    box: { visible: true },
    hoverinfo: 'y+name',
  }));

  const l = layout({
    title: { text: 'Curve score distribution by group', font: { size: 13 } },
    yaxis: { title: 'Curve score', range: [-1.1, 1.1], zeroline: true },
    violingap: 0.3,
    showlegend: false,
  });

  Plotly.react(elId, traces, l, CONFIG);
}

/**
 * Multi-line chart.
 * @param {string} elId
 * @param {{name: string, x: number[], y: number[], color: string, dash?: string}[]} series
 * @param {string} title
 * @param {string} xLabel
 * @param {string} yLabel
 */
export function renderLineMulti(elId, series, title, xLabel, yLabel, opts = {}) {
  const traces = series.map(s => ({
    x: s.x, y: s.y,
    type: 'scatter', mode: 'lines+markers',
    name: s.name,
    line: { color: s.color, width: 2, dash: s.dash || 'solid' },
    marker: { size: 5 },
    hovertemplate: `${s.name} %{x}: %{y:.3f}<extra></extra>`,
  }));

  const l = layout({
    title: { text: title, font: { size: 13 } },
    xaxis: { title: xLabel },
    yaxis: { title: yLabel, zeroline: true, ...(opts.yRange ? { range: opts.yRange } : {}) },
    showlegend: true,
  });

  Plotly.react(elId, traces, l, CONFIG);
}

/**
 * Overlaid histograms.
 * @param {string} elId
 * @param {{name: string, values: number[], color: string}[]} series
 * @param {string} title
 */
export function renderHistogramOverlay(elId, series, title) {
  const traces = series.map(s => ({
    x: s.values,
    type: 'histogram',
    name: s.name,
    opacity: 0.65,
    marker: { color: s.color },
    nbinsx: 21,
    hovertemplate: `${s.name} lag=%{x}: %{y}<extra></extra>`,
  }));

  const l = layout({
    title: { text: title, font: { size: 13 } },
    barmode: 'overlay',
    xaxis: { title: 'Best lag (years)', dtick: 2 },
    yaxis: { title: 'Count' },
    showlegend: true,
  });

  Plotly.react(elId, traces, l, CONFIG);
}

/**
 * Scatter: curve_score vs gender_delta, coloured by era.
 * @param {string} elId
 * @param {{d: number, cs: number, y: number}[]} records
 */
export function renderDeltaVsCurve(elId, records) {
  const chunks = [
    { label: '2000–04', lo: 2000, hi: 2004, color: '#e45756' },
    { label: '2005–09', lo: 2005, hi: 2009, color: '#f58518' },
    { label: '2010–14', lo: 2010, hi: 2014, color: '#54a24b' },
    { label: '2015–18', lo: 2015, hi: 2018, color: '#4c78a8' },
  ];

  const traces = chunks.map(ch => {
    const sub = records.filter(r => r.y >= ch.lo && r.y <= ch.hi && r.cs != null);
    return {
      x: sub.map(r => r.d),
      y: sub.map(r => r.cs),
      type: 'scatter', mode: 'markers',
      name: ch.label,
      marker: { color: ch.color, size: 3, opacity: 0.5 },
      hovertemplate: `δ=%{x:.2f} score=%{y:.3f}<extra>${ch.label}</extra>`,
    };
  });

  const l = layout({
    title: { text: 'Curve score vs gender delta', font: { size: 13 } },
    xaxis: { title: 'Gender delta (−1 = male name, +1 = female name)', zeroline: true, range: [-1.05, 1.05] },
    yaxis: { title: 'Curve score', zeroline: true, range: [-1.05, 1.05] },
    showlegend: true,
    height: 420,
  });

  Plotly.react(elId, traces, l, CONFIG);
}

/**
 * Dose-response: |delta| threshold vs mean lag.
 * @param {string} elId
 * @param {object[]} corrData
 */
export function renderDoseResponse(elId, corrData) {
  const thresholds = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9];
  const x = [], y = [], counts = [];
  for (const t of thresholds) {
    const sub = corrData.filter(d => Math.abs(d.mean_delta ?? 0) >= t);
    if (!sub.length) continue;
    x.push(t);
    y.push(sub.reduce((s, d) => s + d.lag, 0) / sub.length);
    counts.push(sub.length);
  }

  const trace = {
    x, y,
    type: 'scatter', mode: 'lines+markers',
    marker: { color: COLORS.accent, size: 8 },
    line: { color: COLORS.accent, width: 2 },
    text: counts.map(c => `n=${c}`),
    hovertemplate: '|δ| ≥ %{x}: mean lag = %{y:.2f}y (%{text})<extra></extra>',
  };

  const l = layout({
    title: { text: 'Mean lag vs |gender delta| threshold', font: { size: 13 } },
    xaxis: { title: 'Min |gender delta| (0 = all names, 0.7 = strongly trans-coded)', range: [-0.05, 1.0] },
    yaxis: { title: 'Mean best lag (years)', zeroline: true },
  });

  Plotly.react(elId, [trace], l, CONFIG);
}

/**
 * Horizontal bar chart for overview lag comparison.
 */
export function renderLagBarOverview(elId, summary) {
  const groups = ['All changes', 'Trans-coded', 'Female (trans)', 'Male (trans)'];
  const values = [
    summary.mean_lag_all,
    summary.mean_lag_trans,
    summary.mean_lag_mtf || 1.71,
    summary.mean_lag_ftm || 0.78,
  ];
  const colors = values.map(v => v > 0 ? COLORS.positive : COLORS.negative);

  const trace = {
    x: values,
    y: groups,
    type: 'bar', orientation: 'h',
    marker: { color: colors },
    text: values.map(v => (v > 0 ? '+' : '') + v.toFixed(2) + 'y'),
    textposition: 'outside',
    hovertemplate: '%{y}: %{x:.2f} years<extra></extra>',
  };

  const l = layout({
    title: { text: 'Mean cross-correlation lag by group', font: { size: 13 } },
    xaxis: { title: 'Mean best lag (years)', zeroline: true, range: [-1, 2.5] },
    yaxis: { autorange: 'reversed' },
    margin: { l: 110, r: 80, t: 36, b: 50 },
    height: 220,
    annotations: [{
      x: 0, y: 4.5, xref: 'x', yref: 'y',
      text: '← behind trends | ahead of trends →',
      showarrow: false, font: { size: 10, color: '#5a6478' },
    }],
  });

  Plotly.react(elId, [trace], l, CONFIG);
}

/**
 * Bar chart: trans name rate vs baby name rate.
 * @param {string} elId
 * @param {string} name
 * @param {[number, number, number][]} transData - [[year, nameCount, totalForGender], ...]
 * @param {[number, number][]} babyFreq - [[year, rel_freq], ...]
 * @param {'F'|'M'} gender
 * @param {number} startYear
 * @param {number} endYear
 */
export function renderTransVsBabyChart(elId, name, transData, babyFreq, gender, startYear = 2000, endYear = 2024) {
  const filtered = transData.filter(row => row[0] >= startYear && row[0] <= endYear);
  const transTotal = filtered.reduce((s, row) => s + row[2], 0);
  const transCount = filtered.reduce((s, row) => s + row[1], 0);
  const transRate  = transTotal > 0 ? (transCount / transTotal) * 1000 : 0;

  const babyYears = babyFreq.filter(r => r[0] >= startYear && r[0] <= endYear);
  const babyRate  = babyYears.length > 0
    ? (babyYears.reduce((s, r) => s + r[1], 0) / babyYears.length) * 1000
    : 0;

  const transLabel = gender === 'F' ? 'Female trans' : 'Male trans';
  const transColor = gender === 'F' ? COLORS.mtf : COLORS.ftm;

  const trace = {
    x: [transLabel, 'Baby names'],
    y: [transRate, babyRate],
    type: 'bar',
    marker: { color: [transColor, COLORS.muted] },
    text: [transRate.toFixed(2), babyRate.toFixed(2)],
    textposition: 'outside',
    cliponaxis: false,
    hovertemplate: '%{x}: %{y:.2f} per 1,000<extra></extra>',
  };

  const rangeLabel = startYear === endYear ? `${startYear}` : `${startYear}–${endYear}`;
  const l = layout({
    xaxis: { type: 'category', title: `${name} — rate per 1,000 records (${rangeLabel})` },
    yaxis: { title: 'Per 1,000', zeroline: true },
    showlegend: false,
    height: 280,
    margin: { t: 40, r: 60, b: 60, l: 60 },
  });

  Plotly.react(elId, [trace], l, CONFIG);
}
