"""HTML/CSS/JS template strings for build_performance_study_page.py.

Self-contained, no external libraries, theme-aware. Charts are hand-rolled log-log
line charts (SVG, rendered client-side from the embedded JSON so the same code path
draws all 6) plus one 100%-stacked bar for the pipeline-stage breakdown. Method hues
(--m-*) are the site-wide categorical set — the same values as _frame_count_page_template.py's
--colmap/--mastr/--mastr2 and build_thesis_figures.py's METHOD_COLOR, so one method is one
colour across the site and Chapter 5 — see METHOD_COLORVAR in the builder for the assignment.
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
     Method hues (--m-*) are the site-wide set shared with frame count, capture and the
     chapter-5 figures — all four validated against a near-white surface. */
  :root {
    --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084;
    --accent:#17805f; --accent-soft:#d9ece3; --code-bg:#f5f4ef;
    --m-colmap:#c15c85; --m-hloc:#a8621f; --m-mast3r:#0d8054; --m-vggt:#5d63c7;
    --grid:#ddd9cc; --canvas-surface:#ffffff;
    --warn:#a8621f; --warn-soft:#f0dcc4;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084;
      --accent:#17805f; --accent-soft:#d9ece3; --code-bg:#f5f4ef;
      --m-colmap:#c15c85; --m-hloc:#a8621f; --m-mast3r:#0d8054; --m-vggt:#5d63c7;
      --grid:#ddd9cc; --canvas-surface:#ffffff; --warn:#a8621f; --warn-soft:#f0dcc4; }
  }
  :root[data-theme="dark"] { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084;
    --accent:#17805f; --accent-soft:#d9ece3; --code-bg:#f5f4ef;
    --m-colmap:#c15c85; --m-hloc:#a8621f; --m-mast3r:#0d8054; --m-vggt:#5d63c7;
    --grid:#ddd9cc; --canvas-surface:#ffffff; --warn:#a8621f; --warn-soft:#f0dcc4; }
  :root[data-theme="light"] { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084;
    --accent:#17805f; --accent-soft:#d9ece3; --code-bg:#f5f4ef;
    --m-colmap:#c15c85; --m-hloc:#a8621f; --m-mast3r:#0d8054; --m-vggt:#5d63c7;
    --grid:#ddd9cc; --canvas-surface:#ffffff; --warn:#a8621f; --warn-soft:#f0dcc4; }

  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; line-height:1.45; }
  .page { max-width:1560px; margin:0 auto; padding:28px 24px 72px; display:flex; flex-direction:column; gap:26px; }
  a { color:var(--accent); }
  .eyebrow { font-size:11.5px; font-weight:600; letter-spacing:.09em; text-transform:uppercase; color:var(--accent); }
  h1 { font-size:23px; font-weight:650; margin:4px 0 2px; letter-spacing:-.01em; }
  h2 { font-size:18px; font-weight:650; margin:0 0 2px; }
  h3 { font-size:14px; font-weight:650; margin:0; }
  .subtitle { color:var(--text-dim); font-size:13.5px; max-width:92ch; }
  .lede p { margin:0 0 15px; position:relative; padding-left:19px; }
  .lede p:last-child { margin-bottom:0; }
  .lede p::before { content:"\2192"; position:absolute; left:0; top:0; color:var(--accent); font-weight:600; }

  .with-aside { display:grid; grid-template-columns:minmax(0,1fr) 460px; gap:18px; align-items:stretch; }
  @media (max-width:1100px) { .with-aside { grid-template-columns:minmax(0,1fr); } }
  .aside { background:var(--code-bg); border:1px solid var(--panel-border); border-left:3px solid var(--text-faint);
           border-radius:10px; padding:12px 14px; font-size:12px; color:var(--text-dim); }
  .aside b { color:var(--text); }
  .aside .k { display:block; font-size:11px; font-weight:650; letter-spacing:.07em; text-transform:uppercase;
              color:var(--text-faint); margin-bottom:6px; }
  .mkey { display:inline-block; width:9px; height:9px; border-radius:2px; margin-right:7px; }
  .mono { font-family:ui-monospace,"SF Mono","Cascadia Code",Menlo,Consolas,monospace; font-variant-numeric:tabular-nums; }
  section { display:flex; flex-direction:column; gap:14px; }
  hr.sep { border:none; border-top:1px solid var(--panel-border); margin:2px 0; }

  .pending-badge { display:inline-block; font-size:10.5px; font-weight:650; color:var(--warn); border:1px solid color-mix(in srgb, var(--warn) 55%, transparent); background:var(--warn-soft); border-radius:5px; padding:1px 7px; margin-left:4px; }

  details.note { font-size:12px; color:var(--text-faint); border-left:3px solid var(--warn); padding:3px 0 3px 12px; margin-top:12px; max-width:96ch; }
  details.note summary { cursor:pointer; color:var(--warn); font-weight:600; list-style:none; }
  details.note summary::-webkit-details-marker { display:none; }
  details.note summary::before { content:'\25B8\00a0'; }
  details.note[open] summary::before { content:'\25BE\00a0'; }
  details.note > div { padding-top:6px; }
  .obj-scope { font-size:11.5px; color:var(--text-faint); margin-top:-8px; }

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
  .stagebar-seg { height:100%; display:flex; align-items:center; justify-content:center; font-size:10px; color:#fff; font-weight:600; border-right:2px solid var(--panel); overflow:hidden; }
  .stagebar-seg > span { flex:0 0 auto; white-space:nowrap; }
  .stagebar-seg:last-child { border-right:none; }
  .stage-legend { display:flex; flex-wrap:wrap; gap:8px 16px; font-size:11px; color:var(--text-dim); }

  .caveat { font-size:12px; color:var(--text-faint); border-left:3px solid var(--warn); padding:4px 0 4px 12px; }

  footer { color:var(--text-faint); font-size:11px; padding-top:4px; }
__NAV_CSS__
</style>

<div class="page">
  __SITE_NAV__
  <div>
    <div class="eyebrow">Compute cost · time &amp; memory vs frame count</div>
    <h1>Does reconstruction cost grow with the number of photos — and how, per method?</h1>
    <div class="subtitle lede" style="max-width:92ch">
      <p>
        More photos is the obvious way to a better reconstruction. This asks what that costs — in wall
        time, in RAM, in VRAM — and whether the four methods pay the same price for it.
      </p>
      <p>
        <b>Every run on the same NVIDIA L40S pod</b> (<span id="hw-ram">…</span> GiB RAM ceiling,
        <span id="hw-vram">…</span> MiB VRAM), so time and memory are directly comparable across methods.
      </p>
      <p>
        <b>The same two objects and the same nested frame sets</b> as the frame-count study — one object,
        one capture, one frame-ranking method, and only N changes. Anything that is not a controlled
        sweep is kept in a labelled appendix.
      </p>
      <p>
        This is the cost half only. What those frames <b>buy</b> is the same runs scored against LiDAR in
        <a href="frame_count_study.html">frame count</a>.
      </p>
    </div>
    <details class="note">
      <summary>The methods are not doing equally hard work — read every speed number against this</summary>
      <div>
        COLMAP detects features at 3200&nbsp;px and runs dense stereo at 3024&nbsp;px; hloc detects at
        1024&nbsp;px; both feed-forward models operate at roughly 512&nbsp;px — about a sixth of COLMAP's
        linear resolution, so around a thirtieth of the pixels. It is a deliberate property of the methods
        as published, left untuned rather than equalised, and a limitation of this comparison rather than
        a finding of it.
      </div>
    </details>
  </div>

  <hr class="sep">
  <section>
    <h2>Source data — time, RAM and VRAM against N</h2>
    <div class="subtitle" style="max-width:92ch">
      One block per object, three cost axes each. Log-log, so a power law is a straight line and its slope
      is the exponent; the dashed line is the pod's ceiling for that resource.
    </div>
  </section>
  <section id="objects-root"></section>

  <hr class="sep">
  <section>
    <h2>Does the cost actually grow with N?</h2>
    <div class="subtitle" style="max-width:92ch">
      Total wall time fitted as time ~ N<sup>b</sup> on each controlled sweep. <b>b &gt; 1</b> means every
      extra photo costs more than the one before it; <b>b ≈ 1</b> means a frame is a frame. <b>Marginal</b>
      is the same runs fitted linearly — the seconds one more photo adds.
    </div>
    <div class="with-aside">
      <div class="grid-wrap" id="time-scaling-root"></div>
      <div class="aside" id="time-aside"></div>
    </div>
  </section>

  <hr class="sep">
  <section>
    <h2>Which resource runs out first?</h2>
    <div class="subtitle" style="max-width:92ch">
      Peak RAM and peak VRAM fitted linearly against N, then extrapolated to the pod's two ceilings.
      <b>Saturates at N</b> is where a method would exhaust that resource on this hardware — far beyond any
      capture in this project, so read it as the direction each method is heading, not as a limit anyone hit.
    </div>
    <div class="with-aside">
      <div class="grid-wrap" id="memory-headroom-root"></div>
      <div class="aside" id="memory-aside"></div>
    </div>
  </section>

  <hr class="sep">
  <section>
    <h2>Where does the time actually go?</h2>
    <div class="subtitle" style="max-width:92ch">Median % of total wall time per stage, across every successful run of that method (architecture-intrinsic, not restricted to the controlled sweep). 100%-stacked; a segment too narrow for its name shows only its share, and every stage is named in full in the legend under its bar.</div>
    <div class="with-aside">
      <div>
        <div id="stage-root" style="display:flex; flex-direction:column; gap:12px;"></div>
        <details class="table-toggle" style="margin-top:12px;">
          <summary>Per-stage scaling exponents</summary>
          <div class="subtitle" style="margin:6px 0 8px;">Per-stage power-law fit (stage time ~ N^b), controlled sweeps only (manual selection, both objects pooled on log N).</div>
          <div class="grid-wrap" id="stage-scaling-root"></div>
        </details>
        <div id="even-check-root"></div>
      </div>
      <div class="aside" id="stage-aside"></div>
    </div>
  </section>

  <hr class="sep">
  <section>
    <h2>Appendix — VGGT on other objects <span class="pending-badge">not a controlled sweep</span></h2>
    <div class="caveat" id="vggt-caveat"></div>
    <div class="grid-wrap" id="vggt-root"></div>
  </section>

  <footer id="footer-note">timings recorded per run on the pod that produced these reconstructions</footer>
</div>
"""


MAIN_JS = r"""<script>
const DATA = JSON.parse(document.getElementById('page-data').textContent);
const METHOD_LABEL = DATA.method_label;
const CHART_W = 460, CHART_H = 330;
const PAD = { l: 52, r: 18, t: 16, b: 42 };

function fmt(v, digits) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return Number(v).toLocaleString('en-US', { maximumFractionDigits: digits ?? 0, minimumFractionDigits: 0 });
}
function fmtTime(s) {
  if (s >= 3600) return (s/3600).toFixed(1) + 'h';
  if (s >= 90) return Math.round(s/60) + 'm';
  return Math.round(s) + 's';
}
// memory charts plot GiB, so niceLogTicks' 1/2/5 x 10^k lands on round human values.
// Axis ticks are therefore always integers; the extra decimal is for tooltip readouts.
function fmtGib(g) { return (g >= 100 ? Math.round(g) : Math.round(g * 10) / 10) + ' GiB'; }

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
    svg += `<text x="${PAD.l-7}" y="${y+4}" text-anchor="end" font-size="11" fill="var(--text-faint)">${opts.yFmt(t)}</text>`;
  });
  // gridlines (x)
  opts.xTicks.forEach(n => {
    const x = px(n);
    svg += `<line x1="${x}" y1="${PAD.t}" x2="${x}" y2="${CHART_H-PAD.b}" stroke="var(--grid)" stroke-width="1" opacity="0.5"/>`;
    svg += `<text x="${x}" y="${CHART_H-PAD.b+16}" text-anchor="middle" font-size="11" fill="var(--text-faint)">${n}</text>`;
  });
  svg += `<text x="${CHART_W/2}" y="${CHART_H-5}" text-anchor="middle" font-size="11.5" fill="var(--text-dim)">N (frames)</text>`;

  // ceiling reference line
  if (opts.ceiling) {
    const y = py(opts.ceiling.value);
    svg += `<line x1="${PAD.l}" y1="${y}" x2="${CHART_W-PAD.r}" y2="${y}" stroke="var(--text-faint)" stroke-width="1.4" stroke-dasharray="4 3"/>`;
    svg += `<text x="${CHART_W-PAD.r}" y="${y-5}" text-anchor="end" font-size="10.5" fill="var(--text-faint)">${opts.ceiling.label}</text>`;
  }

  // series lines + points (series are identified by the legend under the chart, not by
  // labels inside the plot field - those repeated the legend and overlapped each other)
  opts.series.forEach(s => {
    const pts = s.n.map((n,i) => [px(n), py(s.y[i])]);
    if (pts.length >= 2) {
      const d = pts.map((p,i) => (i===0?'M':'L') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
      const dash = s.dash ? ` stroke-dasharray="${s.dash}"` : '';
      svg += `<path d="${d}" fill="none" stroke="var(${s.colorvar})" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"${dash}/>`;
    }
    pts.forEach(p => {
      svg += `<circle cx="${p[0]}" cy="${p[1]}" r="5" fill="var(--canvas-surface)"/>`;
      svg += `<circle cx="${p[0]}" cy="${p[1]}" r="3.2" fill="var(${s.colorvar})"/>`;
    });
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
      <div class="obj-scope">Controlled sweep — one object, one capture, one frame-ranking method; only N changes.</div>
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
          <div class="chart-sub">log-log · dashed = pod ceiling (${Math.round(DATA.vram_total_mib/1024)} GiB, L40S)</div>
          <div class="ch-vram"></div>
        </div>
      </div>
      <div class="legend" id="legend-${obj.id}"></div>
      <details class="table-toggle">
        <summary>Raw data — ${obj.title}</summary>
        <div class="grid-wrap" style="margin-top:8px;"></div>
      </details>
    `;
    root.appendChild(block);

    const mk = (n,y) => ({ n, y });
    const gib = arr => arr.map(v => v / 1024);
    renderLineChart(block.querySelector('.ch-time'), {
      series: seriesList.map(s => ({ ...mk(s.n, s.time_s), key: s.label, label: s.label, colorvar: s.colorvar, dash: s.dash })),
      xTicks: obj.sizes, yFmt: v => fmtTime(v),
    });
    renderLineChart(block.querySelector('.ch-ram'), {
      series: seriesList.map(s => ({ ...mk(s.n, gib(s.ram_mib)), key: s.label, label: s.label, colorvar: s.colorvar, dash: s.dash })),
      xTicks: obj.sizes, yFmt: fmtGib,
      ceiling: { value: DATA.ram_total_gib, label: 'pod RAM ceiling' },
    });
    renderLineChart(block.querySelector('.ch-vram'), {
      series: seriesList.map(s => ({ ...mk(s.n, gib(s.vram_mib)), key: s.label, label: s.label, colorvar: s.colorvar, dash: s.dash })),
      xTicks: obj.sizes, yFmt: fmtGib,
      ceiling: { value: DATA.vram_total_mib / 1024, label: 'GPU VRAM ceiling' },
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
    tableWrap.innerHTML = `
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
      // filled in by fitStageLabels() once the bar has a real width to measure against
      return `<div class="stagebar-seg" style="width:${st.median_pct}%; background:${color};" title="${st.label}: ${st.median_pct}% (${st.median_s_per_frame}s/frame)"><span data-full="${st.label} ${st.median_pct}%" data-short="${st.median_pct}%"></span></div>`;
    }).join('');
    const legend = entry.stages.map((st,i) => `<span><span class="dot" style="background:${rampSteps[Math.min(i, rampSteps.length-1)]}; display:inline-block; width:8px; height:8px; border-radius:2px; margin-right:4px;"></span>${st.label} — ${st.median_pct}% (${st.median_s_per_frame}s/frame)</span>`).join('');
    row.innerHTML = `<div class="stagebar-row"><div class="stagebar-label">${METHOD_LABEL[method]}</div><div class="stagebar-track">${segs}</div></div>
      <div class="stage-legend" style="margin:2px 0 10px 140px;">${legend}</div>`;
    root.appendChild(row);
  });
  fitStageLabels();
  // segment widths are percentages of the track, so what fits changes with the viewport
  window.addEventListener('resize', fitStageLabels);
}

// A 6.7%-wide segment cannot hold "dense: fusion 6.7%", and a percentage threshold cannot
// know that - the label's own length decides. Measure what fits, fall back to the bare
// number, then to nothing; every stage is named with its value in the legend regardless.
function fitStageLabels() {
  document.querySelectorAll('.stagebar-seg > span').forEach(sp => {
    const avail = sp.parentElement.clientWidth - 8;
    for (const text of [sp.dataset.full, sp.dataset.short, '']) {
      sp.textContent = text;
      if (!text || sp.getBoundingClientRect().width <= avail) break;
    }
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
  if (!DATA.objects.some(o => o.even_check.length)) { root.remove(); return; }
  let html = `<details class="table-toggle"><summary>Robustness check — the "even" (SIFT-overlap greedy) selection sweeps</summary>
    <div class="subtitle" style="margin:6px 0 8px;">Same N grid, an algorithmic instead of human frame selection — included to confirm the exponents above aren't an artifact of the manual ranking.</div>`;
  DATA.objects.forEach(obj => {
    if (!obj.even_check.length) return;
    html += `<h3 style="margin:8px 0 4px;">${obj.title}</h3><div class="grid-wrap"><table class="data" style="min-width:640px; margin-bottom:14px;">
      <thead><tr><th class="txt">method</th><th>time~N^b</th><th>R²</th><th class="txt">N</th><th>time (s)</th><th>RAM (MiB)</th><th>VRAM (MiB)</th></tr></thead><tbody>`;
    obj.even_check.forEach(m => {
      m.rows.forEach((r,i) => {
        html += `<tr>${i===0 ? `<td class="txt" rowspan="${m.rows.length}">${m.method}</td><td rowspan="${m.rows.length}">${m.exponent!=null?m.exponent:'—'}</td><td rowspan="${m.rows.length}">${m.r2!=null?m.r2:'—'}</td>` : ''}
          <td class="txt">${r.n}</td><td>${fmt(r.time_s,0)}</td><td>${fmt(r.ram_mib,0)}</td><td>${fmt(r.vram_mib,0)}</td></tr>`;
      });
    });
    html += '</tbody></table></div>';
  });
  root.innerHTML = html + '</details>';
}

// ---------- VGGT appendix ----------
function renderVggt() {
  const v = DATA.vggt;
  // These older runs logged only model_load - no preprocess/inference entry at all. That is
  // missing data, not zero seconds, so the two stage columns are dropped entirely rather than
  // printed as 0 next to a real total (which read as "VGGT does no work"). They come back on
  // their own, with '—' for any run that still lacks the split, once staged runs are added.
  const stageCols = v.has_work_data;
  const gaps = v.rows.filter(r => r.work_s == null).map(r => r.total_s - r.model_load_s);
  let missingNote = '';
  if (gaps.length) {
    const lo = Math.min(...gaps).toFixed(1), hi = Math.max(...gaps).toFixed(1);
    missingNote = ` ${gaps.length === v.rows.length ? 'These runs predate' : 'Some of these runs predate'}
      per-stage timing — only <span class="mono">model_load</span> was recorded, leaving ${lo}–${hi}s of each
      total unattributed to any stage, so the preprocess/inference split is
      ${stageCols ? "shown as '—' where it was never logged" : 'left out of the table below'}.`;
  }
  let workFit = '';
  if (v.fit_work.b != null) {
    workFit = ` preprocess+inference only: N<sup>${v.fit_work.b}</sup> (R²=${v.fit_work.r2}),
      linear ≈ ${v.fit_work_lin.slope} s/frame + ${v.fit_work_lin.intercept}s.`;
  }
  document.getElementById('vggt-caveat').innerHTML =
    `bollard_003 and information_sign_002 now have a real VGGT N-sweep — see the main charts above, VGGT is
    charted there like every other method. Every row below is everything else: a <b>different object</b> at a different N,
    so an N-effect can't be isolated from an object/scene effect for these.${missingNote}
    Total (uncorrected) fit: N<sup>${v.fit_total.b ?? '—'}</sup> (R²=${v.fit_total.r2 ?? '—'}) — that R² is the point:
    at these small N the total is dominated by <span class="mono">model_load</span> (13–29s, HF cache hot or cold),
    which has nothing to do with frame count.${workFit}`;
  const stageHead = stageCols ? '<th>preprocess+inference (s)</th><th>s/frame (work only)</th>' : '';
  let html = `<table class="data" style="min-width:${stageCols ? 760 : 620}px;"><thead><tr><th class="txt">object</th><th>N</th><th>model_load (s)</th>${stageHead}<th>total (s)</th><th>RAM (MiB)</th><th>VRAM (MiB)</th></tr></thead><tbody>`;
  v.rows.forEach(r => {
    // "_test_1" is an internal capture suffix; other qualifiers (_master, _pool69) name a
    // genuinely different capture and stay.
    const stageCells = stageCols ? `<td>${fmt(r.work_s,1)}</td><td>${fmt(r.work_s_per_frame,3)}</td>` : '';
    html += `<tr><td class="txt">${r.object.replace('_test_1','')}</td><td>${r.n}</td><td>${r.model_load_s}</td>${stageCells}<td>${r.total_s}</td><td>${fmt(r.ram_mib,0)}</td><td>${fmt(r.vram_mib,0)}</td></tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('vggt-root').innerHTML = html;
}

// ---------- shared helpers for the two answer sections ----------
const SUPERLIN = 1.0;  // b > 1 == each extra frame costs more than the last

function seriesOf(method) { return DATA.objects.map(o => o.series[method]).filter(Boolean); }
function valuesOf(method, pick) { return seriesOf(method).map(pick).filter(v => v != null); }
// one number if every sweep agrees, otherwise the range across sweeps
function span(vals, digits) {
  if (!vals.length) return '—';
  const f = v => digits == null ? String(v) : v.toFixed(digits);
  const lo = f(Math.min(...vals)), hi = f(Math.max(...vals));
  return lo === hi ? lo : `${lo}–${hi}`;
}
function swatch(colorvar) { return `<span class="mkey" style="background:var(${colorvar})"></span>`; }

// N at which a linear memory trend would meet the ceiling. A flat or falling trend never
// does, and is reported as such rather than as a huge or negative N.
function saturationN(lin, ceilingMib) {
  if (!lin || lin.slope == null || lin.slope <= 0) return null;
  const n = (ceilingMib - lin.intercept) / lin.slope;
  return n > 0 ? Math.round(n) : null;
}

// ---------- section: does the cost grow with N? ----------
function renderTimeScaling() {
  let html = '<table class="data" style="min-width:600px; width:100%;"><thead><tr><th class="txt">object</th><th class="txt">method</th>'
    + '<th>time ~ N<sup>b</sup></th><th>R²</th><th>marginal</th><th>total at largest N</th></tr></thead><tbody>';
  DATA.objects.forEach(obj => {
    const list = Object.values(obj.series);
    list.forEach((s, i) => {
      const iMax = s.n.indexOf(Math.max(...s.n));
      html += `<tr>${i === 0 ? `<td class="txt" rowspan="${list.length}">${obj.title}</td>` : ''}
        <td class="txt">${swatch(s.colorvar)}${s.label}</td>
        <td class="mono">${s.fit_time.b ?? '—'}</td>
        <td>${s.fit_time.r2 ?? '—'}</td>
        <td>${s.fit_time_lin.slope != null ? s.fit_time_lin.slope.toFixed(1) + ' s/frame' : '—'}</td>
        <td>${fmtTime(s.time_s[iMax])} <span style="color:var(--text-faint)">at N=${s.n[iMax]}</span></td></tr>`;
    });
  });
  document.getElementById('time-scaling-root').innerHTML = html + '</tbody></table>';

  const cB = valuesOf('colmap', s => s.fit_time.b), hB = valuesOf('hloc_colmap', s => s.fit_time.b);
  const mB = valuesOf('mast3r_ga', s => s.fit_time.b), vB = valuesOf('vggt', s => s.fit_time.b);
  const corr = cB.concat(hB);
  const cMarg = valuesOf('colmap', s => s.fit_time_lin.slope);
  const vMarg = valuesOf('vggt', s => s.fit_time_lin.slope);
  const vTimes = seriesOf('vggt').flatMap(s => s.time_s);
  // the headline is read off the data, so a future sweep that changes the picture changes the
  // sentence with it instead of leaving a stale claim on the page
  const headline = corr.every(b => b > SUPERLIN)
    ? 'Yes — but only the correspondence pipelines pay a rising price per frame.'
    : 'Not uniformly — the exponents below disagree across methods.';
  document.getElementById('time-aside').innerHTML = `
    <span class="k">The answer</span>
    <b>${headline}</b> COLMAP grows as N<sup>${span(cB)}</sup> and hloc + COLMAP as N<sup>${span(hB)}</sup>
    — above 1 on every sweep, because exhaustive pairing grows with N². MASt3R-GA is effectively linear or better
    (N<sup>${span(mB)}</sup>).
    <br><br>
    VGGT's exponent is the least stable of the four (N<sup>${span(vB)}</sup>): across whole runs of
    ${fmtTime(Math.min(...vTimes))}–${fmtTime(Math.max(...vTimes))} the fit is riding on a few seconds
    either way, so read its <i>base</i> rather than its slope.
    <br><br>
    That base is where the real gap is: one more frame adds about <b>${span(cMarg, 0)}s</b> to a COLMAP
    run and about <b>${span(vMarg, 1)}s</b> to a VGGT one.`;
}

// ---------- section: which resource runs out first? ----------
function renderMemoryHeadroom() {
  const ramCeil = DATA.ram_total_gib * 1024, vramCeil = DATA.vram_total_mib;
  let html = '<table class="data" style="min-width:660px; width:100%;"><thead><tr><th class="txt">object</th><th class="txt">method</th>'
    + '<th>RAM / frame</th><th>VRAM / frame</th><th class="txt">bound by</th><th>saturates at N ≈</th></tr></thead><tbody>';
  DATA.objects.forEach(obj => {
    const list = Object.values(obj.series);
    list.forEach((s, i) => {
      const nR = saturationN(s.fit_ram_lin, ramCeil), nV = saturationN(s.fit_vram_lin, vramCeil);
      let bound = '<span style="color:var(--text-faint)">neither — both flat</span>', boundN = '—';
      if (nR != null && (nV == null || nR <= nV)) { bound = '<b>RAM</b>'; boundN = nR.toLocaleString(); }
      else if (nV != null) { bound = '<b>VRAM</b>'; boundN = nV.toLocaleString(); }
      const flat = v => {
        if (v == null) return '—';
        if (v <= 0) return `<span style="color:var(--text-faint)" title="${v} MiB/frame — no growth with N">flat</span>`;
        return (v < 1 ? '&lt;1' : v.toFixed(0)) + ' MiB';
      };
      html += `<tr>${i === 0 ? `<td class="txt" rowspan="${list.length}">${obj.title}</td>` : ''}
        <td class="txt">${swatch(s.colorvar)}${s.label}</td>
        <td>${flat(s.fit_ram_lin.slope)}</td>
        <td>${flat(s.fit_vram_lin.slope)}</td>
        <td class="txt">${bound}</td>
        <td>${boundN}</td></tr>`;
    });
  });
  document.getElementById('memory-headroom-root').innerHTML = html + '</tbody></table>';

  const satRam = m => valuesOf(m, s => saturationN(s.fit_ram_lin, ramCeil));
  const satVram = m => valuesOf(m, s => saturationN(s.fit_vram_lin, vramCeil));
  const corrRam = valuesOf('colmap', s => s.fit_ram_lin.slope).concat(valuesOf('hloc_colmap', s => s.fit_ram_lin.slope));
  const corrN = satRam('colmap').concat(satRam('hloc_colmap'));
  const feedVram = valuesOf('mast3r_ga', s => s.fit_vram_lin.slope).concat(valuesOf('vggt', s => s.fit_vram_lin.slope));
  const feedN = satVram('mast3r_ga').concat(satVram('vggt'));
  const vggtN = satVram('vggt');
  const vggtFloor = valuesOf('vggt', s => s.fit_vram_lin.intercept);
  document.getElementById('memory-aside').innerHTML = `
    <span class="k">The answer</span>
    <b>The bottleneck is method-specific, not universal.</b>
    <br><br>
    <b>COLMAP and hloc + COLMAP are RAM-bound.</b> VRAM stays flat — patchmatch's window does not grow
    with N — while RAM climbs ${span(corrRam, 0)} MiB/frame, filling the ${DATA.ram_total_gib} GiB pod at
    N ≈ ${span(corrN)}.
    <br><br>
    <b>MASt3R-GA and VGGT are the mirror image.</b> RAM is essentially flat; VRAM climbs
    ${span(feedVram, 0)} MiB per frame and reaches the L40S's ${Math.round(vramCeil / 1024)} GiB first,
    around N ≈ ${span(feedN)}.
    <br><br>
    <b>VGGT gets there soonest</b> (N ≈ ${span(vggtN)}), from the highest floor
    (${span(vggtFloor.map(Math.round))} MiB before a single frame is added): one feed-forward pass over all
    frames at once costs more memory per frame than an incremental pipeline — and it is still the fastest
    method on the clock.`;
}

// ---------- stage-section answer ----------
function renderStageAside() {
  const pctOf = (method, key) => {
    const st = (DATA.stage_share[method] || {stages: []}).stages.find(x => x.key === key);
    return st ? st.median_pct : '—';
  };
  const pick = (method, key) => {
    const st = (DATA.stage_scaling[method] || []).find(x => x.key === key);
    return st && st.exponent != null ? st.exponent : null;
  };
  const dense = ['colmap', 'hloc_colmap'].map(m => pick(m, 'dense_patchmatch')).filter(v => v != null);
  const match = ['colmap', 'hloc_colmap'].map(m => pick(m, 'matching')).filter(v => v != null);
  const sparse = ['colmap', 'hloc_colmap'].map(m => pick(m, 'sparse_mapping')).filter(v => v != null);
  document.getElementById('stage-aside').innerHTML = `
    <span class="k">The answer</span>
    <b>The super-linear part is matching, not the dense stage.</b>
    <br><br>
    Dense patchmatch — the stage that eats most of the wall clock — scales at N<sup>${span(dense)}</sup>,
    essentially linear, because it is per-image work. What bends the curve is <b>matching</b>
    (N<sup>${span(match)}</sup>) and <b>sparse mapping</b> (N<sup>${span(sparse)}</sup>): both are
    pair-count artifacts of exhaustive pairing, which grows as N².
    <br><br>
    That is also where hloc + COLMAP's extra cost over plain COLMAP sits — in the correspondence stages,
    not in the dense stage the two run identically.
    <br><br>
    <b>The feed-forward pair has no such stage to blame.</b> MASt3R-GA spends ${pctOf('mast3r_ga', 'matching_and_optimization')}%
    of its run in one fused matching + global-optimisation step, and VGGT's single largest stage is
    <span class="mono">model_load</span> at ${pctOf('vggt', 'model_load')}% — at these N its actual inference is
    ${pctOf('vggt', 'inference')}% of the run, which is why its wall time barely moves with N.`;
}

// ---------- header hardware numbers ----------
function renderHeaderNumbers() {
  document.getElementById('hw-ram').textContent = DATA.ram_total_gib;
  document.getElementById('hw-vram').textContent = DATA.vram_total_mib.toLocaleString();
}

renderHeaderNumbers();
renderObjects();
renderTimeScaling();
renderMemoryHeadroom();
renderStageShare();
renderStageScaling();
renderStageAside();
renderEvenCheck();
renderVggt();
</script>"""

HTML_TAIL = "\n__SITE_CREDIT__\n</body>\n</html>\n"
