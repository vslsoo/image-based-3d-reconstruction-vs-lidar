"""HTML/CSS/JS template strings for build_performance_study_page.py.

Self-contained, no external libraries, theme-aware. Charts are hand-rolled log-log
line charts (SVG, rendered client-side from the embedded JSON so the same code path
draws all 6) plus one 100%-stacked bar for the pipeline-stage breakdown. Categorical
colors are the dataviz-skill validated 4-slot set (references/palette.md, adjacent-pair
order) — see METHOD_COLORVAR in the builder for the hue assignment.
"""

HTML_HEAD = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Compute cost vs frame count — time &amp; memory scaling across 4 reconstruction methods</title>
</head>
<body>
<style>
  /* forced light palette — matches the thesis-defense deck (index.html, white bg,
     forest-green accent), same values repeated in every theme block on purpose so it
     never flips dark, regardless of system prefers-color-scheme or a data-theme toggle.
     Chart series hues (--s-*) are unchanged from the dataviz-skill-validated set —
     those were already validated against a near-white surface. */
  :root {
    --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084;
    --accent:#17805f; --accent-soft:#d9ece3; --code-bg:#f5f4ef;
    --s-blue:#2a78d6; --s-orange:#eb6834; --s-aqua:#1baf7a; --s-yellow:#eda100;
    --grid:#ddd9cc; --canvas-surface:#ffffff;
    --warn:#a8621f; --warn-soft:#f0dcc4;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084;
      --accent:#17805f; --accent-soft:#d9ece3; --code-bg:#f5f4ef;
      --s-blue:#2a78d6; --s-orange:#eb6834; --s-aqua:#1baf7a; --s-yellow:#eda100;
      --grid:#ddd9cc; --canvas-surface:#ffffff; --warn:#a8621f; --warn-soft:#f0dcc4; }
  }
  :root[data-theme="dark"] { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084;
    --accent:#17805f; --accent-soft:#d9ece3; --code-bg:#f5f4ef;
    --s-blue:#2a78d6; --s-orange:#eb6834; --s-aqua:#1baf7a; --s-yellow:#eda100;
    --grid:#ddd9cc; --canvas-surface:#ffffff; --warn:#a8621f; --warn-soft:#f0dcc4; }
  :root[data-theme="light"] { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084;
    --accent:#17805f; --accent-soft:#d9ece3; --code-bg:#f5f4ef;
    --s-blue:#2a78d6; --s-orange:#eb6834; --s-aqua:#1baf7a; --s-yellow:#eda100;
    --grid:#ddd9cc; --canvas-surface:#ffffff; --warn:#a8621f; --warn-soft:#f0dcc4; }

  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; line-height:1.45; }
  .page { max-width:1320px; margin:0 auto; padding:28px 24px 72px; display:flex; flex-direction:column; gap:26px; }
  a { color:var(--accent); }
  .eyebrow { font-size:11.5px; font-weight:600; letter-spacing:.09em; text-transform:uppercase; color:var(--accent); }
  h1 { font-size:23px; font-weight:650; margin:4px 0 2px; letter-spacing:-.01em; }
  h2 { font-size:18px; font-weight:650; margin:0 0 2px; }
  h3 { font-size:14px; font-weight:650; margin:0; }
  .subtitle { color:var(--text-dim); font-size:13.5px; max-width:92ch; }
  .mono { font-family:ui-monospace,"SF Mono","Cascadia Code",Menlo,Consolas,monospace; font-variant-numeric:tabular-nums; }
  section { display:flex; flex-direction:column; gap:14px; }
  hr.sep { border:none; border-top:1px solid var(--panel-border); margin:2px 0; }

  .scope-box { font-size:12.5px; color:var(--text-dim); background:var(--code-bg); border:1px solid var(--panel-border); border-radius:10px; padding:12px 16px; display:flex; flex-direction:column; gap:6px; }
  .scope-box b { color:var(--text); }
  .pending-badge { display:inline-block; font-size:10.5px; font-weight:650; color:var(--warn); border:1px solid color-mix(in srgb, var(--warn) 55%, transparent); background:var(--warn-soft); border-radius:5px; padding:1px 7px; margin-left:4px; }

  .obj-block { display:flex; flex-direction:column; gap:14px; padding:18px; border:1px solid var(--panel-border); border-radius:14px; background:color-mix(in srgb, var(--panel) 60%, transparent); }
  .obj-head { display:flex; flex-wrap:wrap; align-items:baseline; gap:6px 14px; }
  .obj-head .chip { font-size:11px; color:var(--text-dim); background:var(--code-bg); border:1px solid var(--panel-border); border-radius:20px; padding:2px 10px; }

  .chart-row { display:grid; grid-template-columns:repeat(auto-fit, minmax(320px,1fr)); gap:16px; }
  .chart-card { background:var(--panel); border:1px solid var(--panel-border); border-radius:12px; padding:12px 14px 10px; display:flex; flex-direction:column; gap:6px; position:relative; }
  .chart-title { font-size:12.5px; font-weight:650; color:var(--text); }
  .chart-sub { font-size:10.5px; color:var(--text-faint); }
  .chart-svg-wrap { position:relative; }
  svg.chart { width:100%; height:auto; display:block; overflow:visible; }
  .legend { display:flex; flex-wrap:wrap; gap:10px 16px; font-size:11px; color:var(--text-dim); }
  .legend .item { display:flex; align-items:center; gap:5px; }
  .legend .key { width:14px; height:2px; border-radius:1px; display:inline-block; }
  .legend .dot { width:8px; height:8px; border-radius:50%; display:inline-block; }

  .tooltip { position:absolute; pointer-events:none; background:var(--panel); border:1px solid var(--panel-border);
    border-radius:8px; padding:7px 10px; font-size:11px; box-shadow:0 4px 16px rgba(0,0,0,.15); z-index:5; opacity:0; transition:opacity .08s; min-width:130px; }
  .tooltip .n { font-weight:650; color:var(--text); margin-bottom:3px; }
  .tooltip .row { display:flex; justify-content:space-between; gap:14px; }
  .tooltip .row .key { width:10px; height:2px; margin-right:5px; display:inline-block; vertical-align:1px; }
  .tooltip .row .val { font-weight:650; font-variant-numeric:tabular-nums; }

  table.data { border-collapse:collapse; font-size:11.5px; min-width:640px; }
  table.data th, table.data td { padding:5px 9px; border-bottom:1px solid var(--panel-border); text-align:right; white-space:nowrap; }
  table.data th { font-weight:650; color:var(--text-dim); position:sticky; top:0; background:var(--panel); }
  table.data td.txt, table.data th.txt { text-align:left; }
  table.data tbody tr:hover { background:color-mix(in srgb, var(--accent-soft) 45%, transparent); }
  .grid-wrap { overflow-x:auto; }
  details.table-toggle { font-size:12px; }
  details.table-toggle summary { cursor:pointer; color:var(--accent); font-weight:600; padding:4px 0; }

  .stagebar-row { display:flex; align-items:center; gap:10px; }
  .stagebar-label { width:130px; font-size:12px; font-weight:600; flex-shrink:0; }
  .stagebar-track { flex:1; height:26px; border-radius:6px; overflow:hidden; display:flex; background:var(--code-bg); }
  .stagebar-seg { height:100%; display:flex; align-items:center; justify-content:center; font-size:10px; color:#fff; font-weight:600; border-right:2px solid var(--panel); }
  .stagebar-seg:last-child { border-right:none; }
  .stage-legend { display:flex; flex-wrap:wrap; gap:8px 16px; font-size:11px; color:var(--text-dim); }

  .interp { background:var(--panel); border:1px solid var(--panel-border); border-radius:12px; padding:18px 20px; display:flex; flex-direction:column; gap:11px;
    box-shadow:0 1px 2px rgba(24,26,23,0.05), 0 1px 8px rgba(24,26,23,0.03); }
  .interp .headline { color:var(--accent); font-size:15px; font-weight:650; }
  .interp ul { margin:2px 0 0; padding-left:18px; font-size:13px; color:var(--text-dim); }
  .interp li { margin:5px 0; }
  .interp b { color:var(--text); }
  .interp .win { color:var(--accent); }

  .caveat { font-size:12px; color:var(--text-faint); border-left:3px solid var(--warn); padding:4px 0 4px 12px; }

  footer { color:var(--text-faint); font-size:11px; padding-top:4px; }
</style>

<div class="page">
  <div>
    <div class="eyebrow">Compute cost · time &amp; memory vs frame count</div>
    <h1>Does reconstruction cost grow with the number of photos — and how, per method?</h1>
    <div class="subtitle">
      Same NVIDIA L40S pod for every run (<span id="hw-ram">…</span> GiB RAM ceiling, <span id="hw-vram">…</span> MiB VRAM),
      so time and memory numbers are directly comparable across methods. Growth-with-N claims below
      are restricted to <b>controlled sweeps</b> — same object, same capture, same
      frame-selection algorithm, only N changes — everything else (cross-object
      comparisons, single points) is kept in a separately-labeled appendix.
    </div>
    <div class="caveat" style="margin-top:10px; max-width:96ch">
      <b>The methods are not doing equally hard work.</b> COLMAP detects features at 3200&nbsp;px and runs
      dense stereo at 3024&nbsp;px; hloc detects at 1024&nbsp;px; both feed-forward models operate at
      roughly 512&nbsp;px — about a sixth of COLMAP's linear resolution, so around a thirtieth of the
      pixels. Every speed and memory advantage below has to be read against that. It is a deliberate
      property of the methods as published, left untuned rather than equalised, and a limitation of this
      comparison rather than a finding of it.
    </div>
  </div>

  <div class="scope-box" id="scope-box"></div>

  <hr class="sep">
  <section id="objects-root"></section>

  <hr class="sep">
  <section>
    <h2>Where the time actually goes — pipeline stage share</h2>
    <div class="subtitle">Median % of total wall time per stage, across every successful run of that method (architecture-intrinsic, not restricted to the controlled sweep). 100%-stacked; segments &lt;6% carry their value in the legend/tooltip only.</div>
    <div id="stage-root" style="display:flex; flex-direction:column; gap:12px;"></div>
  </section>

  <hr class="sep">
  <section>
    <h2>Which stage actually drives the super-linear growth?</h2>
    <div class="subtitle">Per-stage power-law fit (stage time ~ N^b), controlled sweeps only (manual selection, both objects pooled on log N).</div>
    <div class="grid-wrap" id="stage-scaling-root"></div>
  </section>

  <hr class="sep">
  <section>
    <h2>Robustness check — the "even" (SIFT-overlap greedy) selection sweeps</h2>
    <div class="subtitle">Same N grid, a different (algorithmic instead of human) frame-selection method, COLMAP + MASt3R-GA only. Not charted — included to confirm the scaling exponents above aren't an artifact of the manual ranking.</div>
    <div class="grid-wrap" id="even-check-root"></div>
  </section>

  <hr class="sep">
  <section>
    <h2>Appendix — VGGT on other objects <span class="pending-badge">not a controlled sweep</span></h2>
    <div class="caveat" id="vggt-caveat"></div>
    <div class="grid-wrap" id="vggt-root"></div>
  </section>

  <hr class="sep">
  <section>
    <h2>Interpretation</h2>
    <div class="interp" id="interp"></div>
  </section>

  <footer id="footer-note">src/registration/build_performance_study_page.py · data: docs/tables/experiment_metrics.jsonl</footer>
</div>
"""


MAIN_JS = r"""<script>
const DATA = JSON.parse(document.getElementById('page-data').textContent);
const METHOD_LABEL = DATA.method_label;
const CHART_W = 620, CHART_H = 240;
const PAD = { l: 58, r: 150, t: 14, b: 30 };

function fmt(v, digits) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return Number(v).toLocaleString('en-US', { maximumFractionDigits: digits ?? 0, minimumFractionDigits: 0 });
}
function fmtTime(s) {
  if (s >= 3600) return (s/3600).toFixed(1) + 'h';
  if (s >= 90) return Math.round(s/60) + 'm';
  return Math.round(s) + 's';
}
function fmtMib(m) { return m >= 1024 ? (m/1024).toFixed(1) + ' GiB' : Math.round(m) + ' MiB'; }

// ---------- nice log-scale ticks: 1/2/5 * 10^k within [lo,hi] ----------
function niceLogTicks(lo, hi) {
  if (lo <= 0) lo = hi / 100;
  const out = [];
  const k0 = Math.floor(Math.log10(lo)) - 1, k1 = Math.ceil(Math.log10(hi)) + 1;
  for (let k = k0; k <= k1; k++) {
    for (const m of [1, 2, 5]) {
      const v = m * Math.pow(10, k);
      if (v >= lo * 0.92 && v <= hi * 1.08) out.push(v);
    }
  }
  return out;
}

// ---------- generic log-log line chart with hover crosshair ----------
function renderLineChart(container, opts) {
  // opts: { series:[{key,label,colorvar,dash,n:[],y:[]}], xTicks:[], yFmt(v), ceiling:{value,label}|null }
  const allY = [];
  opts.series.forEach(s => s.y.forEach(v => { if (v > 0) allY.push(v); }));
  if (opts.ceiling) allY.push(opts.ceiling.value);
  let yMin = Math.min(...allY), yMax = Math.max(...allY);
  if (yMin === yMax) { yMin *= 0.7; yMax *= 1.4; }
  const xMin = Math.min(...opts.xTicks), xMax = Math.max(...opts.xTicks);
  const px = n => PAD.l + (Math.log(n) - Math.log(xMin)) / (Math.log(xMax) - Math.log(xMin)) * (CHART_W - PAD.l - PAD.r);
  const py = v => (CHART_H - PAD.b) - (Math.log(v) - Math.log(yMin*0.85)) / (Math.log(yMax*1.2) - Math.log(yMin*0.85)) * (CHART_H - PAD.b - PAD.t);

  const yTicks = niceLogTicks(yMin*0.85, yMax*1.2);
  let svg = '';
  // gridlines (y)
  yTicks.forEach(t => {
    const y = py(t);
    svg += `<line x1="${PAD.l}" y1="${y}" x2="${CHART_W-PAD.r}" y2="${y}" stroke="var(--grid)" stroke-width="1"/>`;
    svg += `<text x="${PAD.l-6}" y="${y+3}" text-anchor="end" font-size="9" fill="var(--text-faint)">${opts.yFmt(t)}</text>`;
  });
  // gridlines (x)
  opts.xTicks.forEach(n => {
    const x = px(n);
    svg += `<line x1="${x}" y1="${PAD.t}" x2="${x}" y2="${CHART_H-PAD.b}" stroke="var(--grid)" stroke-width="1" opacity="0.5"/>`;
    svg += `<text x="${x}" y="${CHART_H-PAD.b+12}" text-anchor="middle" font-size="9" fill="var(--text-faint)">${n}</text>`;
  });
  svg += `<text x="${CHART_W/2}" y="${CHART_H-2}" text-anchor="middle" font-size="9.5" fill="var(--text-dim)">N (frames)</text>`;

  // ceiling reference line
  if (opts.ceiling) {
    const y = py(opts.ceiling.value);
    svg += `<line x1="${PAD.l}" y1="${y}" x2="${CHART_W-PAD.r}" y2="${y}" stroke="var(--text-faint)" stroke-width="1.4" stroke-dasharray="4 3"/>`;
    svg += `<text x="${CHART_W-PAD.r}" y="${y-4}" text-anchor="end" font-size="9" fill="var(--text-faint)">${opts.ceiling.label}</text>`;
  }

  // series lines + points
  const endLabels = []; // collected first, laid out after (collision avoidance)
  opts.series.forEach(s => {
    const pts = s.n.map((n,i) => [px(n), py(s.y[i])]);
    if (pts.length >= 2) {
      const d = pts.map((p,i) => (i===0?'M':'L') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
      const dash = s.dash ? ` stroke-dasharray="${s.dash}"` : '';
      svg += `<path d="${d}" fill="none" stroke="var(${s.colorvar})" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"${dash}/>`;
    }
    pts.forEach(p => {
      svg += `<circle cx="${p[0]}" cy="${p[1]}" r="6" fill="var(--canvas-surface)"/>`;
      svg += `<circle cx="${p[0]}" cy="${p[1]}" r="4" fill="var(${s.colorvar})"/>`;
    });
    if (pts.length) {
      const last = pts[pts.length-1];
      const partial = s.n.length < opts.nExpected ? ' (partial)' : '';
      endLabels.push({ x: last[0], py0: last[1], y: last[1], colorvar: s.colorvar, text: s.label + partial });
    }
  });

  // direct end labels: sort by data y, then push apart any that would collide
  // (dataviz skill: "when end-labels collide, don't stack them" - nudge + leader line)
  endLabels.sort((a,b) => a.y - b.y);
  const MIN_GAP = 12;
  for (let i = 1; i < endLabels.length; i++) {
    if (endLabels[i].y - endLabels[i-1].y < MIN_GAP) endLabels[i].y = endLabels[i-1].y + MIN_GAP;
  }
  const yCap = CHART_H - PAD.b - 2;
  for (let i = endLabels.length - 1; i >= 0; i--) {
    if (endLabels[i].y > yCap) { endLabels[i].y = yCap; if (i > 0) endLabels[i-1].y = Math.min(endLabels[i-1].y, yCap - MIN_GAP); }
  }
  endLabels.forEach(lb => {
    if (Math.abs(lb.y - lb.py0) > 1.5) {
      // nudged off its data point - draw a thin leader line so the label still traces back
      svg += `<line x1="${lb.x+2}" y1="${lb.py0}" x2="${lb.x+7}" y2="${lb.y}" stroke="var(${lb.colorvar})" stroke-width="1" opacity="0.55"/>`;
    }
    svg += `<line x1="${lb.x+7}" y1="${lb.y}" x2="${lb.x+19}" y2="${lb.y}" stroke="var(${lb.colorvar})" stroke-width="2"/>`;
    svg += `<text x="${lb.x+22}" y="${lb.y+3}" font-size="9.5" fill="var(--text-dim)">${lb.text}</text>`;
  });

  const svgId = 'svg-' + Math.random().toString(36).slice(2);
  container.innerHTML = `<div class="chart-svg-wrap"><svg class="chart" id="${svgId}" viewBox="0 0 ${CHART_W} ${CHART_H}">${svg}
    <line class="crosshair" x1="0" y1="${PAD.t}" x2="0" y2="${CHART_H-PAD.b}" stroke="var(--text-dim)" stroke-width="1" opacity="0"/>
  </svg><div class="tooltip"></div></div>`;

  const svgEl = container.querySelector('svg');
  const crosshair = container.querySelector('.crosshair');
  const tooltip = container.querySelector('.tooltip');
  const wrap = container.querySelector('.chart-svg-wrap');

  function handleMove(evt) {
    const rect = svgEl.getBoundingClientRect();
    const relX = (evt.clientX - rect.left) / rect.width * CHART_W;
    let nearest = opts.xTicks[0], best = Infinity;
    opts.xTicks.forEach(n => { const d = Math.abs(px(n) - relX); if (d < best) { best = d; nearest = n; } });
    const x = px(nearest);
    crosshair.setAttribute('x1', x); crosshair.setAttribute('x2', x); crosshair.setAttribute('opacity', '0.5');
    let rows = '';
    opts.series.forEach(s => {
      const i = s.n.indexOf(nearest);
      if (i === -1) return;
      rows += `<div class="row"><span><span class="key" style="background:var(${s.colorvar})"></span>${s.label}</span><span class="val">${opts.yFmt(s.y[i])}</span></div>`;
    });
    if (!rows) { tooltip.style.opacity = 0; return; }
    tooltip.innerHTML = `<div class="n">N = ${nearest}</div>${rows}`;
    tooltip.style.opacity = 1;
    const wrapRect = wrap.getBoundingClientRect();
    const px_ = x / CHART_W * wrapRect.width;
    let left = px_ + 10;
    if (left + 150 > wrapRect.width) left = px_ - 150;
    tooltip.style.left = left + 'px';
    tooltip.style.top = '4px';
  }
  svgEl.addEventListener('pointermove', handleMove);
  svgEl.addEventListener('pointerleave', () => { crosshair.setAttribute('opacity','0'); tooltip.style.opacity = 0; });
}

// ---------- objects section ----------
function fitBadge(fit) {
  if (fit == null || fit.b == null) return '<span class="mono" style="color:var(--text-faint)">n/a</span>';
  return `<span class="mono">N<sup>${fit.b}</sup></span> <span style="color:var(--text-faint)">(R²=${fit.r2})</span>`;
}

function renderObjects() {
  const root = document.getElementById('objects-root');
  DATA.objects.forEach(obj => {
    const seriesList = Object.values(obj.series);
    const block = document.createElement('div');
    block.className = 'obj-block';
    block.innerHTML = `
      <div class="obj-head">
        <h2>${obj.title}</h2>
        <span class="chip">${obj.shape}</span>
        <span class="chip">N = ${obj.sizes.join(' / ')} (manual selection)</span>
        <span class="chip">${seriesList.length} methods</span>
      </div>
      <div class="chart-row">
        <div class="chart-card">
          <div class="chart-title">Total time vs N</div>
          <div class="chart-sub">log-log · s/frame in the table below</div>
          <div class="ch-time"></div>
        </div>
        <div class="chart-card">
          <div class="chart-title">Peak RAM vs N</div>
          <div class="chart-sub">log-log · dashed = pod ceiling (${DATA.ram_total_gib} GiB)</div>
          <div class="ch-ram"></div>
        </div>
        <div class="chart-card">
          <div class="chart-title">Peak VRAM vs N</div>
          <div class="chart-sub">log-log · dashed = pod ceiling (${DATA.vram_total_mib.toLocaleString()} MiB, L40S)</div>
          <div class="ch-vram"></div>
        </div>
      </div>
      <div class="legend" id="legend-${obj.id}"></div>
      <details class="table-toggle">
        <summary>Fitted exponents &amp; raw data — ${obj.title}</summary>
        <div class="grid-wrap" style="margin-top:8px;"></div>
      </details>
    `;
    root.appendChild(block);

    const mk = (n,y) => ({ n, y });
    renderLineChart(block.querySelector('.ch-time'), {
      series: seriesList.map(s => ({ ...mk(s.n, s.time_s), key: s.label, label: s.label, colorvar: s.colorvar, dash: s.dash })),
      xTicks: obj.sizes, yFmt: v => fmtTime(v), nExpected: Math.max(...obj.sizes) ? obj.sizes.length : 4,
    });
    renderLineChart(block.querySelector('.ch-ram'), {
      series: seriesList.map(s => ({ ...mk(s.n, s.ram_mib), key: s.label, label: s.label, colorvar: s.colorvar, dash: s.dash })),
      xTicks: obj.sizes, yFmt: v => fmtMib(v), nExpected: obj.sizes.length,
      ceiling: { value: DATA.ram_total_gib * 1024, label: 'pod RAM ceiling' },
    });
    renderLineChart(block.querySelector('.ch-vram'), {
      series: seriesList.map(s => ({ ...mk(s.n, s.vram_mib), key: s.label, label: s.label, colorvar: s.colorvar, dash: s.dash })),
      xTicks: obj.sizes, yFmt: v => fmtMib(v), nExpected: obj.sizes.length,
      ceiling: { value: DATA.vram_total_mib, label: 'GPU VRAM ceiling' },
    });

    const legend = block.querySelector(`#legend-${obj.id}`);
    legend.innerHTML = seriesList.map(s => {
      const partial = s.n_points < s.n_expected ? ` <span class="pending-badge">${s.n_points}/${s.n_expected} — sweep pending</span>` : '';
      return `<span class="item"><span class="key" style="background:var(${s.colorvar})"></span>${s.label}${partial}</span>`;
    }).join('');

    const tableWrap = block.querySelector('.table-toggle .grid-wrap');
    let rows = '';
    seriesList.forEach(s => {
      s.n.forEach((n,i) => {
        rows += `<tr><td class="txt">${s.label}</td><td>${n}</td><td>${s.exp_ids[i]}</td>
          <td>${fmt(s.time_s[i],0)}</td><td>${(s.time_s[i]/n).toFixed(1)}</td>
          <td>${fmt(s.ram_mib[i],0)}</td><td>${fmt(s.vram_mib[i],0)}</td></tr>`;
      });
    });
    let fitRows = '';
    seriesList.forEach(s => {
      fitRows += `<tr><td class="txt">${s.label}</td><td>${fitBadge(s.fit_time)}</td>
        <td>${s.fit_time_lin.slope!=null ? s.fit_time_lin.slope.toFixed(1)+' s/frame' : 'n/a'}</td>
        <td>${s.fit_ram_lin.slope!=null ? s.fit_ram_lin.slope.toFixed(0)+' MiB/frame' : 'n/a'}</td>
        <td>${s.fit_vram_lin.slope!=null ? s.fit_vram_lin.slope.toFixed(1)+' MiB/frame' : 'n/a'}</td></tr>`;
    });
    tableWrap.innerHTML = `
      <table class="data" style="min-width:520px; margin-bottom:14px;">
        <thead><tr><th class="txt">method</th><th>time~N^b</th><th>marginal time</th><th>marginal RAM</th><th>marginal VRAM</th></tr></thead>
        <tbody>${fitRows}</tbody>
      </table>
      <table class="data">
        <thead><tr><th class="txt">method</th><th>N</th><th class="txt">exp_id</th><th>total (s)</th><th>s/frame</th><th>RAM (MiB)</th><th>VRAM (MiB)</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  });
}

// ---------- stage share stacked bars ----------
function renderStageShare() {
  const root = document.getElementById('stage-root');
  const rampSteps = ['#9ec5f4','#5598e7','#2a78d6','#184f95','#0d366b','#082347'];
  Object.entries(DATA.stage_share).forEach(([method, entry]) => {
    const row = document.createElement('div');
    const segs = entry.stages.map((st, i) => {
      const color = rampSteps[Math.min(i, rampSteps.length-1)];
      const label = st.median_pct >= 6 ? `${st.label} ${st.median_pct}%` : '';
      return `<div class="stagebar-seg" style="width:${st.median_pct}%; background:${color};" title="${st.label}: ${st.median_pct}% (${st.median_s_per_frame}s/frame)">${label}</div>`;
    }).join('');
    const legend = entry.stages.map((st,i) => `<span><span class="dot" style="background:${rampSteps[Math.min(i, rampSteps.length-1)]}; display:inline-block; width:8px; height:8px; border-radius:2px; margin-right:4px;"></span>${st.label} — ${st.median_pct}% (${st.median_s_per_frame}s/frame)</span>`).join('');
    row.innerHTML = `<div class="stagebar-row"><div class="stagebar-label">${METHOD_LABEL[method]}</div><div class="stagebar-track">${segs}</div></div>
      <div class="stage-legend" style="margin:2px 0 10px 140px;">${legend}</div>`;
    root.appendChild(row);
  });
}

// ---------- stage scaling table ----------
function renderStageScaling() {
  const root = document.getElementById('stage-scaling-root');
  let html = '<table class="data" style="min-width:820px;"><thead><tr><th class="txt">method</th><th class="txt">stage</th><th>exponent b (time~N^b)</th><th>R²</th></tr></thead><tbody>';
  Object.entries(DATA.stage_scaling).forEach(([method, stages]) => {
    stages.forEach((st, i) => {
      html += `<tr>${i===0 ? `<td class="txt" rowspan="${stages.length}">${METHOD_LABEL[method]}</td>` : ''}
        <td class="txt">${st.label}</td>
        <td>${st.exponent != null ? st.exponent : '—'}</td>
        <td>${st.r2 != null ? st.r2 : '—'}</td></tr>`;
    });
  });
  html += '</tbody></table>';
  root.innerHTML = html;
}

// ---------- even-selection robustness table ----------
function renderEvenCheck() {
  const root = document.getElementById('even-check-root');
  let html = '';
  DATA.objects.forEach(obj => {
    if (!obj.even_check.length) return;
    html += `<h3 style="margin:8px 0 4px;">${obj.title}</h3><table class="data" style="min-width:640px; margin-bottom:14px;">
      <thead><tr><th class="txt">method</th><th>time~N^b</th><th>R²</th><th class="txt">N</th><th>time (s)</th><th>RAM (MiB)</th><th>VRAM (MiB)</th></tr></thead><tbody>`;
    obj.even_check.forEach(m => {
      m.rows.forEach((r,i) => {
        html += `<tr>${i===0 ? `<td class="txt" rowspan="${m.rows.length}">${m.method}</td><td rowspan="${m.rows.length}">${m.exponent!=null?m.exponent:'—'}</td><td rowspan="${m.rows.length}">${m.r2!=null?m.r2:'—'}</td>` : ''}
          <td class="txt">${r.n}</td><td>${fmt(r.time_s,0)}</td><td>${fmt(r.ram_mib,0)}</td><td>${fmt(r.vram_mib,0)}</td></tr>`;
      });
    });
    html += '</tbody></table>';
  });
  root.innerHTML = html;
}

// ---------- VGGT appendix ----------
function renderVggt() {
  const v = DATA.vggt;
  document.getElementById('vggt-caveat').innerHTML =
    `bollard_003_test_1 and information_sign_002_test_1 now have a real VGGT N-sweep — see the main charts above, VGGT is
    charted there like every other method. Every row below is everything else: a <b>different object</b> at a different N,
    so an N-effect can't be isolated from an object/scene effect for these. <span class="mono">model_load</span>
    (13–29s, HF cache hot/cold) is stripped before fitting since it swamps the signal at these small N and has nothing to do with frame count.
    total (uncorrected) fit: N<sup>${v.fit_total.b ?? '—'}</sup> (R²=${v.fit_total.r2 ?? '—'}) — dominated by cache-state noise, not meaningful.
    preprocess+inference only: N<sup>${v.fit_work.b ?? '—'}</sup> (R²=${v.fit_work.r2 ?? '—'}), linear ≈ ${v.fit_work_lin.slope} s/frame + ${v.fit_work_lin.intercept}s.`;
  let html = '<table class="data" style="min-width:760px;"><thead><tr><th class="txt">object</th><th>N</th><th>model_load (s)</th><th>preprocess+inference (s)</th><th>s/frame (work only)</th><th>total (s)</th><th>RAM (MiB)</th><th>VRAM (MiB)</th></tr></thead><tbody>';
  v.rows.forEach(r => {
    html += `<tr><td class="txt">${r.object}</td><td>${r.n}</td><td>${r.model_load_s}</td><td>${r.work_s}</td><td>${r.work_s_per_frame}</td><td>${r.total_s}</td><td>${fmt(r.ram_mib,0)}</td><td>${fmt(r.vram_mib,0)}</td></tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('vggt-root').innerHTML = html;
}

// ---------- scope box + interpretation (data-driven text) ----------
function renderScopeAndInterp() {
  document.getElementById('hw-ram').textContent = DATA.ram_total_gib;
  document.getElementById('hw-vram').textContent = DATA.vram_total_mib.toLocaleString();
  const scope = document.getElementById('scope-box');
  let hlocLines = '';
  Object.entries(DATA.hloc_status).forEach(([obj, st]) => {
    const missing = st.expected.filter(n => !st.have.includes(n));
    if (missing.length) hlocLines += `<div>hloc+COLMAP · ${obj}: have N=${st.have.join(',')||'none'} <span class="pending-badge">missing N=${missing.join(',')}</span> — rerun this builder once the pod sweep lands.</div>`;
  });
  const scopeLines = DATA.objects.map(obj => {
    const methods = Object.values(obj.series).map(s => s.label).join(', ');
    return `<div><b>${obj.title}</b> (N=${obj.sizes.join('/')}, manual frame selection): ${methods}.</div>`;
  }).join('');
  scope.innerHTML = `
    <div><b>In scope (controlled, charted):</b></div>
    ${scopeLines}
    <div><b>Out of scope (appendix only):</b> VGGT on every other object in the project — still just one point each, no N-sweep.</div>
    ${hlocLines}
  `;

  // ---- data-driven interpretation ----
  const interp = document.getElementById('interp');
  let items = '';
  DATA.objects.forEach(obj => {
    const c = obj.series.colmap, m = obj.series.mast3r_ga, v = obj.series.vggt;
    if (c && c.fit_time.b != null) items += `<li><b>${obj.title}:</b> COLMAP time ~ N<sup>${c.fit_time.b}</sup> (R²=${c.fit_time.r2}), super-linear — each extra frame costs more than the last (dense patchmatch + sparse mapping both grow, see stage table).</li>`;
    if (m && m.fit_time.b != null) items += `<li><b>${obj.title}:</b> MASt3R-GA time ~ N<sup>${m.fit_time.b}</sup> (R²=${m.fit_time.r2}), close to linear.</li>`;
    if (v && v.fit_time.b != null) items += `<li><b>${obj.title}:</b> VGGT (model_load-corrected) time ~ N<sup>${v.fit_time.b}</sup> (R²=${v.fit_time.r2}), ${v.fit_time_lin.slope.toFixed(2)} s/frame — an order of magnitude below every other method's marginal cost.</li>`;
  });
  const c1 = DATA.objects[1]?.series.colmap, m1 = DATA.objects[1]?.series.mast3r_ga, v1 = DATA.objects[1]?.series.vggt;
  interp.innerHTML = `
    <div class="headline">Bottleneck resource is method-specific, not universal</div>
    <ul>
      ${items}
      <li>COLMAP and hloc+COLMAP are <b>RAM-bound</b>, not VRAM-bound: VRAM stays flat (patchmatch's windowed workspace doesn't grow with N) while RAM grows ${c1 ? c1.fit_ram_lin.slope.toFixed(0) : '—'} MiB/frame — at that rate the ${DATA.ram_total_gib} GiB pod saturates around N ≈ ${c1 ? Math.round((DATA.ram_total_gib*1024 - c1.fit_ram_lin.intercept)/c1.fit_ram_lin.slope) : '—'}, far beyond any capture in this project.</li>
      <li>MASt3R-GA is the mirror image — <b>VRAM-bound</b>: RAM is essentially flat (~12 GiB regardless of N) while VRAM grows ${m1 ? m1.fit_vram_lin.slope.toFixed(1) : '—'} MiB/frame, hitting the L40S's ${DATA.vram_total_mib.toLocaleString()} MiB around N ≈ ${m1 ? Math.round((DATA.vram_total_mib - m1.fit_vram_lin.intercept)/m1.fit_vram_lin.slope) : '—'} — the practical scaling ceiling for this method on this GPU.</li>
      <li>hloc+COLMAP's extra cost over plain COLMAP is concentrated in <b>matching + sparse mapping</b> (both exhaustive-pairing artifacts), not in the shared dense stage — see the stage-scaling table above.</li>
      <li>VGGT is <b>VRAM-bound from a much higher floor</b>: even at the smallest N its VRAM (${v1 ? Math.round(v1.fit_vram_lin.intercept).toLocaleString() : '—'} MiB baseline) already exceeds MASt3R-GA's VRAM at the *largest* N tested — a single feed-forward pass over every frame at once costs more memory per frame than an incremental/windowed pipeline, even though it's by far the fastest wall-clock method.</li>
    </ul>
  `;
}

renderObjects();
renderStageShare();
renderStageScaling();
renderEvenCheck();
renderVggt();
renderScopeAndInterp();
</script>"""

HTML_TAIL = "\n</body>\n</html>\n"
