"""HTML/CSS/JS template strings for build_capture_comparison_page.py.

Kept in a separate module so the builder (which does the heavy o3d numeric work) stays
readable. HTML_HEAD holds the head + CSS + empty mount points; MAIN_JS holds all the
interactive logic (WebGL viewers, live per-object DBSCAN tuners, reactive summary table
and grouped F1 bar chart); HTML_TAIL closes the document. The whole page is
self-contained - no external libraries, theme-aware, raw WebGL.

Most of the low-level machinery (grid-accelerated DBSCAN, the mat4 helpers, makeViewer,
the population-weighted accuracy%) is lifted verbatim from site/bus_stop_001.html so the
numbers are produced identically to the per-object pages.
"""

HTML_HEAD = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Capture-approach comparison — bollard_003 &amp; information_sign_002 (gap-aware Accuracy/Completeness/F1)</title>
</head>
<body>
<style>
  /* Forced light palette - matches the thesis-defense deck (white bg, forest-green accent)
     and every other page on the site. Series hues are the CVD-safe set.
     NOTE: this palette was originally applied by hand-editing the generated .html (commit
     707db75) and was silently lost on the next rebuild, because the template it is built
     from still had the old grey/orange one. It lives here now so a rebuild keeps it. */
  :root {
    --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084;
    --accent:#17805f; --accent-soft:#d9ece3; --green:#1aacb3; --red:#e16b3e; --ref-magenta:#2b2b28;
    --canvas-bg:#ffffff; --code-bg:#f5f4ef; --best:#0d8054; --best-soft:#e3f1ea;
    --t1:#c15c85; --t2:#0d8054; --t3:#5d63c7;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084;
      --accent:#17805f; --accent-soft:#d9ece3; --green:#1aacb3; --red:#e16b3e; --code-bg:#f5f4ef; --best:#0d8054; --best-soft:#e3f1ea;
      --t1:#c15c85; --t2:#0d8054; --t3:#5d63c7; }
  }
  :root[data-theme="dark"] { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084;
    --accent:#17805f; --accent-soft:#d9ece3; --green:#1aacb3; --red:#e16b3e; --code-bg:#f5f4ef; --best:#0d8054; --best-soft:#e3f1ea;
    --t1:#c15c85; --t2:#0d8054; --t3:#5d63c7; }
  :root[data-theme="light"] { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084;
    --accent:#17805f; --accent-soft:#d9ece3; --green:#1aacb3; --red:#e16b3e; --code-bg:#f5f4ef; --best:#0d8054; --best-soft:#e3f1ea;
    --t1:#c15c85; --t2:#0d8054; --t3:#5d63c7; }

  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; line-height:1.45; }
  .page { max-width:1560px; margin:0 auto; padding:28px 24px 72px; display:flex; flex-direction:column; gap:26px; }
  a { color:var(--accent); }
  .eyebrow { font-size:11.5px; font-weight:600; letter-spacing:.09em; text-transform:uppercase; color:var(--accent); }
  h1 { font-size:23px; font-weight:650; margin:4px 0 2px; letter-spacing:-.01em; }
  h2 { font-size:19px; font-weight:650; margin:0 0 2px; }
  h3 { font-size:15px; font-weight:650; margin:0; }
  .subtitle { color:var(--text-dim); font-size:13.5px; max-width:88ch; }
  /* one treatment for emphasis: near-black. Without this, <b> inside .subtitle / .aside /
     .row-note inherits --text-dim and reads as barely-bolder grey. */
  b, strong { color:var(--text); font-weight:600; }
  /* arrow bullets for the intro paragraphs, matching index.html */
  .lede p { margin:0 0 15px; position:relative; padding-left:19px; }
  .lede p:last-child { margin-bottom:0; }
  .lede p::before { content:"\2192"; position:absolute; left:0; top:0; color:var(--accent); font-weight:600; }
  .mono { font-family:ui-monospace,"SF Mono","Cascadia Code",Menlo,Consolas,monospace; font-variant-numeric:tabular-nums; }
  section { display:flex; flex-direction:column; gap:14px; }
  hr.sep { border:none; border-top:1px solid var(--panel-border); margin:2px 0; }

  .params { font-size:12px; color:var(--text-faint); background:var(--code-bg); border:1px solid var(--panel-border); border-radius:10px; padding:11px 15px; }
  .params b { color:var(--text-dim); font-weight:600; }

  .obj-block { display:flex; flex-direction:column; gap:14px; padding:16px; border:1px solid var(--panel-border); border-radius:14px; background:color-mix(in srgb, var(--panel) 55%, transparent); }
  .obj-head { display:flex; flex-wrap:wrap; align-items:baseline; gap:6px 14px; }
  .obj-head .chip { font-size:11px; color:var(--text-dim); background:var(--code-bg); border:1px solid var(--panel-border); border-radius:20px; padding:2px 10px; }
  .ref-note { font-size:12px; color:var(--text-faint); max-width:96ch; }

  .grid-wrap { overflow-x:auto; }
  .obj-grid { display:grid; grid-template-columns:78px repeat(3, minmax(280px,1fr)); gap:12px; min-width:960px; }
  .col-head { font-size:12.5px; font-weight:650; color:var(--text); padding:0 2px 2px; align-self:end; }
  .col-head .hint { display:block; font-weight:400; font-size:10px; color:var(--text-faint); margin-top:2px; }
  .row-note { grid-column:2 / -1; font-size:12px; color:var(--text-dim); background:var(--code-bg);
              border-left:3px solid var(--text-faint); border-radius:0 8px 8px 0; padding:7px 12px; margin:-4px 0 4px; }
  .row-note b { color:var(--text); }
  .row-head { display:flex; align-items:center; justify-content:center; font-weight:650; font-size:12.5px; writing-mode:vertical-rl; transform:rotate(180deg); color:var(--text-dim); }

  .panel { background:var(--panel); border:1px solid var(--panel-border); border-radius:10px; padding:9px 9px 11px; display:flex; flex-direction:column; gap:7px; box-shadow:0 1px 2px rgba(24,26,23,0.05), 0 1px 8px rgba(24,26,23,0.03); }
  .panel-title { font-weight:650; font-size:12.5px; display:flex; justify-content:space-between; align-items:baseline; gap:6px; }
  .panel-title .exp { font-size:10px; color:var(--text-faint); font-weight:500; }
  canvas { width:100%; height:220px; display:block; border-radius:7px; background:var(--canvas-bg); touch-action:none; cursor:grab; }
  canvas:active { cursor:grabbing; }

  .tabs { display:flex; flex-wrap:wrap; gap:5px; }
  .tab-btn, .toggle-btn { font-family:inherit; font-size:10.5px; padding:3px 9px; border-radius:6px; border:1px solid var(--panel-border); background:transparent; color:var(--text-dim); cursor:pointer; }
  .tab-btn:hover, .toggle-btn:hover { border-color:var(--accent); color:var(--text); }
  .tab-btn.active { background:var(--accent-soft); border-color:var(--accent); color:var(--text); font-weight:600; }
  .toggle-btn.active { background:var(--accent-soft); border-color:var(--ref-magenta); color:var(--text); font-weight:600; }

  .slider-row { display:flex; align-items:center; gap:8px; font-size:11px; color:var(--text-dim); }
  .slider-row input[type=range] { flex:1; accent-color:var(--accent); }
  .preset-btns { display:flex; gap:4px; }
  .preset-btn { font-size:10px; padding:2px 6px; border-radius:5px; border:1px solid var(--panel-border); background:transparent; color:var(--text-faint); cursor:pointer; }
  .preset-btn.active { border-color:var(--accent); color:var(--accent); font-weight:600; }

  .panel-stats { font-size:10.5px; color:var(--text-faint); }
  .panel-stats b { color:var(--text); font-weight:600; }
  .panel-stats .f1 { color:var(--accent); font-weight:700; font-size:12px; }


  .legend-bar { display:flex; width:fit-content; max-width:100%; flex-wrap:wrap; gap:14px 26px; padding:10px 14px; background:var(--panel); border:1px solid var(--panel-border); border-radius:10px; align-items:center; font-size:11.5px; color:var(--text-dim); }
  .swatch { width:11px; height:11px; border-radius:3px; display:inline-block; margin-right:6px; vertical-align:-1px; border:1px solid var(--panel-border); }
  .gradient-bar { height:9px; width:150px; border-radius:5px; border:1px solid var(--panel-border);
    background:linear-gradient(90deg,#30123b 0%,#4458cb 12%,#3e9bfe 25%,#18d5cc 37%,#46f783 50%,#a4fc3b 62%,#e1dc37 75%,#fd8d27 87%,#7a0403 100%); }

  table.summary { border-collapse:collapse; font-size:12px; min-width:900px; }
  table.summary th, table.summary td { padding:6px 10px; border-bottom:1px solid var(--panel-border); text-align:right; white-space:nowrap; }
  table.summary th { font-weight:650; color:var(--text-dim); text-align:right; position:sticky; top:0; background:var(--panel); }
  table.summary td.txt, table.summary th.txt { text-align:left; }
  table.summary td.f1cell { font-weight:700; font-variant-numeric:tabular-nums; }
  table.summary tr.best td.f1cell { color:var(--best); }
  table.summary td.best-cell { background:var(--best-soft); border-radius:4px; }
  table.summary tbody tr:hover { background:color-mix(in srgb, var(--accent-soft) 40%, transparent); }
  .grouprule td { border-top:2px solid var(--panel-border); }

  .with-aside { display:grid; grid-template-columns:minmax(0,1fr) 260px; gap:18px; align-items:start; }
  @media (max-width:1100px) { .with-aside { grid-template-columns:minmax(0,1fr); } }
  .aside { background:var(--code-bg); border:1px solid var(--panel-border); border-left:3px solid var(--text-faint);
           border-radius:10px; padding:12px 14px; font-size:12.5px; color:var(--text-dim); }
  .aside b { color:var(--text); }
  .aside .k { display:block; font-size:11px; font-weight:650; letter-spacing:.07em; text-transform:uppercase;
              color:var(--text-faint); margin-bottom:5px; }

  footer { color:var(--text-faint); font-size:11px; padding-top:4px; }
</style>

<div class="page">
  <div>
    <div class="eyebrow">Capture-strategy ablation · gap-aware Chamfer (Accuracy / Completeness / F1)</div>
    <h1>Does how you film the object change the reconstruction?</h1>
    <div class="subtitle lede" style="max-width:92ch">
      <p>
        Before the main captures were shot, one question had to be settled: <b>how should you walk around
        an object?</b> Getting close shows detail but never the whole shape; staying back frames the whole
        object but resolves less. This is the pilot that decided it.
      </p>
      <p>
        <b>T1</b> = close-range + distant &middot; <b>T2</b> = close-range only &middot;
        <b>T3</b> = distant only — same number of images in each.
      </p>
      <p>
        <b>Two objects, opposite extremes</b> on both axes the project varies: the bollard small, compact
        and convex under semi-gloss paint — the easy end; the information sign taller, a flat slab with two
        near-identical faces under a glossy cover that mirrors the street — the hard end. A strategy that
        survives both should hold for everything in between.
      </p>
      <p>
        <b>Two methods, one from each family</b> — COLMAP matches features between views, MASt3R-GA
        regresses geometry from a learned prior. Running both asks whether capture geometry matters the
        same way for fundamentally different principles.
      </p>
    </div>
  </div>

  <div class="legend-bar">
    <span><b style="color:var(--text)">Colouring</b></span>
    <span><span class="swatch" style="background:var(--green)"></span>within t (correct)&nbsp;&nbsp;<span class="swatch" style="background:var(--red)"></span>beyond t</span>
    <span>heatmap: <span class="gradient-bar" style="display:inline-block; vertical-align:middle"></span> 0…15 cm</span>
    <span><span class="swatch" style="background:var(--ref-magenta)"></span>LiDAR / reconstruction overlay</span>
  </div>

  <hr class="sep">
  <section>
    <h2>Source data — every reconstruction, side by side</h2>
    <div class="subtitle" style="max-width:92ch">
      Each row is one method; the three columns are the three capture approaches. Colour is distance to
      the LiDAR reference. The line under each row says what changing the capture did to that method on
      that object.
    </div>
  </section>
  <section id="objects-root"></section>

  <hr class="sep">
  <section>
    <div style="display:flex; align-items:baseline; gap:14px; flex-wrap:wrap;">
      <h2>Summary — object × approach × method</h2>
      <div class="tabs" id="thr-toggle">
        <button class="tab-btn active" data-thr="3">3 cm</button>
        <button class="tab-btn" data-thr="5">5 cm</button>
        <button class="tab-btn" data-thr="10">10 cm</button>
      </div>
    </div>
    <div class="subtitle" style="max-width:92ch">
      The threshold above drives this table and the chart below it. A score that recovers as the
      threshold widens means the surface is <b>there but offset</b>; one that stays low even at 10&nbsp;cm
      means the geometry is <b>simply missing</b>. Best F1 per group is highlighted.
    </div>
    <div class="with-aside">
      <div class="grid-wrap"><div id="summary-table-wrap"></div></div>
      <div class="aside">
        <span class="k">What to look for</span>
        On the <b>bollard</b> the three rows sit within a couple of points of each other — a small,
        simple object is forgiving. On the <b>information sign</b> the <b>T2</b> row collapses for both
        methods: shooting only from close up never sees the whole slab, so large parts of it are never
        reconstructed at all.
      </div>
    </div>
  </section>

  <hr class="sep">
  <section>
    <h2 id="chart-title">F1@3cm by capture approach</h2>
    <div class="with-aside">
      <div class="panel"><svg id="f1-chart" viewBox="0 0 1000 340" style="width:100%; height:340px;"></svg></div>
      <div class="aside">
        <span class="k">Reading the bars</span>
        The grey <b>Δ</b> above each bar is how much F1 gains between 3 and 10&nbsp;cm. A <b>small Δ</b>
        means the surface is already where it should be. A <b>large Δ on a low bar</b> means the points
        are far out — and if the bar is still low at 10&nbsp;cm, that geometry was never built.
        <br><br>
        The line under each group says what changing the capture cost that method.
      </div>
    </div>
  </section>

  <hr class="sep">
  <section>
    <h2>Is the difference between capture approaches real?</h2>
    <div class="subtitle" style="max-width:92ch">
      A gap of a few points could just be luck of which surface patches happened to be covered. To tell,
      each pair of approaches is re-scored 2000 times on resampled patches of the object; the histogram
      is the spread of differences that produces. <b>If it sits entirely to one side of 0</b>, the
      approaches genuinely differ. <b>If it straddles 0</b>, the ranking is noise and the approaches are
      indistinguishable at this sample size. Computed at 3&nbsp;cm.
    </div>
    <div class="with-aside">
      <div>
        <div id="diff-hist-grid" style="display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:12px;"></div>
        <div class="params" id="stats-caveats" style="margin-top:12px"></div>
      </div>
      <div class="aside">
        <span class="k">The answer</span>
        <b>It depends on the object — the split is by size and shape, not by method.</b> On the compact
        bollard the strategy is <b>inconsequential</b>: nothing is resolvable for either family. On the
        taller, flat-faced sign it is <b>decisive</b> — close-range-only loses 33–37 points. Both methods
        agree, so it is the object's property, not an algorithm's.
      </div>
    </div>
  </section>


  <footer>exp_081–092 · src/registration/build_capture_comparison_page.py</footer>
</div>
"""


MAIN_JS = r"""<script>
const DATA = JSON.parse(document.getElementById('page-data').textContent);
const FLOOR_CM = DATA.floor_cm;
const RENDER_CAP = 8000;
const HEAT_VMAX = 15.0; // cm mapped to the top of the turbo scale

// ---------- grid-accelerated DBSCAN (Ester et al. 1996), from bus_stop_001 ----------
function dbscan(pos, eps, minPts) {
  const n = pos.length / 3;
  const cell = eps > 0 ? eps : 0.001;
  const grid = new Map();
  const keyOf = (ix, iy, iz) => ix + ',' + iy + ',' + iz;
  const cellIdx = new Int32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const ix = Math.floor(pos[i*3] / cell), iy = Math.floor(pos[i*3+1] / cell), iz = Math.floor(pos[i*3+2] / cell);
    cellIdx[i*3]=ix; cellIdx[i*3+1]=iy; cellIdx[i*3+2]=iz;
    const k = keyOf(ix, iy, iz);
    if (!grid.has(k)) grid.set(k, []);
    grid.get(k).push(i);
  }
  const eps2 = eps * eps;
  function regionQuery(i) {
    const ix = cellIdx[i*3], iy = cellIdx[i*3+1], iz = cellIdx[i*3+2];
    const xi = pos[i*3], yi = pos[i*3+1], zi = pos[i*3+2];
    const out = [];
    for (let dx=-1; dx<=1; dx++) for (let dy=-1; dy<=1; dy++) for (let dz=-1; dz<=1; dz++) {
      const c = grid.get(keyOf(ix+dx, iy+dy, iz+dz)); if (!c) continue;
      for (const j of c) {
        const ddx = pos[j*3]-xi, ddy = pos[j*3+1]-yi, ddz = pos[j*3+2]-zi;
        if (ddx*ddx + ddy*ddy + ddz*ddz <= eps2) out.push(j);
      }
    }
    return out;
  }
  const UNVISITED = -2, NOISE = -1;
  const labels = new Int32Array(n).fill(UNVISITED);
  let clusterId = 0;
  for (let i = 0; i < n; i++) {
    if (labels[i] !== UNVISITED) continue;
    const neighbors = regionQuery(i);
    if (neighbors.length < minPts) { labels[i] = NOISE; continue; }
    labels[i] = clusterId;
    const seeds = neighbors.slice(); let qi = 0;
    while (qi < seeds.length) {
      const q = seeds[qi++];
      if (labels[q] === NOISE) labels[q] = clusterId;
      if (labels[q] !== UNVISITED) continue;
      labels[q] = clusterId;
      const qn = regionQuery(q);
      if (qn.length >= minPts) for (const x of qn) seeds.push(x);
    }
    clusterId++;
  }
  return { labels, nClusters: clusterId };
}

function b64ToFloat32(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Float32Array(bytes.buffer);
}

// ---------- mat4 + WebGL viewer (Z-up, Open3D convention) — from bus_stop_001 ----------
function mat4Perspective(fovy, aspect, near, far) {
  const f = 1 / Math.tan(fovy / 2), nf = 1 / (near - far);
  return new Float32Array([f/aspect,0,0,0, 0,f,0,0, 0,0,(far+near)*nf,-1, 0,0,2*far*near*nf,0]);
}
function mat4LookAt(eye, center, up) {
  let zx=eye[0]-center[0], zy=eye[1]-center[1], zz=eye[2]-center[2];
  let zl=Math.hypot(zx,zy,zz)||1; zx/=zl; zy/=zl; zz/=zl;
  let xx=up[1]*zz-up[2]*zy, xy=up[2]*zx-up[0]*zz, xz=up[0]*zy-up[1]*zx;
  let xl=Math.hypot(xx,xy,xz)||1; xx/=xl; xy/=xl; xz/=xl;
  let yx=zy*xz-zz*xy, yy=zz*xx-zx*xz, yz=zx*xy-zy*xx;
  return new Float32Array([xx,yx,zx,0, xy,yy,zy,0, xz,yz,zz,0,
    -(xx*eye[0]+xy*eye[1]+xz*eye[2]), -(yx*eye[0]+yy*eye[1]+yz*eye[2]), -(zx*eye[0]+zy*eye[1]+zz*eye[2]), 1]);
}
function mat4Multiply(a,b) {
  const out = new Float32Array(16);
  for (let i=0;i<4;i++) for (let j=0;j<4;j++) out[i*4+j]=a[j]*b[i*4]+a[4+j]*b[i*4+1]+a[8+j]*b[i*4+2]+a[12+j]*b[i*4+3];
  return out;
}
const VERT_SRC = `attribute vec3 aPosition; attribute vec3 aColor; uniform mat4 uMVP; uniform float uPointSize;
  varying vec3 vColor; void main(){ gl_Position=uMVP*vec4(aPosition,1.0); gl_PointSize=uPointSize; vColor=aColor; }`;
const FRAG_SRC = `precision mediump float; varying vec3 vColor;
  void main(){ vec2 d=gl_PointCoord-vec2(0.5); if(dot(d,d)>0.25) discard; gl_FragColor=vec4(vColor,1.0); }`;
function compileShader(gl, type, src) {
  const sh = gl.createShader(type); gl.shaderSource(sh, src); gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) console.error(gl.getShaderInfoLog(sh));
  return sh;
}
function makeViewer(canvas, layers) {
  const gl = canvas.getContext('webgl', { antialias: true, preserveDrawingBuffer: true });
  if (!gl) { canvas.replaceWith(document.createTextNode('WebGL not available')); return null; }
  const prog = gl.createProgram();
  gl.attachShader(prog, compileShader(gl, gl.VERTEX_SHADER, VERT_SRC));
  gl.attachShader(prog, compileShader(gl, gl.FRAGMENT_SHADER, FRAG_SRC));
  gl.linkProgram(prog); gl.useProgram(prog);
  const aPosition = gl.getAttribLocation(prog, 'aPosition');
  const aColor = gl.getAttribLocation(prog, 'aColor');
  const uMVP = gl.getUniformLocation(prog, 'uMVP');
  const uPointSize = gl.getUniformLocation(prog, 'uPointSize');
  function makeBuffer(data){ const b=gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER,b); gl.bufferData(gl.ARRAY_BUFFER,data,gl.DYNAMIC_DRAW); return b; }
  const state = layers.map(l => ({ posBuf: makeBuffer(l.pos), colorBuf: makeBuffer(l.color), n: l.pos.length/3, on: l.defaultOn !== false, sizeMul: l.sizeMul || 1 }));
  let minX=Infinity,minY=Infinity,minZ=Infinity,maxX=-Infinity,maxY=-Infinity,maxZ=-Infinity;
  for (const l of layers) for (let i=0;i<l.pos.length;i+=3){ const x=l.pos[i],y=l.pos[i+1],z=l.pos[i+2];
    if(x<minX)minX=x; if(x>maxX)maxX=x; if(y<minY)minY=y; if(y>maxY)maxY=y; if(z<minZ)minZ=z; if(z>maxZ)maxZ=z; }
  const center = [(minX+maxX)/2,(minY+maxY)/2,(minZ+maxZ)/2];
  const diag = Math.hypot(maxX-minX,maxY-minY,maxZ-minZ) || 1;
  let azimuth = 0.6, elevation = 0.25, distance = diag * 1.35;
  function resize(){ const dpr=Math.min(window.devicePixelRatio||1,2); const w=canvas.clientWidth*dpr,h=canvas.clientHeight*dpr;
    if(canvas.width!==w||canvas.height!==h){ canvas.width=w; canvas.height=h; } }
  function draw(){
    resize(); gl.viewport(0,0,canvas.width,canvas.height); gl.enable(gl.DEPTH_TEST);
    gl.clearColor(1,1,1,1); gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
    const eye=[center[0]+distance*Math.cos(elevation)*Math.cos(azimuth),
      center[1]+distance*Math.cos(elevation)*Math.sin(azimuth), center[2]+distance*Math.sin(elevation)];
    const view=mat4LookAt(eye,center,[0,0,1]);
    const proj=mat4Perspective(Math.PI/4, canvas.width/canvas.height, diag*0.01, diag*10);
    const mvp=mat4Multiply(proj,view);
    gl.useProgram(prog); gl.uniformMatrix4fv(uMVP,false,mvp);
    const baseSize = Math.max(2.2, Math.min(canvas.width,canvas.height)/185);
    for (const s of state) {
      if(!s.on||s.n===0) continue;
      gl.uniform1f(uPointSize, baseSize * s.sizeMul);
      gl.bindBuffer(gl.ARRAY_BUFFER,s.posBuf); gl.enableVertexAttribArray(aPosition); gl.vertexAttribPointer(aPosition,3,gl.FLOAT,false,0,0);
      gl.bindBuffer(gl.ARRAY_BUFFER,s.colorBuf); gl.enableVertexAttribArray(aColor); gl.vertexAttribPointer(aColor,3,gl.FLOAT,false,0,0);
      gl.drawArrays(gl.POINTS,0,s.n);
    }
  }
  let dragging=false,lastX=0,lastY=0;
  canvas.addEventListener('pointerdown',e=>{ dragging=true; lastX=e.clientX; lastY=e.clientY; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener('pointerup',()=>dragging=false);
  canvas.addEventListener('pointermove',e=>{ if(!dragging)return;
    azimuth+=(e.clientX-lastX)*0.008; elevation=Math.max(-1.5,Math.min(1.5,elevation-(e.clientY-lastY)*0.008));
    lastX=e.clientX; lastY=e.clientY; draw(); });
  canvas.addEventListener('wheel',e=>{ e.preventDefault(); distance=Math.max(diag*0.1,Math.min(diag*6,distance*(1+e.deltaY*0.001))); draw(); }, { passive:false });
  const onResize = () => draw();
  window.addEventListener('resize', onResize);
  draw();
  return {
    draw,
    setLayer(idx,pos,color){ state[idx].n=pos.length/3;
      gl.bindBuffer(gl.ARRAY_BUFFER,state[idx].posBuf); gl.bufferData(gl.ARRAY_BUFFER,pos,gl.DYNAMIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER,state[idx].colorBuf); gl.bufferData(gl.ARRAY_BUFFER,color,gl.DYNAMIC_DRAW); draw(); },
    setLayerOn(idx,on){ state[idx].on=on; draw(); },
    // frees the WebGL context - browsers cap the number of *live* contexts per page
    // (Chrome: ~16); with dozens of thumbnail viewers on one page we must give up
    // off-screen contexts or the oldest ones get silently evicted and go blank.
    destroy(){ window.removeEventListener('resize', onResize); const ext=gl.getExtension('WEBGL_lose_context'); if(ext) ext.loseContext(); },
  };
}

// ---------- colours ----------
const GREEN=[0.102,0.675,0.702], RED=[0.882,0.420,0.243], MAGENTA=[0.169,0.169,0.157]; // #1aacb3, #e16b3e, #2b2b28 (teal instead of green: validated far from red and from the undefined violet)
const TURBO=[[48,18,59],[68,88,203],[62,155,254],[24,213,204],[70,247,131],[164,252,59],[225,220,55],[253,141,39],[122,4,3]];
function turbo(dCm, vmax){
  let f=Math.max(0,Math.min(1,dCm/vmax)); let x=f*(TURBO.length-1); let i=Math.floor(x); let t=x-i;
  if(i>=TURBO.length-1){ i=TURBO.length-2; t=1; }
  const a=TURBO[i], b=TURBO[i+1];
  return [(a[0]+(b[0]-a[0])*t)/255,(a[1]+(b[1]-a[1])*t)/255,(a[2]+(b[2]-a[2])*t)/255];
}
function solidColor(n,rgb){ const out=new Float32Array(n*3); for(let i=0;i<n;i++){ out[i*3]=rgb[0]; out[i*3+1]=rgb[1]; out[i*3+2]=rgb[2]; } return out; }
function pctWithin(distCm,t){ let c=0; for(let i=0;i<distCm.length;i++) if(distCm[i]<=t) c++; return distCm.length? c/distCm.length*100 : 0; }

// ---------- per-panel state ----------
const panelState = {};
for (const key in DATA.panels) {
  const d = DATA.panels[key];
  panelState[key] = {
    d,
    belowPos: b64ToFloat32(d.below_pos),
    belowDist: b64ToFloat32(d.below_dist_cm),
    candidatePos: b64ToFloat32(d.candidate_pos),
    candidateDist: b64ToFloat32(d.candidate_dist_cm),
    targetDist: b64ToFloat32(d.target_dist_cm),
    nBelowTrue: d.n_below_true,
    nCandTrue: d.n_candidates_true,
    keptMask: null,
  };
  // default = all points kept, so the first refresh (rAF) is safe even before the
  // per-object tuner has run its first recomputeExclusion.
  panelState[key].keptMask = new Uint8Array(panelState[key].candidateDist.length).fill(1);
}
// target positions are shared per object
const objTargetPos = {};
for (const o of DATA.objects) objTargetPos[o.id] = b64ToFloat32(o.target_pos);

// re-run DBSCAN for one panel's candidate pool under the given tuner params
function recomputeExclusion(key, ft, eps, mp, applyDbscan) {
  const s = panelState[key];
  const n = s.candidateDist.length;
  if (!applyDbscan) { s.keptMask = new Uint8Array(n).fill(1); return; }
  const active = [];
  for (let i=0;i<n;i++) if (s.candidateDist[i] > ft) active.push(i);
  const pos = new Float32Array(active.length*3);
  for (let k=0;k<active.length;k++){ const i=active[k]; pos[k*3]=s.candidatePos[i*3]; pos[k*3+1]=s.candidatePos[i*3+1]; pos[k*3+2]=s.candidatePos[i*3+2]; }
  const { labels } = dbscan(pos, eps/100, mp);
  const kept = new Uint8Array(n).fill(1);
  for (let k=0;k<active.length;k++) if (labels[k] !== -1) kept[active[k]] = 0;
  s.keptMask = kept;
}

// population-weighted accuracy% at threshold t (groups subsampled at different rates)
function accuracyPct(key, t) {
  const s = panelState[key];
  let belowWithin=0; for (let i=0;i<s.belowDist.length;i++) if (s.belowDist[i]<=t) belowWithin++;
  const belowWithinEst = s.belowDist.length ? s.nBelowTrue*(belowWithin/s.belowDist.length) : 0;
  let keptWithin=0, keptTotal=0;
  for (let i=0;i<s.candidateDist.length;i++){ if(!s.keptMask[i]) continue; keptTotal++; if(s.candidateDist[i]<=t) keptWithin++; }
  const rate = s.candidateDist.length ? (1/s.candidateDist.length) : 0;
  const keptWithinEst = s.nCandTrue*keptWithin*rate;
  const keptTotalEst = s.nCandTrue*keptTotal*rate;
  const totalEst = s.nBelowTrue + keptTotalEst;
  return { pct: totalEst>0 ? (belowWithinEst+keptWithinEst)/totalEst*100 : 0,
           nExcludedEst: Math.round(s.nCandTrue - keptTotalEst) };
}
function inlierRmse(key, t) {
  const s = panelState[key]; let sum=0, n=0;
  for (let i=0;i<s.belowDist.length;i++){ const d=s.belowDist[i]; if(d<=t){ sum+=d*d; n++; } }
  for (let i=0;i<s.candidateDist.length;i++){ if(!s.keptMask[i]) continue; const d=s.candidateDist[i]; if(d<=t){ sum+=d*d; n++; } }
  return n? Math.sqrt(sum/n) : NaN;
}
function panelMetrics(key, t) {
  const s = panelState[key];
  const acc = accuracyPct(key, t);
  const comp = pctWithin(s.targetDist, t);
  const f1 = (acc.pct+comp)>0 ? 2*acc.pct*comp/(acc.pct+comp) : 0;
  return { accPct: acc.pct, compPct: comp, f1, nExcluded: acc.nExcludedEst, rmse: inlierRmse(key, t) };
}

// render the "main" layer for a panel
function buildMain(key, tab, t, colorMode) {
  const s = panelState[key];
  if (tab === 'completeness') {
    const pos = objTargetPos[s.d.object]; const td = s.targetDist;
    const color = new Float32Array(td.length*3);
    for (let i=0;i<td.length;i++){ const c = colorMode==='turbo' ? turbo(td[i],HEAT_VMAX) : (td[i]<=t?GREEN:RED);
      color[i*3]=c[0]; color[i*3+1]=c[1]; color[i*3+2]=c[2]; }
    return { pos, color };
  }
  const pos=[], color=[];
  const nBelow=Math.min(RENDER_CAP, s.belowDist.length);
  for (let i=0;i<nBelow;i++){ pos.push(s.belowPos[i*3],s.belowPos[i*3+1],s.belowPos[i*3+2]);
    const c = colorMode==='turbo' ? turbo(s.belowDist[i],HEAT_VMAX) : (s.belowDist[i]<=t?GREEN:RED); color.push(c[0],c[1],c[2]); }
  let shown=0;
  for (let i=0;i<s.candidateDist.length && shown<RENDER_CAP;i++){ if(!s.keptMask[i]) continue;
    pos.push(s.candidatePos[i*3],s.candidatePos[i*3+1],s.candidatePos[i*3+2]);
    const c = colorMode==='turbo' ? turbo(s.candidateDist[i],HEAT_VMAX) : (s.candidateDist[i]<=t?GREEN:RED); color.push(c[0],c[1],c[2]); shown++; }
  return { pos:new Float32Array(pos), color:new Float32Array(color) };
}
function keptReconPos(key) {
  const s = panelState[key]; const pos=[];
  const nBelow=Math.min(RENDER_CAP, s.belowDist.length);
  for (let i=0;i<nBelow;i++) pos.push(s.belowPos[i*3],s.belowPos[i*3+1],s.belowPos[i*3+2]);
  let shown=0;
  for (let i=0;i<s.candidateDist.length && shown<RENDER_CAP;i++){ if(!s.keptMask[i]) continue;
    pos.push(s.candidatePos[i*3],s.candidatePos[i*3+1],s.candidatePos[i*3+2]); shown++; }
  return new Float32Array(pos);
}


// ---------- build the page ----------
const APPROACHES = [1,2,3];
const APPROACH_COLORVAR = { 1:'--t1', 2:'--t2', 3:'--t3' };
const objRoot = document.getElementById('objects-root');
const panelApi = {};   // key -> { refresh() }
const objTuner = {};   // objectId -> { ft, eps, mp, applyDbscan }

for (const obj of DATA.objects) {
  const methods = [...new Set(obj.panels.map(k => panelState[k].d.method))];
  const block = document.createElement('div');
  block.className = 'obj-block';
  block.innerHTML = `
    <div class="obj-head">
      <h2>${obj.title}</h2>
      <span class="chip">${obj.shape}</span>
      <span class="chip">ref median spacing ${obj.ref_spacing_cm.toFixed(2)} cm</span>
      <span class="chip">gap detection: ft${obj.dbscan.ft}/eps${obj.dbscan.eps}/mp${obj.dbscan.mp}</span>
    </div>
    <div class="ref-note">${obj.ref_note}</div>
    <div class="grid-wrap"><div class="obj-grid" id="grid-${obj.id}"></div></div>
  `;
  objRoot.appendChild(block);


  // grid: header row, then one row per method
  const grid = block.querySelector(`#grid-${obj.id}`);
  grid.appendChild(document.createElement('div')); // corner
  for (const ap of APPROACHES) {
    const h=document.createElement('div'); h.className='col-head';
    h.innerHTML = `T${ap}<span class="hint">${DATA.approach_label[ap].replace('T'+ap+' · ','')}</span>`;
    grid.appendChild(h);
  }
  for (const method of methods) {
    const rh=document.createElement('div'); rh.className='row-head'; rh.textContent=DATA.method_label[method]; grid.appendChild(rh);
    for (const ap of APPROACHES) {
      const key = `${obj.id}__${method}__${ap}`;
      grid.appendChild(buildPanel(key));
    }
    // what changing the capture did to THIS method on THIS object - one line per triple,
    // recomputed whenever the threshold changes (see refreshRowNotes)
    const note = document.createElement('div');
    note.className = 'row-note';
    note.id = `rownote-${obj.id}__${method}`;
    grid.appendChild(note);
  }

  // Gap-detection settings are fixed per object (the values tuned in tuner.html) rather
  // than exposed as sliders here: this page compares capture approaches, so the gap
  // handling has to be one constant, not something the reader can move mid-comparison.
  objTuner[obj.id] = { ft:obj.dbscan.ft, eps:obj.dbscan.eps, mp:obj.dbscan.mp, applyDbscan:true };
}

// Hard cap on simultaneously-live WebGL contexts, enforced ourselves rather than
// trusting a browser/GPU-specific limit (Chrome warns around ~16, but real GPUs/drivers
// can silently evict sooner). The IntersectionObserver below is the primary mechanism
// (free contexts once a panel is well off-screen); this cap is a backstop for the case
// where more panels are simultaneously near-viewport than the browser can hold - it
// evicts off-screen entries first and only touches a visible one as an absolute last
// resort (a big monitor showing more rows than any browser could hold live at once).
const __liveViewers = []; // {teardown, visible}, oldest-touched first
const __MAX_LIVE_VIEWERS = 14;
function __evictIfNeeded() {
  while (__liveViewers.length > __MAX_LIVE_VIEWERS) {
    let idx = __liveViewers.findIndex(v => !v.visible);
    if (idx === -1) idx = 0;
    __liveViewers.splice(idx, 1)[0].teardown();
  }
}
function __registerViewer(entry) { entry.visible = true; __liveViewers.push(entry); __evictIfNeeded(); }
function __touchViewer(entry) {
  entry.visible = true;
  const i = __liveViewers.indexOf(entry);
  if (i >= 0) { __liveViewers.splice(i, 1); __liveViewers.push(entry); }
}
function __markInvisible(entry) { entry.visible = false; }
function __unregisterViewer(entry) {
  const i = __liveViewers.indexOf(entry);
  if (i >= 0) __liveViewers.splice(i, 1);
}

function buildPanel(key) {
  const s = panelState[key], d = s.d;
  const panel = document.createElement('div');
  panel.className = 'panel';
  panel.innerHTML = `
    <div class="panel-title"><span>${d.label}</span><span class="exp">${d.exp_id}</span></div>
    <canvas></canvas>
    <div class="tabs">
      <button class="tab-btn active" data-tab="accuracy">Accuracy</button>
      <button class="tab-btn" data-tab="completeness">Completeness</button>
      <button class="toggle-btn" data-color>heatmap</button>
      <button class="toggle-btn" data-overlay>ref</button>
    </div>
    <div class="slider-row"><span>t=</span><input type="range" min="0.5" max="15" step="0.1" value="3">
      <span class="mono thr-val">3.0cm</span>
      <div class="preset-btns"><button class="preset-btn active" data-t="3">3</button><button class="preset-btn" data-t="5">5</button><button class="preset-btn" data-t="10">10</button></div>
    </div>
    <div class="panel-stats"><span class="tab-pct">-</span> within t &nbsp;·&nbsp; <span class="f1">F1=-</span><br>
      <span class="mono">n=${d.n_source_total.toLocaleString('en-US')} · ref=${d.n_target_total.toLocaleString('en-US')} · excl≈<span class="excl">0</span></span></div>
  `;
  let canvas=panel.querySelector('canvas');
  const slider=panel.querySelector('input[type=range]');
  const thrVal=panel.querySelector('.thr-val');
  const tabPct=panel.querySelector('.tab-pct');
  const f1El=panel.querySelector('.f1');
  const exclEl=panel.querySelector('.excl');
  const tabBtns=panel.querySelectorAll('.tab-btn');
  const colorBtn=panel.querySelector('[data-color]');
  const overlayBtn=panel.querySelector('[data-overlay]');
  const presetBtns=panel.querySelectorAll('.preset-btn');
  let activeTab='accuracy', colorMode='threshold', viewer=null;

  function overlayLayer(){ return activeTab==='accuracy' ? objTargetPos[s.d.object] : keptReconPos(key); }
  function refresh(){
    const t=parseFloat(slider.value);
    const m=panelMetrics(key,t);
    tabPct.textContent=(activeTab==='accuracy'?m.accPct:m.compPct).toFixed(1)+'%';
    f1El.textContent='F1='+m.f1.toFixed(1);
    exclEl.textContent=m.nExcluded.toLocaleString('en-US');
    if(!viewer) return; // off-screen right now - ensureViewer() will pick up the current state when it scrolls back in
    const main=buildMain(key,activeTab,t,colorMode);
    const ov=overlayLayer();
    viewer.setLayer(0,main.pos,main.color); viewer.setLayer(1,ov,solidColor(ov.length/3,MAGENTA)); viewer.setLayerOn(1,overlayBtn.classList.contains('active'));
  }
  const __lruEntry = { teardown: () => teardownViewer() };
  function ensureViewer(){
    if(viewer) { __touchViewer(__lruEntry); return; }
    const t=parseFloat(slider.value);
    const main=buildMain(key,activeTab,t,colorMode);
    const ov=overlayLayer();
    viewer=makeViewer(canvas,[{pos:main.pos,color:main.color,defaultOn:true},{pos:ov,color:solidColor(ov.length/3,MAGENTA),defaultOn:false,sizeMul:0.85}]);
    viewer.setLayerOn(1,overlayBtn.classList.contains('active'));
    __registerViewer(__lruEntry);
  }
  function teardownViewer(){
    if(!viewer) return;
    viewer.destroy();
    viewer=null;
    __unregisterViewer(__lruEntry);
    // A canvas whose WebGL context was explicitly lost via loseContext() keeps returning
    // that SAME lost context from getContext() forever - there's no getting a live one
    // back on that element without a manual restoreContext()+re-init dance. Swapping in a
    // fresh (unused) canvas node is simpler and gives ensureViewer() a genuinely new context.
    const fresh = canvas.cloneNode();
    canvas.replaceWith(fresh);
    io.unobserve(canvas);
    canvas = fresh;
    io.observe(canvas);
  }
  // Only ~16 WebGL contexts can be live at once in most browsers (fewer on some real
  // GPUs/drivers); this page can have dozens of panels, so give each canvas a context
  // only while it's near the viewport, with the LRU cap above as a hard backstop.
  const io = new IntersectionObserver(entries => {
    for (const e of entries) {
      if (e.isIntersecting) ensureViewer();
      else { __markInvisible(__lruEntry); teardownViewer(); }
    }
  }, { rootMargin: '150px 0px 150px 0px' });
  io.observe(canvas);
  panelApi[key]={ refresh };
  requestAnimationFrame(refresh);
  slider.addEventListener('input',()=>{ thrVal.textContent=parseFloat(slider.value).toFixed(1)+'cm';
    presetBtns.forEach(b=>b.classList.toggle('active',parseFloat(b.dataset.t)===parseFloat(slider.value))); refresh(); });
  presetBtns.forEach(b=>b.addEventListener('click',()=>{ slider.value=b.dataset.t; slider.dispatchEvent(new Event('input')); }));
  tabBtns.forEach(b=>b.addEventListener('click',()=>{ tabBtns.forEach(x=>x.classList.remove('active')); b.classList.add('active'); activeTab=b.dataset.tab; refresh(); }));
  colorBtn.addEventListener('click',()=>{ colorMode = colorMode==='threshold'?'turbo':'threshold'; colorBtn.classList.toggle('active',colorMode==='turbo'); refresh(); });
  overlayBtn.addEventListener('click',()=>{ overlayBtn.classList.toggle('active'); if(viewer) viewer.setLayerOn(1,overlayBtn.classList.contains('active')); });
  return panel;
}

function recomputeObject(objId) {
  const t = objTuner[objId];
  const obj = DATA.objects.find(o=>o.id===objId);
  for (const key of obj.panels) {
    recomputeExclusion(key, t.ft, t.eps, t.mp, t.applyDbscan);
    panelApi[key].refresh();
  }
  updateTable(); updateChart(); refreshRowNotes();
}

// Metric threshold for the table and the F1 chart. panelMetrics(key, t) already takes any
// t, so switching this recomputes both live in the browser - no rebuild needed. The
// bootstrap CIs under "Is the difference real?" are precomputed in Python at 3cm only,
// so the narrative below deliberately stays at 3.0 regardless of this setting.
let activeThreshold = 3.0;

// ---------- summary table ----------
function fmtReg(r){ return r==null ? '—' : (r*100).toFixed(1)+'%'; }
function buildTable() {
  const wrap=document.getElementById('summary-table-wrap');
  let h='<table class="summary"><thead><tr>'
    + '<th class="txt">Object</th><th class="txt">Approach</th><th class="txt">Method</th>'
    + '<th>F1</th><th>Acc</th><th>Comp</th><th>Acc median</th><th>Comp median</th>'
    + '<th>reg-rate</th><th>#pts (raw→matched)</th><th>inlier RMSE</th><th>excl≈</th></tr></thead><tbody>';
  for (const obj of DATA.objects) {
    const methods=[...new Set(obj.panels.map(k=>panelState[k].d.method))];
    for (const method of methods) {
      for (const ap of APPROACHES) {
        const key=`${obj.id}__${method}__${ap}`; const d=panelState[key].d;
        h+=`<tr id="row-${key}" ${ap===1?'class="grouprule"':''}>`
          + `<td class="txt">${ap===1&&method===methods[0]?obj.title:''}</td>`
          + `<td class="txt">T${ap}</td><td class="txt">${DATA.method_label[method]}</td>`
          + `<td class="f1cell" data-col="f1">–</td><td data-col="acc">–</td><td data-col="comp">–</td>`
          + `<td>${d.accuracy_median_cm.toFixed(2)}</td><td>${d.completeness_median_cm.toFixed(2)}</td>`
          + `<td>${fmtReg(d.reg_rate)}</td><td class="mono">${d.raw_points.toLocaleString('en-US')}→${d.matched_points.toLocaleString('en-US')}</td>`
          + `<td data-col="rmse">–</td><td data-col="excl">–</td></tr>`;
      }
    }
  }
  h+='</tbody></table>';
  wrap.innerHTML=h;
}
// One sentence per (object, method) triple under the viewers: did the capture approach
// change this reconstruction, and if so how - a deficit that closes as the threshold widens
// is an offset, one that persists is geometry that was never built.
function refreshRowNotes() {
  for (const obj of DATA.objects) {
    const methods = [...new Set(obj.panels.map(k => panelState[k].d.method))];
    for (const method of methods) {
      const el = document.getElementById(`rownote-${obj.id}__${method}`);
      if (!el) continue;
      const f1 = APPROACHES.map(ap => panelMetrics(`${obj.id}__${method}__${ap}`, activeThreshold).f1);
      const spread = Math.max(...f1) - Math.min(...f1);
      const worst = APPROACHES[f1.indexOf(Math.min(...f1))];
      const wide = panelMetrics(`${obj.id}__${method}__${worst}`, 10.0).f1;
      const tight = panelMetrics(`${obj.id}__${method}__${worst}`, 3.0).f1;
      const name = DATA.approach_label[worst].split('·')[1].trim();
      if (spread < 5) {
        el.innerHTML = `<b>Capture barely matters here.</b> All three land within `
          + `${spread.toFixed(1)} points of each other — the shape is simple enough that every route `
          + `around it sees essentially the same surface.`;
      } else if (wide < 90) {
        el.innerHTML = `<b>${name} costs ${spread.toFixed(0)} points, and the loss is permanent.</b> `
          + `Even at a 10 cm threshold it only reaches ${wide.toFixed(0)}% — those parts of the object `
          + `were never reconstructed, not merely misplaced.`;
      } else {
        el.innerHTML = `<b>${name} costs ${spread.toFixed(0)} points, but the surface is there.</b> `
          + `Widening the threshold to 10 cm recovers it to ${wide.toFixed(0)}% (from `
          + `${tight.toFixed(0)}% at 3 cm) — the geometry is built, just offset.`;
      }
    }
  }
}

function updateTable() {
  for (const obj of DATA.objects) {
    const methods=[...new Set(obj.panels.map(k=>panelState[k].d.method))];
    for (const method of methods) {
      let bestF1=-1, bestKey=null;
      const rows=[];
      for (const ap of APPROACHES) {
        const key=`${obj.id}__${method}__${ap}`; const m=panelMetrics(key,activeThreshold);
        rows.push({key,m}); if(m.f1>bestF1){ bestF1=m.f1; bestKey=key; }
      }
      for (const {key,m} of rows) {
        const tr=document.getElementById(`row-${key}`); if(!tr) continue;
        tr.querySelector('[data-col=f1]').textContent=m.f1.toFixed(1);
        tr.querySelector('[data-col=acc]').textContent=m.accPct.toFixed(1);
        tr.querySelector('[data-col=comp]').textContent=m.compPct.toFixed(1);
        tr.querySelector('[data-col=rmse]').textContent=isNaN(m.rmse)?'—':m.rmse.toFixed(2);
        tr.querySelector('[data-col=excl]').textContent=m.nExcluded.toLocaleString('en-US');
        tr.classList.toggle('best', key===bestKey);
        tr.querySelector('[data-col=f1]').classList.toggle('best-cell', key===bestKey);
      }
    }
  }
}

// ---------- grouped F1 bar chart ----------
function cssvar(v){ return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
function updateChart() {
  const svg=document.getElementById('f1-chart');
  const groups=[];
  for (const obj of DATA.objects) {
    const methods=[...new Set(obj.panels.map(k=>panelState[k].d.method))];
    for (const method of methods) groups.push({ label:`${obj.title.replace('information_sign','is')} · ${DATA.method_label[method]}`, obj:obj.id, method });
  }
  const W=1000,H=340,padL=42,padR=12,padT=20,padB=64;
  const plotW=W-padL-padR, plotH=H-padT-padB;
  const gN=groups.length, gW=plotW/gN, barGap=9, innerPad=17;
  const barW=(gW-innerPad*2-barGap*(APPROACHES.length-1))/APPROACHES.length;
  const tick=cssvar('--text-faint'), textc=cssvar('--text-dim');
  let s='';
  for (let y=0;y<=100;y+=20){ const yy=padT+plotH-(y/100)*plotH;
    s+=`<line x1="${padL}" y1="${yy}" x2="${W-padR}" y2="${yy}" stroke="${tick}" stroke-opacity="0.16"/>`;
    s+=`<text x="${padL-6}" y="${yy+3}" font-size="10" fill="${tick}" text-anchor="end">${y}</text>`; }
  s+=`<text x="12" y="${padT+plotH/2}" font-size="10" fill="${tick}" transform="rotate(-90 12 ${padT+plotH/2})" text-anchor="middle">F1@${activeThreshold}cm (%)</text>`;
  groups.forEach((g,gi)=>{
    const gx=padL+gi*gW;
    APPROACHES.forEach((ap,ai)=>{
      const key=`${g.obj}__${g.method}__${ap}`; const m=panelMetrics(key,activeThreshold);
      const bx=gx+innerPad+ai*(barW+barGap); const bh=(m.f1/100)*plotH; const by=padT+plotH-bh;
      s+=`<rect x="${bx}" y="${by}" width="${barW}" height="${bh}" rx="5" fill="${cssvar(APPROACH_COLORVAR[ap])}" fill-opacity="0.8"><title>${g.label} · T${ap}: F1=${m.f1.toFixed(1)}</title></rect>`;
      s+=`<text x="${bx+barW/2}" y="${by-4}" font-size="9.5" fill="${tick}" text-anchor="middle">${m.f1.toFixed(0)}</text>`;
      // ΔF1 from 3 to 10cm: small = the deficit is an offset that a wider threshold absorbs,
      // large = the surface is genuinely absent and never comes back.
      const dF1 = panelMetrics(key,10.0).f1 - panelMetrics(key,3.0).f1;
      s+=`<text x="${bx+barW/2}" y="${by-15}" font-size="8.5" fill="${tick}" fill-opacity="0.75" text-anchor="middle">Δ${dF1.toFixed(0)}</text>`;
    });
    s+=`<text x="${gx+gW/2}" y="${H-42}" font-size="10.5" fill="${textc}" text-anchor="middle">${g.label}</text>`;
    // one-line read of what changing the capture did to THIS method on THIS object:
    // spread across the three approaches, at the threshold currently selected.
    const f1s = APPROACHES.map(ap => panelMetrics(`${g.obj}__${g.method}__${ap}`, activeThreshold).f1);
    const spread = Math.max(...f1s) - Math.min(...f1s);
    const worstAp = APPROACHES[f1s.indexOf(Math.min(...f1s))];
    const verdict = spread < 5
      ? 'capture barely matters here'
      : `T${worstAp} costs ${spread.toFixed(0)} pts`;
    s+=`<text x="${gx+gW/2}" y="${H-28}" font-size="9.5" fill="${tick}" fill-opacity="0.85" text-anchor="middle">${verdict}</text>`;
  });
  // legend
  const lx=padL, ly=H-16;
  // 130px was narrower than the labels themselves, so they ran into each other; space the
  // three entries evenly across the plot instead of at a fixed pitch.
  const legendPitch = Math.max(200, (W - padR - lx) / APPROACHES.length);
  APPROACHES.forEach((ap,ai)=>{ const x=lx+ai*legendPitch;
    s+=`<rect x="${x}" y="${ly-9}" width="11" height="11" rx="3" fill="${cssvar(APPROACH_COLORVAR[ap])}" fill-opacity="0.8"/>`;
    s+=`<text x="${x+17}" y="${ly}" font-size="10.5" fill="${textc}">${DATA.approach_label[ap]}</text>`; });
  svg.innerHTML=s;
}

// ---------- interpretation (auto from the live numbers + the static bootstrap significance test) ----------
function approachDesc(ap) {
  return DATA.approach_label[ap].split('·')[1].trim();  // "T2 · close-range only" -> "close-range only"
}

// Data-driven per-object verdict: is ANY pairwise F1 difference actually statistically
// resolvable (95% CI excludes 0), or is the nominal ranking within bootstrap noise?
// Uses DATA.sensitivity (static, computed once at default DBSCAN params), not the live
// tuner state, so this text doesn't need to move when a slider moves.
function buildSignificanceNarrative() {
  const legend = `<div class="subtitle" style="margin:0">`
    + `<b>T1</b> = close-range + distant &middot; <b>T2</b> = close-range only &middot; <b>T3</b> = distant only.</div>`;

  let blocks = '';
  for (const obj of DATA.objects) {
    const rows = DATA.sensitivity.filter(r => r.object === obj.id);
    if (!rows.length) continue;
    const heightTxt = obj.height_m ? `~${obj.height_m.toFixed(1)}&nbsp;m` : obj.shape;
    const anySig = rows.some(r => r.pairwise.some(p => !p.includes_zero));

    if (!anySig) {
      blocks += `<div class="headline"><b>${obj.title}</b> (${heightTxt}): no pairwise difference between `
        + `T1/T2/T3 is statistically significant, for either method — every 95%&nbsp;CI crosses 0. `
        + `The nominal ranking is noise: at this size you can shoot however you like and land on about the same numbers.</div>`;
      continue;
    }

    // an approach that is significantly worse than BOTH others, in every method
    let badAp = null;
    for (const ap of [1, 2, 3]) {
      const others = [1, 2, 3].filter(x => x !== ap);
      const worstEverywhere = rows.every(r => others.every(o => {
        const lo = Math.min(ap, o), hi = Math.max(ap, o);
        const p = r.pairwise.find(pp => pp.label === `T${lo}−T${hi}`);
        return p && !p.includes_zero && r.f1[ap - 1] < r.f1[o - 1];
      }));
      if (worstEverywhere) { badAp = ap; break; }
    }

    if (badAp) {
      const others = [1, 2, 3].filter(x => x !== badAp);
      const [lo, hi] = [Math.min(...others), Math.max(...others)];
      const tied = rows.every(r => (r.pairwise.find(pp => pp.label === `T${lo}−T${hi}`) || {}).includes_zero);
      const gaps = rows.map(r => {
        const meanOthers = others.reduce((s, o) => s + r.f1[o - 1], 0) / others.length;
        const label = DATA.method_label[r.method] + (r.method === 'mast3r_ga' ? ' (end-to-end)' : '');
        return `${label}: &Delta;&approx;${(meanOthers - r.f1[badAp - 1]).toFixed(0)}&nbsp;pts`;
      });
      blocks += `<div class="headline"><b>${obj.title}</b> (${heightTxt}): <b>T${badAp}</b> (${approachDesc(badAp)}) `
        + `is significantly worse than T${others[0]} and T${others[1]} for every method (95%&nbsp;CIs exclude 0)`
        + (tied ? `, and T${others[0]}/T${others[1]} are statistically indistinguishable from each other — both far better than T${badAp}.`
                : '.')
        + ` ${gaps.join(' &middot; ')}.</div>`;
    } else {
      blocks += `<div class="headline"><b>${obj.title}</b> (${heightTxt}): some pairwise differences are `
        + `significant, but no single approach is consistently worst across both methods.</div>`;
    }
  }
  return legend + blocks;
}

// threshold toggle: recompute the table + chart in place
document.querySelectorAll('#thr-toggle .tab-btn').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('#thr-toggle .tab-btn').forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  activeThreshold = parseFloat(b.dataset.thr);
  const h = document.getElementById('chart-title');
  if (h) h.textContent = `F1@${activeThreshold}cm by capture approach`;
  updateTable(); updateChart(); refreshRowNotes();
}));

// ---------- statistical-significance section (static, at default DBSCAN params) ----------
function renderStats() {
  const os = DATA.object_sensitivity.map(o => {
    const t = DATA.objects.find(x => x.id === o.object).title;
    return `<b>${t}</b>: spread ${o.mean_spread.toFixed(1)} pts (${o.any_resolvable ? 'resolvable' : 'within noise'})`;
  }).join('&nbsp;&middot;&nbsp;');
  const cav = document.getElementById('stats-caveats');
  if (cav) cav.innerHTML = `${os}. n=2 objects — illustrative, not a population test.`;
  renderDiffHists();
}

// ---------- pairwise-difference bootstrap histograms (4 panels: object x method) ----------
function renderDiffHists() {
  const grid = document.getElementById('diff-hist-grid');
  if (!grid) return;
  grid.innerHTML = '';
  const tick = cssvar('--text-faint'), axis = cssvar('--text-dim');
  const PAIR_COLORS = ['#4c8dff', '#c86bd6', '#38b58a'];
  for (const sv of DATA.sensitivity) {
    const obj = DATA.objects.find(o => o.id === sv.object);
    const edges = sv.hist.edges, counts = sv.hist.counts, nb = edges.length - 1;
    const maxc = Math.max(1, ...counts.flat());
    const W = 340, H = 200, padL = 8, padR = 8, padT = 12, padB = 34;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const lo = edges[0], hi = edges[nb];
    const X = v => padL + (v - lo) / (hi - lo) * plotW;
    const YB = c => padT + plotH - (c / maxc) * plotH;
    let s = '';
    if (lo <= 0 && hi >= 0) {
      const x0 = X(0);
      s += `<line x1="${x0.toFixed(1)}" y1="${padT}" x2="${x0.toFixed(1)}" y2="${padT + plotH}" stroke="${axis}" stroke-width="1.4" stroke-dasharray="3,3"/>`;
      s += `<text x="${x0.toFixed(1)}" y="${padT - 3}" font-size="9" fill="${axis}" text-anchor="middle">0</text>`;
    }
    sv.pairwise.forEach((p, pi) => {
      const col = PAIR_COLORS[pi];
      for (let b = 0; b < nb; b++) {
        const c = counts[pi][b]; if (!c) continue;
        const x0 = X(edges[b]), x1 = X(edges[b + 1]);
        s += `<rect x="${x0.toFixed(1)}" y="${YB(c).toFixed(1)}" width="${Math.max(x1 - x0 - 0.4, 0.6).toFixed(1)}" height="${(padT + plotH - YB(c)).toFixed(1)}" fill="${col}" fill-opacity="0.5"/>`;
      }
    });
    for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4;
      s += `<text x="${X(v).toFixed(1)}" y="${H - 18}" font-size="9" fill="${tick}" text-anchor="middle">${v.toFixed(0)}</text>`; }
    s += `<text x="${W / 2}" y="${H - 5}" font-size="8.5" fill="${tick}" text-anchor="middle">&Delta; F1@3cm (%) &middot; ${DATA.bootstrap.n_draws} bootstrap draws</text>`;
    const legend = sv.pairwise.map((p, pi) => {
      const sig = !p.includes_zero;
      return `<span style="color:${PAIR_COLORS[pi]}; font-weight:${sig ? '700' : '400'}">&#9632;&nbsp;${p.label}${sig ? ' *' : ''}</span>`;
    }).join('&nbsp;&nbsp;');
    const lines = sv.pairwise.map(p => {
      const sig = !p.includes_zero;
      const c = sig ? 'var(--red)' : 'var(--text-faint)';
      return `<span style="color:${c}; font-weight:${sig ? '650' : '400'}">${p.label}: ${p.delta > 0 ? '+' : ''}${p.delta.toFixed(1)} [${p.ci_lo.toFixed(1)}, ${p.ci_hi.toFixed(1)}]</span>`;
    }).join('&nbsp;&middot;&nbsp;');
    const panel = document.createElement('div');
    panel.className = 'panel';
    panel.innerHTML = `<div style="display:flex; justify-content:space-between; align-items:baseline; gap:6px; flex-wrap:wrap;">`
      + `<span style="font-weight:650; font-size:12.5px;">${obj.title} &middot; ${DATA.method_label[sv.method]}</span>`
      + `<span style="font-size:10px;">${legend}</span></div>`
      + `<svg viewBox="0 0 ${W} ${H}" style="width:100%; height:auto;">${s}</svg>`
      + `<div style="font-size:10.5px; line-height:1.4;">${lines}<span style="color:var(--text-faint)">&nbsp; (* = 95% CI excludes 0)</span></div>`;
    grid.appendChild(panel);
  }
}

// ---------- init ----------
buildTable();
renderStats();
for (const obj of DATA.objects) recomputeObject(obj.id);
// re-render histograms on theme change
const mq = window.matchMedia('(prefers-color-scheme: dark)');
mq.addEventListener && mq.addEventListener('change', ()=>{ updateChart(); renderStats(); });
</script>
"""


HTML_TAIL = r"""
</body>
</html>
"""
