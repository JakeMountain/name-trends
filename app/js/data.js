/**
 * data.js — loads and indexes all JSON data files
 *
 * All functions return data from module-level cache after first load.
 * Call loadAll() before using any other function.
 */

const _cache = {
  summary: null,
  babyNames: null,       // {NAME: [[year, rel_freq], ...]}
  nameChanges: null,     // [{n, y, d, cs}, ...]
  correlation: null,     // [{name, lag, r, p, is_trans, dir}, ...]
  curveSummary: null,    // {NAME: {mean_cs, n, dir, is_trans}}
};

// Indexes built once after load
const _idx = {
  changesByName: null,    // Map<name, [{y, d, cs}]>
  correlationByName: null, // Map<name, {lag, r, p, dir, is_trans}>
  allNames: null,          // sorted string[]
  mtfTotalByYear: null,    // Map<year, count> — all MTF records
  ftmTotalByYear: null,    // Map<year, count> — all FTM records
};

const DATA_FILES = [
  ['summary',      'data/summary.json'],
  ['babyNames',    'data/baby_names.json'],
  ['nameChanges',  'data/name_changes.json'],
  ['correlation',  'data/correlation.json'],
  ['curveSummary', 'data/curve_scores_summary.json'],
];

/**
 * Load all JSON files in parallel. Call once on app boot.
 * @param {function(number, number): void} onProgress - called with (loaded, total)
 */
export async function loadAll(onProgress) {
  let loaded = 0;
  const total = DATA_FILES.length;

  await Promise.all(DATA_FILES.map(async ([key, path]) => {
    const resp = await fetch(path);
    if (!resp.ok) throw new Error(`Failed to load ${path}: ${resp.status}`);
    _cache[key] = await resp.json();
    loaded++;
    if (onProgress) onProgress(loaded, total);
  }));

  _buildIndexes();
}

function _buildIndexes() {
  // changesByName: Map<NAME, [{y, d, cs}]>
  _idx.changesByName = new Map();
  for (const rec of _cache.nameChanges) {
    const name = rec.n;
    if (!_idx.changesByName.has(name)) _idx.changesByName.set(name, []);
    _idx.changesByName.get(name).push({ y: rec.y, d: rec.d, cs: rec.cs });
  }

  // mtfTotalByYear / ftmTotalByYear: Map<year, count>
  _idx.mtfTotalByYear = new Map();
  _idx.ftmTotalByYear = new Map();
  for (const rec of _cache.nameChanges) {
    if (rec.d >= 0.7) {
      _idx.mtfTotalByYear.set(rec.y, (_idx.mtfTotalByYear.get(rec.y) || 0) + 1);
    } else if (rec.d <= -0.7) {
      _idx.ftmTotalByYear.set(rec.y, (_idx.ftmTotalByYear.get(rec.y) || 0) + 1);
    }
  }

  // correlationByName: Map<NAME, {...}>
  _idx.correlationByName = new Map();
  for (const c of _cache.correlation) {
    _idx.correlationByName.set(c.name, c);
  }

  // allNames: sorted union of baby_names keys + gazette names
  const nameSet = new Set([
    ...Object.keys(_cache.babyNames),
    ..._idx.changesByName.keys(),
  ]);
  _idx.allNames = [...nameSet].sort();
}

export function getSummary() { return _cache.summary; }

export function getAllNames() { return _idx.allNames; }

/** @returns {[[number, number]]} array of [year, rel_freq] pairs or [] */
export function getBabyFreq(name) {
  return _cache.babyNames[name] || [];
}

/** @returns {{y, d, cs}[]} gazette appearances for this name (as new_first_name) */
export function getChangesByName(name) {
  return _idx.changesByName.get(name) || [];
}

/** @returns {object|null} correlation result */
export function getCorrelation(name) {
  return _idx.correlationByName.get(name) || null;
}

/** @returns {object|null} curve score summary */
export function getCurveSummary(name) {
  return (_cache.curveSummary && _cache.curveSummary[name]) || null;
}

/**
 * Get all correlation records, optionally filtered.
 * @param {number} minAbsDelta - minimum |delta| for inclusion (based on direction)
 */
export function getCorrelationAll(minAbsDelta = 0) {
  if (minAbsDelta === 0) return _cache.correlation;
  // We don't have per-name mean delta in correlation.json; filter by is_trans flag
  // If minAbsDelta >= 0.7, restrict to is_trans entries
  if (minAbsDelta >= 0.7) return _cache.correlation.filter(c => c.is_trans);
  return _cache.correlation;
}

/**
 * Get all name change records, optionally filtered.
 * @param {string} direction - 'all'|'mtf'|'ftm'|'nontrans'
 * @param {string} search - substring match on name
 */
export function getNameChanges(direction = 'all', search = '') {
  let data = _cache.nameChanges;
  if (direction === 'mtf')     data = data.filter(r => r.d >= 0.7);
  if (direction === 'ftm')     data = data.filter(r => r.d <= -0.7);
  if (direction === 'nontrans') data = data.filter(r => Math.abs(r.d) < 0.1);
  if (search) {
    const q = search.toUpperCase();
    data = data.filter(r => r.n.includes(q));
  }
  return data;
}

/**
 * Get all curve summary entries, optionally filtered.
 */
export function getCurveSummaryAll(direction = 'all', minN = 1) {
  const entries = Object.entries(_cache.curveSummary || {});
  return entries
    .filter(([, v]) => v.n >= minN)
    .filter(([, v]) => {
      if (direction === 'mtf') return v.gender === 'F';
      if (direction === 'ftm') return v.gender === 'M';
      if (direction === 'trans') return v.is_trans;
      return true;
    });
}

/**
 * Per-year trans rate for a name: [[year, nameCount, totalForGender], ...] 2000–2018.
 * @param {string} name
 * @param {'F'|'M'} gender
 */
export function getTransRateByYear(name, gender, startYear = 2000, endYear = 2024) {
  const appearances = _idx.changesByName.get(name) || [];
  const totalsMap = gender === 'F' ? _idx.mtfTotalByYear : _idx.ftmTotalByYear;
  const isMatch = gender === 'F' ? d => d >= 0.7 : d => d <= -0.7;

  const result = [];
  for (let y = startYear; y <= endYear; y++) {
    const nameCount = appearances.filter(a => a.y === y && isMatch(a.d)).length;
    const total = totalsMap.get(y) || 0;
    result.push([y, nameCount, total]);
  }
  return result;
}
