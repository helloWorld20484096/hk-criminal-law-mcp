import createPubSub from './vendor/pub-sub-es.esm.js';

window.createPubSub = createPubSub;

const loadScript = (src) =>
  new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`Could not load ${src}`));
    document.head.appendChild(script);
  });

try {
  await loadScript('./vendor/regl.min.js');
  await loadScript('./vendor/regl-scatterplot.min.js');
} catch (error) {
  showFatal(error);
  throw error;
}

const createScatterplot = window.createScatterplot?.default;
if (typeof createScatterplot !== 'function') {
  showFatal(new Error('The map renderer did not initialize.'));
  throw new Error('createScatterplot unavailable');
}

const DATA_ROOT = './data';
const K = 12;
const NUMBER = new Intl.NumberFormat('en-HK');
const CRIMINAL_CAPS = new Set(['4', '8', '91', '134', '136', '200', '210', '212', '221', '226', '227', '232', '383']);
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

const state = {
  overview: null,
  clusters: [],
  clusterById: new Map(),
  clusterColorIndex: new Map(),
  colorByValue: [],
  meta: null,
  points: null,
  knn: null,
  n: 0,
  scatterplot: null,
  xScale: null,
  yScale: null,
  selected: null,
  selectedPoints: [],
  pair: null,
  matches: null,
  visible: null,
  filters: { query: '', lang: 'all', cap: 'all', cluster: 'all' },
  focusMode: false,
  focusSet: null,
  searchText: [],
  pairMap: new Map(),
  centroids: [],
  visibleClusterCounts: null,
  capCache: new Map(),
  theme: 'light',
  listRows: [],
  listPage: 0,
  listSort: 'cap',
  listFilter: '',
  internalSelection: false,
  labelsFrame: 0,
};

const el = {
  loading: $('#loading'),
  loadingTitle: $('#loading-title'),
  loadingDetail: $('#loading-detail'),
  loadingError: $('#loading-error'),
  loadingRetry: $('#loading-retry'),
  progressBar: $('#progress-bar'),
  subtitle: $('#subtitle'),
  search: $('#search'),
  searchClear: $('#search-clear'),
  searchCount: $('#search-count'),
  searchResults: $('#search-results'),
  capFilter: $('#cap-filter'),
  clusterFilter: $('#cluster-filter'),
  filterNote: $('#filter-note'),
  clusterCount: $('#cluster-count'),
  clusterLegend: $('#cluster-legend'),
  map: $('#map'),
  labels: $('#labels'),
  mapWrap: $('.map-wrap'),
  tooltip: $('#tooltip'),
  mapEmpty: $('#map-empty'),
  statusVisible: $('#status-visible'),
  statusSelected: $('#status-selected'),
  detail: $('#detail'),
  detailEmpty: $('#detail-empty'),
  detailContent: $('#detail-content'),
  detailCitation: $('#detail-citation'),
  detailLanguage: $('#detail-language'),
  detailTitle: $('#detail-title'),
  detailDoc: $('#detail-doc'),
  detailMeta: $('#detail-meta'),
  detailSource: $('#detail-source'),
  detailText: $('#detail-text'),
  detailClose: $('#detail-close'),
  btnCopy: $('#btn-copy'),
  btnLink: $('#btn-link'),
  btnPair: $('#btn-pair'),
  btnFocus: $('#btn-focus'),
  neighbourList: $('#neighbour-list'),
  provenanceList: $('#provenance-list'),
  selectionSummary: $('#selection-summary'),
  selectionCount: $('#selection-count'),
  selectionList: $('#selection-list'),
  selectionClear: $('#selection-clear'),
  selectionExport: $('#selection-export'),
  footerStatus: $('#footer-status'),
  footerSnapshot: $('#footer-snapshot'),
  sidebar: $('#sidebar'),
  sidebarBackdrop: $('#sidebar-backdrop'),
  btnFilters: $('#btn-filters'),
  btnList: $('#btn-list'),
  btnAbout: $('#btn-about'),
  btnTheme: $('#btn-theme'),
  listView: $('#list-view'),
  listBody: $('#list-body'),
  listSummary: $('#list-summary'),
  listSearch: $('#list-search'),
  listSort: $('#list-sort'),
  listExport: $('#list-export'),
  listPrev: $('#list-prev'),
  listNext: $('#list-next'),
  listPage: $('#list-page'),
  listClose: $('#list-close'),
  about: $('#about'),
  aboutBody: $('#about-body'),
  aboutClose: $('#about-close'),
};

function fmt(n) {
  return NUMBER.format(Number(n) || 0);
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function setLoading(title, detail, percent) {
  if (el.loadingTitle) el.loadingTitle.textContent = title;
  if (el.loadingDetail && detail) el.loadingDetail.textContent = detail;
  if (el.progressBar && Number.isFinite(percent)) el.progressBar.style.width = `${Math.max(0, Math.min(100, percent))}%`;
}

function showFatal(error) {
  const loading = document.getElementById('loading');
  if (!loading) return;
  loading.hidden = false;
  loading.classList.remove('is-hidden');
  const title = document.getElementById('loading-title');
  const detail = document.getElementById('loading-detail');
  const message = document.getElementById('loading-error');
  const retry = document.getElementById('loading-retry');
  if (title) title.textContent = 'The atlas could not start';
  if (detail) detail.textContent = 'The map renderer or data files could not be loaded.';
  if (message) {
    message.hidden = false;
    message.textContent = error?.message || String(error);
  }
  if (retry) {
    retry.hidden = false;
    retry.onclick = () => window.location.reload();
  }
}

function citationOf(index) {
  const cap = state.meta.c[index];
  const section = state.meta.s[index] || '';
  if (/^sch/i.test(section)) {
    return `Cap. ${cap} Sch. ${section.replace(/^sch/i, '')}`;
  }
  if (!section || section === 'document') return `Cap. ${cap}`;
  return `Cap. ${cap} s.${section}`;
}

function languageLabel(value) {
  return value === 'en' ? 'EN' : '中文';
}

function clusterOf(index) {
  return state.clusterById.get(state.meta.cl[index]) || state.clusterById.get(-1);
}

function normalizeQuery(value) {
  return value
    .toLowerCase()
    .replace(/[.,;:()[\]{}'"]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function makeScale() {
  let domain = [-1, 1];
  let range = [0, 1];
  const scale = (value) => {
    const span = domain[1] - domain[0] || 1;
    return range[0] + ((value - domain[0]) / span) * (range[1] - range[0]);
  };
  scale.domain = (next) => {
    if (next === undefined) return domain;
    domain = next;
    return scale;
  };
  scale.range = (next) => {
    if (next === undefined) return range;
    range = next;
    return scale;
  };
  return scale;
}

async function loadJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Could not load ${url} (${response.status})`);
  return response.json();
}

async function loadBinary(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Could not load ${url} (${response.status})`);
  return response.arrayBuffer();
}

function setupTheme() {
  let stored = null;
  try { stored = localStorage.getItem('hk-law-atlas-theme'); } catch { /* storage may be blocked */ }
  const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
  state.theme = stored || (prefersDark ? 'dark' : 'light');
  applyTheme(state.theme);
}

function applyTheme(theme) {
  state.theme = theme;
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#141513' : '#f2f4ef');
  try { localStorage.setItem('hk-law-atlas-theme', theme); } catch { /* storage may be blocked */ }
  const background = theme === 'dark' ? '#171916' : '#edf0e9';
  if (state.scatterplot) {
    state.scatterplot.set({
      backgroundColor: background,
      pointColorActive: theme === 'dark' ? '#ffffff' : '#111111',
      pointColorHover: theme === 'dark' ? '#ffffff' : '#111111',
    });
  }
  drawLabels();
}

async function loadData() {
  setLoading('Loading the atlas', 'Reading the corpus snapshot…', 4);
  const [overview, clustersPayload] = await Promise.all([
    loadJSON(`${DATA_ROOT}/overview.json`),
    loadJSON(`${DATA_ROOT}/clusters.json`),
  ]);
  state.overview = overview;
  state.clusters = clustersPayload.clusters || [];
  state.clusterById = new Map(state.clusters.map((cluster) => [cluster.id, cluster]));
  state.clusters.forEach((cluster, index) => {
    state.clusterColorIndex.set(cluster.id, index + 1);
  });
  state.colorByValue = ['#9ca3af', ...state.clusters.map((cluster) => cluster.color)];

  setLoading('Loading the atlas', 'Reading provision records…', 18);
  const metaChunks = Math.max(1, Number(overview.meta_chunks) || 1);
  let loadedChunks = 0;
  const metaParts = await Promise.all(
    Array.from({ length: metaChunks }, async (_, chunkIndex) => {
      const part = await loadJSON(`${DATA_ROOT}/meta-${chunkIndex}.json`);
      loadedChunks += 1;
      setLoading(
        'Loading the atlas',
        `Reading provision records (${loadedChunks}/${metaChunks})…`,
        18 + (28 * loadedChunks) / metaChunks,
      );
      return part;
    }),
  );
  const meta = {};
  for (const key of Object.keys(metaParts[0] || {})) {
    meta[key] = metaParts.flatMap((part) => part[key]);
  }
  state.meta = meta;
  state.n = meta.i.length;

  setLoading('Loading the atlas', 'Drawing the point cloud…', 46);
  const pointsBuffer = await loadBinary(`${DATA_ROOT}/points.bin`);
  state.points = new Float32Array(pointsBuffer);
  if (state.points.length !== state.n * 2) {
    throw new Error('points.bin does not match meta.json');
  }

  setLoading('Loading the atlas', 'Indexing nearest neighbours…', 66);
  try {
    const knnBuffer = await loadBinary(`${DATA_ROOT}/knn.bin`);
    state.knn = new Int32Array(knnBuffer);
    if (state.knn.length < state.n * K) state.knn = null;
  } catch (error) {
    state.knn = null;
    console.warn('Nearest-neighbour data unavailable', error);
  }

  setLoading('Loading the atlas', 'Preparing search and filters…', 82);
  buildIndexes();
  buildFilterOptions();
  buildClusterLegend();
  renderAbout();
  updateFooter();
  setLoading('Loading the atlas', 'Fitting the view…', 94);
}

function buildIndexes() {
  const { meta } = state;
  const searchText = new Array(state.n);
  const pairMap = new Map();
  const sums = new Map();
  for (let i = 0; i < state.n; i += 1) {
    searchText[i] = normalizeQuery(
      `${meta.h[i]} ${meta.d[i]} cap ${meta.c[i]} s ${meta.s[i]} ${meta.sn[i]}`,
    );
    const key = `${meta.c[i]}|${meta.k[i]}`;
    if (!pairMap.has(key)) pairMap.set(key, []);
    pairMap.get(key).push(i);
    const cluster = meta.cl[i];
    if (!sums.has(cluster)) sums.set(cluster, { x: 0, y: 0, n: 0, minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity });
    const sum = sums.get(cluster);
    const px = state.points[i * 2];
    const py = state.points[i * 2 + 1];
    sum.x += px;
    sum.y += py;
    sum.n += 1;
    sum.minX = Math.min(sum.minX, px);
    sum.maxX = Math.max(sum.maxX, px);
    sum.minY = Math.min(sum.minY, py);
    sum.maxY = Math.max(sum.maxY, py);
  }
  state.searchText = searchText;
  state.pairMap = pairMap;
  state.allIndices = Array.from({ length: state.n }, (_, index) => index);
  state.centroids = [...sums.entries()]
    .filter(([id]) => id >= 0)
    .map(([id, sum]) => {
      const cluster = state.clusterById.get(id);
      return {
        id,
        x: sum.x / sum.n,
        y: sum.y / sum.n,
        minX: sum.minX,
        maxX: sum.maxX,
        minY: sum.minY,
        maxY: sum.maxY,
        size: sum.n,
        label: cluster?.label_en || cluster?.label || `Cluster ${id}`,
        labelZh: cluster?.label_zh || cluster?.label || `群組 ${id}`,
        color: cluster?.color || '#9ca3af',
      };
    })
    .sort((a, b) => b.size - a.size);
}

function buildFilterOptions() {
  const caps = new Map();
  for (let i = 0; i < state.n; i += 1) {
    const cap = state.meta.c[i];
    if (!caps.has(cap)) caps.set(cap, state.meta.d[i]);
  }
  const capEntries = [...caps.entries()].sort((a, b) =>
    a[0].localeCompare(b[0], undefined, { numeric: true }),
  );
  const capFragment = document.createDocumentFragment();
  const allCap = document.createElement('option');
  allCap.value = 'all';
  allCap.textContent = 'All Cap. numbers';
  capFragment.appendChild(allCap);
  const criminal = document.createElement('option');
  criminal.value = '__criminal__';
  criminal.textContent = 'Core criminal law';
  capFragment.appendChild(criminal);
  for (const [cap, title] of capEntries) {
    const option = document.createElement('option');
    option.value = cap;
    option.textContent = `Cap. ${cap} — ${title || 'Untitled'}`;
    capFragment.appendChild(option);
  }
  el.capFilter.replaceChildren(capFragment);

  const clusterFragment = document.createDocumentFragment();
  const allCluster = document.createElement('option');
  allCluster.value = 'all';
  allCluster.textContent = 'All clusters';
  clusterFragment.appendChild(allCluster);
  for (const cluster of [...state.clusters].sort((a, b) => b.size - a.size)) {
    const option = document.createElement('option');
    option.value = String(cluster.id);
    option.textContent = `${cluster.label || `Cluster ${cluster.id}`} (${fmt(cluster.size)})`;
    clusterFragment.appendChild(option);
  }
  el.clusterFilter.replaceChildren(clusterFragment);
  const noiseSize = state.clusters.find((c) => c.id === -1)?.size || 0;
  el.clusterCount.textContent = `${state.clusters.filter((c) => c.id >= 0).length} groups${noiseSize ? ` · ${fmt(noiseSize)} unclustered` : ''}`;
}

function buildClusterLegend() {
  const fragment = document.createDocumentFragment();
  const orderedClusters = [...state.clusters].filter((c) => c.id >= 0).sort((a, b) => b.size - a.size);
  const noiseCluster = state.clusters.find((c) => c.id === -1 && c.size > 0);
  if (noiseCluster) orderedClusters.push(noiseCluster);
  for (const cluster of orderedClusters) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'cluster-item';
    button.dataset.cluster = String(cluster.id);
    button.title = `${cluster.label_en || cluster.label}${cluster.label_zh ? ` · ${cluster.label_zh}` : ''}`;
    const swatch = document.createElement('span');
    swatch.className = 'cluster-swatch';
    swatch.style.background = cluster.color;
    const label = document.createElement('span');
    label.className = 'cluster-label';
    label.textContent = state.filters.lang === 'zh'
      ? (cluster.label_zh || cluster.label)
      : (cluster.label_en || cluster.label);
    const size = document.createElement('span');
    size.className = 'cluster-size';
    size.textContent = fmt(cluster.size);
    button.append(swatch, label, size);
    button.addEventListener('click', () => {
      const next = state.filters.cluster === String(cluster.id) ? 'all' : String(cluster.id);
      state.filters.cluster = next;
      el.clusterFilter.value = next;
      applyFilters();
    });
    fragment.appendChild(button);
  }
  el.clusterLegend.replaceChildren(fragment);
  markActiveCluster();
}

function markActiveCluster() {
  for (const button of $$('.cluster-item', el.clusterLegend)) {
    button.classList.toggle('is-active', button.dataset.cluster === state.filters.cluster);
  }
}

async function setupScatterplot() {
  const rect = el.map.getBoundingClientRect();
  state.xScale = makeScale();
  state.yScale = makeScale();
  const background = state.theme === 'dark' ? '#171916' : '#edf0e9';
  const dense = state.n > 50000;
  const baseSize = dense ? 1.2 : 2.35;
  const scheduleSize = dense ? 2.2 : 4.1;
  const selectedSize = dense ? 3.4 : 4.0;
  const baseOpacity = dense ? 0.55 : 0.9;
  state.pointSizes = { base: baseSize, schedule: scheduleSize };
  state.scatterplot = createScatterplot({
    canvas: el.map,
    width: Math.max(1, rect.width),
    height: Math.max(1, rect.height),
    xScale: state.xScale,
    yScale: state.yScale,
    pointSize: baseSize,
    pointSizeSelected: selectedSize,
    pointColor: state.colorByValue,
    pointColorActive: state.theme === 'dark' ? '#ffffff' : '#111111',
    pointColorHover: state.theme === 'dark' ? '#ffffff' : '#111111',
    backgroundColor: background,
    opacity: baseOpacity,
    lassoOnLongPress: true,
    lassoInitiator: false,
  });

  const { meta, points } = state;
  const x = new Float32Array(state.n);
  const y = new Float32Array(state.n);
  const valueA = new Float32Array(state.n);
  const valueB = new Float32Array(state.n);
  for (let i = 0; i < state.n; i += 1) {
    x[i] = points[i * 2];
    y[i] = points[i * 2 + 1];
    valueA[i] = state.clusterColorIndex.get(meta.cl[i]) || 0;
    valueB[i] = /^sch/i.test(meta.s[i] || '') ? 1 : 0;
  }
  await state.scatterplot.draw(
    { x, y, valueA, valueB },
    { zDataType: 'categorical', wDataType: 'categorical' },
  );
  state.scatterplot.set({
    colorBy: 'valueA',
    pointColor: state.colorByValue,
    sizeBy: 'valueB',
    pointSize: [state.pointSizes.base, state.pointSizes.schedule],
  });
  state.scatterplot.zoomToArea({ x: -1, y: -1, width: 2, height: 2 }, { padding: 0.02 });
  drawLabels();

  state.scatterplot.subscribe('select', ({ points: selected }) => {
    if (state.internalSelection) return;
    if (selected?.length === 1) selectPoint(selected[0]);
    else if (selected?.length > 1) showSelection(selected);
    else clearSelection();
  });
  state.scatterplot.subscribe('deselect', () => {
    if (!state.internalSelection) clearSelection();
  });
  state.scatterplot.subscribe('pointover', (index) => showHover(index));
  state.scatterplot.subscribe('pointout', () => hideHover());
  state.scatterplot.subscribe('view', ({ xScale, yScale }) => {
    state.xScale = xScale;
    state.yScale = yScale;
    scheduleLabels();
  });

  const observer = new ResizeObserver(() => {
    const box = el.map.getBoundingClientRect();
    state.scatterplot.set({ width: Math.max(1, box.width), height: Math.max(1, box.height) });
    scheduleLabels();
  });
  observer.observe(el.mapWrap);
}

function scheduleLabels() {
  if (state.labelsFrame) return;
  state.labelsFrame = requestAnimationFrame(() => {
    state.labelsFrame = 0;
    drawLabels();
  });
}

function drawLabels() {
  const canvas = el.labels;
  if (!canvas || !state.xScale || !state.yScale) return;
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  if (canvas.width !== Math.round(rect.width * dpr) || canvas.height !== Math.round(rect.height * dpr)) {
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);
  const ink = cssVar('--ink');
  const mapBg = cssVar('--map-bg');
  const maxLabels = rect.width < 720 ? 8 : 18;
  const minSize = Math.max(12, Math.min(400, Math.round(state.n * 0.001)));
  const placed = [];
  for (const centroid of state.centroids.slice(0, maxLabels + 12)) {
    const visibleCount = state.visibleClusterCounts
      ? (state.visibleClusterCounts.get(centroid.id) || 0)
      : centroid.size;
    if (visibleCount < minSize) continue;
    const labelX = state.xScale((centroid.minX + centroid.maxX) / 2);
    let labelY = state.yScale(centroid.maxY + 0.025);
    if (labelY < 24) labelY = state.yScale(centroid.minY - 0.025);
    const x = state.xScale(centroid.x);
    const y = state.yScale(centroid.y);
    if (labelX < 20 || labelY < 20 || labelX > rect.width - 20 || labelY > rect.height - 20) continue;
    const rawLabel = (state.filters.lang === 'zh' ? centroid.labelZh : centroid.label).slice(0, 48);
    const fontSize = rect.width < 720 ? 10 : 11;
    ctx.font = `600 ${fontSize}px "Iowan Old Style", "Palatino Linotype", Georgia, serif`;
    let label = rawLabel;
    const maxWidth = Math.max(40, rect.width - 32);
    while (label.length > 4 && ctx.measureText(label).width > maxWidth) {
      label = `${label.slice(0, -2).trim()}…`;
    }
    const width = ctx.measureText(label).width;
    const textX = Math.max(8, Math.min(rect.width - width - 12, labelX - width / 2));
    const box = { x: textX - 6, y: labelY - 20, w: width + 12, h: 17 };
    if (box.x < 0 || box.y < 0 || box.x + box.w > rect.width || box.y + box.h > rect.height) {
      continue;
    }
    if (placed.some((other) => !(box.x + box.w < other.x || box.x > other.x + other.w || box.y + box.h < other.y || box.y > other.y + other.h))) {
      continue;
    }
    placed.push(box);
    ctx.fillStyle = centroid.color;
    ctx.beginPath();
    ctx.arc(x, y, 3.1, 0, Math.PI * 2);
    ctx.fill();
    ctx.lineWidth = 3.5;
    ctx.strokeStyle = mapBg;
    ctx.strokeText(label, textX, labelY - 8);
    ctx.fillStyle = ink;
    ctx.fillText(label, textX, labelY - 8);
    if (placed.length >= maxLabels) break;
  }
}

function showHover(index) {
  if (index === null || index === undefined || index < 0 || !state.xScale || !state.yScale) return;
  if (!window.matchMedia?.('(hover: hover)').matches) return;
  const x = state.xScale(state.points[index * 2]);
  const y = state.yScale(state.points[index * 2 + 1]);
  el.tooltip.hidden = false;
  el.tooltip.innerHTML = '';
  const cite = document.createElement('span');
  cite.className = 't-cite';
  cite.textContent = citationOf(index);
  const title = document.createElement('span');
  title.textContent = state.meta.h[index] || state.meta.d[index] || 'Untitled provision';
  el.tooltip.append(cite, title);
  const rect = el.mapWrap.getBoundingClientRect();
  el.tooltip.style.left = `${Math.min(rect.width - 230, Math.max(8, x + 12))}px`;
  el.tooltip.style.top = `${Math.min(rect.height - 60, Math.max(8, y - 12))}px`;
}

function hideHover() {
  el.tooltip.hidden = true;
}

function renderSearchResults() {
  const query = state.filters.query;
  el.searchClear.hidden = !query;
  $('.search-shell').classList.toggle('has-value', Boolean(query));
  if (!query) {
    el.searchCount.textContent = '';
    el.searchResults.innerHTML = '<p class="muted">Search by citation, heading, or phrase.</p>';
    return;
  }
  const matches = state.visible || [];
  el.searchCount.textContent = `${fmt(matches.length)}${state.matchesTruncated ? '+' : ''} match${matches.length === 1 ? '' : 'es'}`;
  if (!matches.length) {
    el.searchResults.innerHTML = '<p class="result-empty">No provisions match that search in the current filters.</p>';
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const index of matches.slice(0, 12)) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'result-item';
    button.setAttribute('role', 'option');
    const citation = document.createElement('span');
    citation.className = 'result-citation';
    citation.textContent = citationOf(index);
    const heading = document.createElement('span');
    heading.className = 'result-heading';
    heading.lang = state.meta.l[index] === 'en' ? 'en' : 'zh-Hant';
    heading.textContent = state.meta.h[index] || state.meta.d[index] || 'Untitled provision';
    const meta = document.createElement('span');
    meta.className = 'result-meta';
    meta.textContent = `${state.meta.d[index] || '—'} · ${languageLabel(state.meta.l[index])}`;
    button.append(citation, heading, meta);
    button.addEventListener('click', () => {
      selectPoint(index, { zoom: true });
      closeSidebar();
    });
    fragment.appendChild(button);
  }
  el.searchResults.replaceChildren(fragment);
}

function applyFilters() {
  const { filters, meta } = state;
  const hasFilter =
    filters.query ||
    filters.lang !== 'all' ||
    filters.cap !== 'all' ||
    filters.cluster !== 'all' ||
    state.focusMode;
  if (!hasFilter) {
    state.visible = null;
    state.visibleClusterCounts = null;
    state.focusSet = null;
    state.scatterplot?.unfilter({ preventEvent: true });
    updateStatus();
    updateFilterNote();
    renderSearchResults();
    scheduleLabels();
    if (state.selected !== null) {
      // Keep the current selection visible.
    }
    return;
  }
  const candidates = state.matches || null;
  const visible = [];
  const total = candidates ? candidates.length : state.n;
  for (let position = 0; position < total; position += 1) {
    const index = candidates ? candidates[position] : position;
    if (filters.lang === 'en' && meta.l[index] !== 'en') continue;
    if (filters.lang === 'zh' && meta.l[index] === 'en') continue;
    if (filters.cap === '__criminal__' && !CRIMINAL_CAPS.has(meta.c[index])) continue;
    if (filters.cap !== 'all' && filters.cap !== '__criminal__' && meta.c[index] !== filters.cap) continue;
    if (filters.cluster !== 'all' && String(meta.cl[index]) !== filters.cluster) continue;
    if (state.focusMode && state.focusSet && !state.focusSet.has(index)) continue;
    visible.push(index);
  }
  state.visible = visible;
  const visibleCounts = new Map();
  for (const index of visible) {
    const cluster = meta.cl[index];
    visibleCounts.set(cluster, (visibleCounts.get(cluster) || 0) + 1);
  }
  state.visibleClusterCounts = visibleCounts;
  if (visible.length) state.scatterplot?.filter(visible, { preventEvent: true });
  else state.scatterplot?.filter([], { preventEvent: true });
  if (state.selected !== null && !visible.includes(state.selected)) clearSelection();
  updateStatus();
  updateFilterNote();
  renderSearchResults();
  renderList();
  scheduleLabels();
  if (state.scatterplot && state.n) {
    // Keep the current camera; filtering should not move the view.
  }
}

function updateStatus() {
  const visible = state.visible ? state.visible.length : state.n;
  el.statusVisible.textContent = state.visible
    ? `${fmt(visible)} of ${fmt(state.n)} points`
    : `${fmt(state.n)} points`;
  el.footerStatus.textContent = `${fmt(state.n)} provisions · ${state.clusters.filter((c) => c.id >= 0).length} clusters`;
  if (state.selected !== null) {
    el.statusSelected.textContent = citationOf(state.selected);
  } else {
    el.statusSelected.textContent = 'Select a point to inspect';
  }
  el.mapEmpty.hidden = !(state.visible && state.visible.length === 0);
}

function updateFilterNote() {
  if (!state.visible) {
    el.filterNote.textContent = 'Showing the full corpus.';
  } else if (!state.visible.length) {
    el.filterNote.textContent = 'No provisions match these filters.';
  } else {
    el.filterNote.textContent = `${fmt(state.visible.length)} provisions in view.`;
  }
}

function clearFilters() {
  state.filters = { query: '', lang: 'all', cap: 'all', cluster: 'all' };
  state.matches = null;
  state.matchesTruncated = false;
  state.focusMode = false;
  state.focusSet = null;
  el.search.value = '';
  for (const button of $$('.segmented button')) {
    button.classList.toggle('is-active', button.dataset.lang === 'all');
    button.setAttribute('aria-pressed', String(button.dataset.lang === 'all'));
  }
  el.capFilter.value = 'all';
  el.clusterFilter.value = 'all';
  markActiveCluster();
  el.btnFocus.textContent = 'Focus neighbours';
  applyFilters();
  if (state.scatterplot) state.scatterplot.zoomToOrigin({ transition: true, transitionDuration: 250 });
}

function runSearch(value) {
  state.filters.query = value.trim();
  if (state.filters.query && window.matchMedia?.('(max-width: 820px)').matches) {
    openSidebar();
  }
  if (!state.filters.query) {
    state.matches = null;
    state.matchesTruncated = false;
    applyFilters();
    return;
  }
  const tokens = normalizeQuery(state.filters.query).split(' ').filter(Boolean);
  if (!tokens.length) {
    state.matches = null;
    applyFilters();
    return;
  }
  const matches = [];
  for (let i = 0; i < state.n; i += 1) {
    const text = state.searchText[i];
    if (tokens.every((token) => text.includes(token))) matches.push(i);
    if (matches.length >= 20000) break;
  }
  state.matches = matches;
  state.matchesTruncated = matches.length >= 20000;
  applyFilters();
}

function showSelection(points) {
  if (!points.length) return clearSelection();
  state.selectedPoints = points;
  state.selected = points.length === 1 ? points[0] : null;
  state.pair = null;
  if (points.length === 1) {
    selectPoint(points[0]);
    return;
  }
  el.detailContent.hidden = true;
  el.detailEmpty.hidden = true;
  el.selectionSummary.hidden = false;
  el.selectionCount.textContent = `${fmt(points.length)} selected`;
  const fragment = document.createDocumentFragment();
  for (const index of points.slice(0, 200)) {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'result-item';
    const citation = document.createElement('span');
    citation.className = 'result-citation';
    citation.textContent = citationOf(index);
    const heading = document.createElement('span');
    heading.className = 'result-heading';
    heading.textContent = state.meta.h[index] || 'Untitled provision';
    item.append(citation, heading);
    item.addEventListener('click', () => selectPoint(index, { zoom: true }));
    fragment.appendChild(item);
  }
  el.selectionList.replaceChildren(fragment);
  el.detail.classList.add('open');
  el.statusSelected.textContent = `${fmt(points.length)} selected`;
}

function selectPoint(index, { zoom = false } = {}) {
  if (index === null || index === undefined || index < 0 || index >= state.n) return;
  const pairKey = `${state.meta.c[index]}|${state.meta.k[index]}`;
  const candidates = state.pairMap.get(pairKey) || [];
  const pair = candidates.find((candidate) => state.meta.l[candidate] !== state.meta.l[index]) ?? null;
  const pairList = pair === null ? [] : [pair];
  state.selected = index;
  state.selectedPoints = [index];
  state.pair = pair;
  state.internalSelection = true;
  try {
    state.scatterplot?.select([index, ...pairList], { preventEvent: true });
  } finally {
    state.internalSelection = false;
  }
  if (zoom) {
    state.scatterplot?.zoomToPoints([index, ...pairList], {
      padding: 0.55,
      transition: true,
      transitionDuration: 320,
    });
  }
  el.detailContent.hidden = false;
  el.detailEmpty.hidden = true;
  el.selectionSummary.hidden = true;
  el.detail.classList.add('open');
  el.detailCitation.textContent = citationOf(index);
  el.detailLanguage.textContent = languageLabel(state.meta.l[index]);
  el.detailTitle.textContent = state.meta.h[index] || state.meta.d[index] || 'Untitled provision';
  el.detailTitle.lang = state.meta.l[index] === 'en' ? 'en' : 'zh-Hant';
  el.detailDoc.textContent = state.meta.d[index] || '';
  el.detailDoc.lang = state.meta.l[index] === 'en' ? 'en' : 'zh-Hant';
  el.detailSource.textContent = 'Official source';
  el.detailSource.href = `https://www.elegislation.gov.hk/hk/${state.meta.c[index]}!${state.meta.l[index] === 'en' ? 'en' : 'zh-Hant'}`;
  const cluster = clusterOf(index);
  const chips = [
    state.meta.p[index] ? `Part: ${state.meta.p[index]}` : null,
    state.meta.v[index] ? `Version: ${state.meta.v[index]}` : null,
    cluster ? cluster.label_en || cluster.label : 'Unclustered',
    pair !== null ? 'Bilingual pair' : null,
  ].filter(Boolean);
  el.detailMeta.replaceChildren(
    ...chips.map((text) => {
      const span = document.createElement('span');
      span.className = 'meta-chip';
      span.textContent = text;
      return span;
    }),
  );
  el.btnPair.hidden = pair === null;
  el.btnFocus.textContent = state.focusMode ? 'Show all' : 'Focus neighbours';
  el.detailText.textContent = '';
  el.detailText.dataset.point = String(index);
  el.detailText.lang = state.meta.l[index] === 'en' ? 'en' : 'zh-Hant';
  el.neighbourList.replaceChildren();
  renderProvenance(index, pair);
  setTab('text');
  loadProvisionText(index);
  renderNeighbours(index);
  el.statusSelected.textContent = `${citationOf(index)} · ${languageLabel(state.meta.l[index])}`;
  if (state.focusMode) {
    const focus = new Set([index]);
    if (state.knn) {
      for (let offset = 0; offset < K; offset += 1) {
        const neighbour = state.knn[index * K + offset];
        if (neighbour !== undefined) focus.add(neighbour);
      }
    }
    state.focusSet = focus;
    applyFilters();
    el.btnFocus.textContent = 'Show all';
  }
  history.replaceState(null, '', `#p=${index}`);
  if (window.matchMedia?.('(max-width: 820px)').matches) {
    closeSidebar();
  }
}

async function loadProvisionText(index) {
  const cap = state.meta.c[index];
  el.detailText.textContent = 'Loading provision text…';
  try {
    let payload = state.capCache.get(cap);
    if (!payload) {
      payload = await loadJSON(`${DATA_ROOT}/caps/${cap}.json`);
      state.capCache.set(cap, payload);
      if (state.capCache.size > 24) {
        const oldest = state.capCache.keys().next().value;
        state.capCache.delete(oldest);
      }
    }
    const section = payload.sections?.find((item) => Number(item.i) === index);
    if (el.detailText.dataset.point !== String(index)) return;
    if (section?.u) el.detailSource.href = section.u;
    el.detailText.textContent = section?.t || 'The provision text is not available in this snapshot.';
  } catch (error) {
    if (el.detailText.dataset.point !== String(index)) return;
    el.detailText.textContent = 'The provision text could not be loaded. Use the official source link above.';
  }
}

function renderNeighbours(index) {
  if (!state.knn) {
    el.neighbourList.innerHTML = '<p class="muted small">Nearest-neighbour data is not available in this build.</p>';
    return;
  }
  const fragment = document.createDocumentFragment();
  for (let offset = 0; offset < K; offset += 1) {
    const neighbour = state.knn[index * K + offset];
    if (neighbour === undefined || neighbour === index) continue;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'neighbour-item';
    const cite = document.createElement('span');
    cite.className = 'neighbour-cite';
    cite.textContent = citationOf(neighbour);
    const head = document.createElement('span');
    head.className = 'neighbour-head';
    head.textContent = state.meta.h[neighbour] || 'Untitled provision';
    const meta = document.createElement('span');
    meta.className = 'neighbour-meta';
    meta.textContent = `${languageLabel(state.meta.l[neighbour])} · ${state.meta.d[neighbour] || ''}`;
    button.append(cite, head, meta);
    button.addEventListener('click', () => selectPoint(neighbour, { zoom: true }));
    fragment.appendChild(button);
  }
  if (!fragment.childNodes.length) {
    const p = document.createElement('p');
    p.className = 'muted small';
    p.textContent = 'No neighbours available.';
    fragment.appendChild(p);
  }
  el.neighbourList.replaceChildren(fragment);
}

function renderProvenance(index, pair) {
  const cluster = clusterOf(index);
  const rows = [
    ['Source', state.overview?.coverage?.legislation || 'Current-version e-Legislation'],
    ['Version date', state.meta.v[index] || '—'],
    ['Language', languageLabel(state.meta.l[index])],
    ['Cluster', cluster ? `${cluster.label_en || cluster.label}${cluster.label_zh ? ` · ${cluster.label_zh}` : ''}` : 'Unclustered'],
    ['Point ID', String(index)],
    ['Snapshot', state.overview?.snapshot ? String(state.overview.snapshot).slice(0, 10) : '—'],
    ['Embedding model', state.overview?.model || '—'],
    ['Bilingual pair', pair === null || pair === undefined ? 'Not found' : citationOf(pair)],
  ];
  const fragment = document.createDocumentFragment();
  for (const [term, value] of rows) {
    const dt = document.createElement('dt');
    dt.textContent = term;
    const dd = document.createElement('dd');
    dd.textContent = value;
    fragment.append(dt, dd);
  }
  el.provenanceList.replaceChildren(fragment);
}

function setTab(name) {
  for (const tab of $$('.tab')) {
    const active = tab.id === `tab-${name}`;
    tab.classList.toggle('is-active', active);
    tab.setAttribute('aria-selected', String(active));
  }
  for (const pane of $$('.detail-pane')) {
    pane.hidden = pane.id !== `pane-${name}`;
  }
}

function clearSelection() {
  state.selected = null;
  state.selectedPoints = [];
  state.pair = null;
  state.internalSelection = true;
  try {
    state.scatterplot?.deselect({ preventEvent: true });
  } finally {
    state.internalSelection = false;
  }
  el.detailContent.hidden = true;
  el.detailEmpty.hidden = false;
  el.selectionSummary.hidden = true;
  el.detail.classList.remove('open');
  el.statusSelected.textContent = 'Select a point to inspect';
  history.replaceState(null, '', window.location.pathname + window.location.search);
}

function fitAll(transition = true) {
  if (!state.scatterplot) return;
  const points = state.visible && state.visible.length ? state.visible : state.allIndices;
  state.scatterplot.zoomToPoints(points, {
    padding: 0.06,
    transition,
    transitionDuration: 300,
  });
}

function toggleFocus() {
  if (state.selected === null) return;
  if (state.focusMode) {
    state.focusMode = false;
    state.focusSet = null;
    el.btnFocus.textContent = 'Focus neighbours';
    applyFilters();
    return;
  }
  const set = new Set([state.selected]);
  if (state.knn) {
    for (let offset = 0; offset < K; offset += 1) {
      const neighbour = state.knn[state.selected * K + offset];
      if (neighbour !== undefined) set.add(neighbour);
    }
  }
  state.focusMode = true;
  state.focusSet = set;
  el.btnFocus.textContent = 'Show all';
  applyFilters();
}

async function copyText(value, button, reset) {
  try {
    await navigator.clipboard.writeText(value);
    button.textContent = 'Copied';
  } catch {
    button.textContent = 'Copy failed';
  }
  setTimeout(() => { button.textContent = reset; }, 1200);
}

function exportIndices(points, filename) {
  if (!points.length) return;
  const lines = ['citation,heading,language,cluster,version,source'];
  for (const index of points) {
    const cluster = clusterOf(index);
    const row = [
      citationOf(index),
      state.meta.h[index] || '',
      state.meta.l[index],
      cluster?.label_en || cluster?.label || '',
      state.meta.v[index] || '',
      `https://www.elegislation.gov.hk/hk/${state.meta.c[index]}!${state.meta.l[index] === 'en' ? 'en' : 'zh-Hant'}`,
    ].map((value) => `"${String(value).replace(/"/g, '""')}"`);
    lines.push(row.join(','));
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function exportSelection() {
  const points = state.selectedPoints.length ? state.selectedPoints : state.visible || [];
  exportIndices(points, 'hk-law-atlas-selection.csv');
}

function openSidebar() {
  el.sidebar.classList.add('is-open');
  if (window.matchMedia?.('(max-width: 820px)').matches) el.sidebarBackdrop.hidden = false;
}
function closeSidebar() {
  el.sidebar.classList.remove('is-open');
  el.sidebarBackdrop.hidden = true;
}

function renderList() {
  if (el.listView.hidden) return;
  const source = state.visible || state.allIndices;
  const query = normalizeQuery(state.listFilter);
  let rows = source;
  if (query) {
    const tokens = query.split(' ').filter(Boolean);
    rows = source.filter((index) => tokens.every((token) => state.searchText[index].includes(token)));
  }
  rows = [...rows];
  if (state.listSort === 'cluster') {
    rows.sort((a, b) => state.meta.cl[a] - state.meta.cl[b] || a - b);
  } else if (state.listSort === 'version') {
    rows.sort((a, b) => String(state.meta.v[b]).localeCompare(String(state.meta.v[a])));
  } else {
    rows.sort((a, b) => state.meta.c[a].localeCompare(state.meta.c[b], undefined, { numeric: true }) || String(state.meta.s[a]).localeCompare(String(state.meta.s[b]), undefined, { numeric: true }));
  }
  state.listRows = rows;
  const pageSize = 50;
  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  state.listPage = Math.min(state.listPage, pages - 1);
  const start = state.listPage * pageSize;
  const pageRows = rows.slice(start, start + pageSize);
  el.listSummary.textContent = `${fmt(rows.length)} provisions · page ${state.listPage + 1} of ${fmt(pages)}`;
  el.listPage.textContent = `Page ${fmt(state.listPage + 1)} of ${fmt(pages)}`;
  el.listPrev.disabled = state.listPage === 0;
  el.listNext.disabled = state.listPage >= pages - 1;
  const fragment = document.createDocumentFragment();
  for (const index of pageRows) {
    const cluster = clusterOf(index);
    const tr = document.createElement('tr');
    const cite = document.createElement('td');
    cite.className = 'cell-cite';
    cite.textContent = citationOf(index);
    const heading = document.createElement('td');
    heading.className = 'cell-heading';
    heading.lang = state.meta.l[index] === 'en' ? 'en' : 'zh-Hant';
    heading.textContent = state.meta.h[index] || 'Untitled provision';
    const lang = document.createElement('td');
    lang.className = 'cell-muted';
    lang.textContent = languageLabel(state.meta.l[index]);
    const clusterCell = document.createElement('td');
    clusterCell.className = 'cell-muted';
    clusterCell.textContent = cluster?.label_en || cluster?.label || '—';
    const version = document.createElement('td');
    version.className = 'cell-muted';
    version.textContent = state.meta.v[index] || '—';
    tr.append(cite, heading, lang, clusterCell, version);
    tr.tabIndex = 0;
    tr.setAttribute('role', 'button');
    const openRow = () => { selectPoint(index, { zoom: true }); closeList(); };
    tr.addEventListener('click', openRow);
    tr.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openRow();
      }
    });
    fragment.appendChild(tr);
  }
  el.listBody.replaceChildren(fragment);
}

function openList() {
  el.listView.hidden = false;
  el.btnList.setAttribute('aria-pressed', 'true');
  state.listPage = 0;
  renderList();
}
function closeList() {
  el.listView.hidden = true;
  el.btnList.setAttribute('aria-pressed', 'false');
}

function openAbout() {
  el.about.hidden = false;
  el.aboutClose.focus?.();
}
function closeAbout() {
  el.about.hidden = true;
}

function renderAbout() {
  const overview = state.overview || {};
  const umap = overview.umap || {};
  const languages = overview.languages || {};
  const points = overview.points || state.n;
  const clusterCount = state.clusters.filter((cluster) => cluster.id >= 0).length;
  const clustering = overview.clustering || overview.hdbscan || {};
  const clusteringText = clustering.method === 'kmeans'
    ? `KMeans (${clustering.clusters || clusterCount} clusters)`
    : `HDBSCAN (${clustering.min_cluster_size || '—'} minimum cluster size)`;
  const body = el.aboutBody;
  body.innerHTML = `
    <p>This atlas places every current-version provision in the local Hong Kong legislation corpus on a two-dimensional semantic map. Provisions that are close in meaning tend to sit near one another. The map is a discovery aid, not a citator and not legal advice.</p>
    <div class="modal-stats">
      <div class="modal-stat"><strong>${fmt(points)}</strong><span>provisions</span></div>
      <div class="modal-stat"><strong>${fmt(overview.documents)}</strong><span>ordinances</span></div>
      <div class="modal-stat"><strong>${fmt(clusterCount)}</strong><span>semantic clusters</span></div>
    </div>
    <h3>How to read it</h3>
    <ul>
      <li><strong>Colour</strong> is an emergent cluster, not a legal category. Cluster labels are generated from the text and are provisional.</li>
      <li><strong>Distance</strong> is semantic similarity in the embedding space. It is not authority, treatment, or hierarchy.</li>
      <li><strong>Language</strong>: English and Traditional Chinese provisions are embedded together. Use the language filter or the bilingual-pair action.</li>
      <li><strong>Search</strong> covers headings, ordinance titles, citations, and the first part of each provision. Use the official source for the full text.</li>
      <li><strong>Shift-drag</strong> on a desktop to lasso; on mobile, long-press to lasso. Select a point to inspect its nearest provisions.</li>
    </ul>
    <h3>Data and method</h3>
    <p>${fmt(languages.en || 0)} English and ${fmt(languages['zh-Hant'] || 0)} Traditional Chinese provisions were embedded with <code>${overview.model || 'multilingual-e5-small'}</code> (${overview.embedding_dimension || 384} dimensions), reduced with PCA (50 components) and UMAP (${umap.n_neighbors || '—'} neighbours, min_dist ${umap.min_dist ?? '—'}), and clustered with ${clusteringText}. English and Chinese translations of the same provision are aligned in the embedding space (alpha ${overview.bilingual_alignment?.alpha ?? '—'}) so the map is organised by legal concept rather than language.</p>
    <p><strong>Snapshot:</strong> ${overview.snapshot ? String(overview.snapshot).slice(0, 10) : '—'} · <strong>Generated:</strong> ${overview.generated_at ? String(overview.generated_at).slice(0, 10) : '—'} · <strong>Noise points:</strong> ${fmt(overview.noise || 0)}</p>
    <h3>Coverage</h3>
    <ul>
      <li>Current-version legislation: complete for the indexed e-Legislation corpus.</li>
      <li>Historical versions: not embedded in this map; use <code>statute_history</code> in the MCP server.</li>
      <li>Judgments and citation treatment: not included in this map; the case-law graph is demand-driven.</li>
    </ul>
    <h3>Attribution and limits</h3>
    <p>Legislation is sourced from the Hong Kong Department of Justice e-Legislation XML on DATA.GOV.HK and is reproduced with attribution. This map is a research aid; check commencement, amendments, and judicial treatment against the official source before relying on a provision.</p>
    <div class="modal-disclaimer">${overview.disclaimer || 'Research aid, not legal advice. Verify every provision against the official source.'}</div>
  `;
}

function updateFooter() {
  const points = state.overview?.points || state.n;
  el.footerSnapshot.textContent = state.overview?.snapshot
    ? `Snapshot ${String(state.overview.snapshot).slice(0, 10)}`
    : 'Local snapshot';
  el.subtitle.textContent = `${fmt(points)} provisions · ${fmt(state.overview?.documents)} ordinances · ${fmt(state.clusters.filter((c) => c.id >= 0).length)} clusters`;
}

function setupUI() {
  let searchTimer = 0;
  let listTimer = 0;
  el.search.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => runSearch(el.search.value), 120);
  });
  el.search.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      clearTimeout(searchTimer);
      runSearch(el.search.value);
      const picks = state.visible || state.matches;
      if (picks?.length) selectPoint(picks[0], { zoom: true });
    }
  });
  el.searchClear.addEventListener('click', () => {
    el.search.value = '';
    runSearch('');
    el.search.focus();
  });
  for (const button of $$('.segmented button')) {
    button.addEventListener('click', () => {
      state.filters.lang = button.dataset.lang;
      for (const peer of $$('.segmented button')) peer.classList.toggle('is-active', peer === button);
      buildClusterLegend();
      applyFilters();
    });
  }
  el.capFilter.addEventListener('change', () => {
    state.filters.cap = el.capFilter.value;
    applyFilters();
  });
  el.clusterFilter.addEventListener('change', () => {
    state.filters.cluster = el.clusterFilter.value;
    markActiveCluster();
    applyFilters();
  });
  $('#clear-filters').addEventListener('click', clearFilters);
  $('#empty-reset').addEventListener('click', clearFilters);
  el.btnFilters.addEventListener('click', () => {
    if (el.sidebar.classList.contains('is-open')) closeSidebar();
    else openSidebar();
  });
  el.sidebarBackdrop.addEventListener('click', closeSidebar);
  el.btnList.addEventListener('click', () => (el.listView.hidden ? openList() : closeList()));
  el.btnAbout.addEventListener('click', openAbout);
  el.btnTheme.addEventListener('click', () => applyTheme(state.theme === 'dark' ? 'light' : 'dark'));
  el.detailClose.addEventListener('click', clearSelection);
  el.selectionClear.addEventListener('click', clearSelection);
  el.selectionExport.addEventListener('click', exportSelection);
  el.btnCopy.addEventListener('click', () => {
    if (state.selected === null) return;
    copyText(citationOf(state.selected), el.btnCopy, 'Copy citation');
  });
  el.btnLink.addEventListener('click', () => {
    copyText(window.location.href, el.btnLink, 'Copy link');
  });
  el.btnPair.addEventListener('click', () => {
    if (state.pair !== null && state.pair !== undefined) selectPoint(state.pair, { zoom: true });
  });
  el.btnFocus.addEventListener('click', toggleFocus);
  for (const tab of $$('.tab')) {
    tab.addEventListener('click', () => setTab(tab.id.replace('tab-', '')));
  }
  el.listClose.addEventListener('click', closeList);
  el.listSearch.addEventListener('input', () => {
    state.listFilter = el.listSearch.value;
    state.listPage = 0;
    clearTimeout(listTimer);
    listTimer = setTimeout(renderList, 140);
  });
  el.listExport.addEventListener('click', () => exportIndices(state.listRows, 'hk-law-atlas-list.csv'));
  el.listSort.addEventListener('change', () => {
    state.listSort = el.listSort.value;
    state.listPage = 0;
    renderList();
  });
  el.listPrev.addEventListener('click', () => {
    state.listPage = Math.max(0, state.listPage - 1);
    renderList();
  });
  el.listNext.addEventListener('click', () => {
    state.listPage += 1;
    renderList();
  });
  el.aboutClose.addEventListener('click', closeAbout);
  let sheetStartY = null;
  el.detail.addEventListener('touchstart', (event) => {
    if (!el.detail.classList.contains('open')) return;
    if (event.target.closest('.detail-head') || event.target === el.detail) {
      sheetStartY = event.touches[0]?.clientY ?? null;
    }
  }, { passive: true });
  el.detail.addEventListener('touchend', (event) => {
    if (sheetStartY === null) return;
    const endY = event.changedTouches[0]?.clientY ?? sheetStartY;
    if (endY - sheetStartY > 60) clearSelection();
    sheetStartY = null;
  }, { passive: true });
  el.about.addEventListener('click', (event) => {
    if (event.target === el.about) closeAbout();
  });
  $('#footer-about').addEventListener('click', (event) => {
    event.preventDefault();
    openAbout();
  });
  $('#zoom-in').addEventListener('click', () => state.scatterplot?.zoomToLocation([0, 0], 0.6, { transition: true }));
  $('#zoom-out').addEventListener('click', () => state.scatterplot?.zoomToLocation([0, 0], 2.2, { transition: true }));
  $('#zoom-fit').addEventListener('click', () => fitAll(true));
  document.addEventListener('keydown', (event) => {
    const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName);
    if (event.key === '/' && !typing) {
      event.preventDefault();
      el.search.focus();
    } else if (event.key === 'Escape') {
      if (!el.about.hidden) closeAbout();
      else if (!el.listView.hidden) closeList();
      else if (el.sidebar.classList.contains('is-open')) closeSidebar();
      else if (state.filters.query) {
        el.search.value = '';
        runSearch('');
      } else if (state.selected !== null) clearSelection();
    } else if ((event.key === 'l' || event.key === 'L') && !typing && !event.metaKey && !event.ctrlKey) {
      el.listView.hidden ? openList() : closeList();
    } else if ((event.key === 'f' || event.key === 'F') && !typing && !event.metaKey && !event.ctrlKey) {
      if (window.matchMedia?.('(max-width: 820px)').matches) openSidebar();
      else el.capFilter.focus();
    }
  });
  window.addEventListener('resize', () => {
    if (window.innerWidth > 820) closeSidebar();
  });
  window.addEventListener('orientationchange', () => {
    setTimeout(() => fitAll(false), 320);
  });
}

async function init() {
  try {
    setupTheme();
    await loadData();
    await setupScatterplot();
    setupUI();
    applyFilters();
    el.loading.classList.add('is-hidden');
    setTimeout(() => { el.loading.hidden = true; }, 250);
    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ''));
    if (hash.has('p')) {
      const index = Number(hash.get('p'));
      if (Number.isInteger(index) && index >= 0 && index < state.n) selectPoint(index, { zoom: true });
    }
    if ('serviceWorker' in navigator && location.protocol.startsWith('http')) {
      navigator.serviceWorker.register('./sw.js').catch(() => {});
    }
  } catch (error) {
    showFatal(error);
  }
}

init();
