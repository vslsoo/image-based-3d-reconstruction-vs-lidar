"""HTML/CSS/JS template strings for build_frame_count_study_page.py.

Kept in a separate module so the builder (which does the heavy o3d numeric work) stays
readable. HTML_HEAD holds the head + CSS + empty mount points; MAIN_JS holds all the
interactive logic (coverage-curve charts with an x-axis toggle, WebGL viewers, a live
DBSCAN tuner, reactive summary table); HTML_TAIL closes the document. The whole page is
self-contained - no external libraries, theme-aware, raw WebGL.

Most of the low-level machinery (grid-accelerated DBSCAN, the mat4 helpers, makeViewer,
the population-weighted accuracy%) is lifted verbatim from
_capture_page_template.py / site/bus_stop_001.html so the numbers are produced
identically to the other pages.
"""

HTML_HEAD = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Frame-count sensitivity — information_sign_002 &amp; bollard_003 (gap-aware Accuracy/Completeness/F1 vs N)</title>
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
    --colmap:#c15c85; --mastr:#0d8054; --mastr2:#5d63c7;
    --n25:#bfdbfe; --n50:#7fb3f5; --n75:#3f7fe0; --n100:#1d4ed8;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084;
      --accent:#17805f; --accent-soft:#d9ece3; --green:#1aacb3; --red:#e16b3e; --code-bg:#f5f4ef; --best:#0d8054; --best-soft:#e3f1ea;
      --colmap:#c15c85; --mastr:#0d8054; --mastr2:#5d63c7;
      --n25:#bfdbfe; --n50:#7fb3f5; --n75:#3f7fe0; --n100:#1d4ed8; }
  }
  :root[data-theme="dark"] { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084;
    --accent:#17805f; --accent-soft:#d9ece3; --green:#1aacb3; --red:#e16b3e; --code-bg:#f5f4ef; --best:#0d8054; --best-soft:#e3f1ea;
    --colmap:#c15c85; --mastr:#0d8054; --mastr2:#5d63c7;
    --n25:#bfdbfe; --n50:#7fb3f5; --n75:#3f7fe0; --n100:#1d4ed8; }
  :root[data-theme="light"] { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084;
    --accent:#17805f; --accent-soft:#d9ece3; --green:#1aacb3; --red:#e16b3e; --code-bg:#f5f4ef; --best:#0d8054; --best-soft:#e3f1ea;
    --colmap:#c15c85; --mastr:#0d8054; --mastr2:#5d63c7;
    --n25:#bfdbfe; --n50:#7fb3f5; --n75:#3f7fe0; --n100:#1d4ed8; }

  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; line-height:1.45; }
  .page { max-width:1560px; margin:0 auto; padding:28px 24px 72px; display:flex; flex-direction:column; gap:26px; }
  a { color:var(--accent); }
  .eyebrow { font-size:11.5px; font-weight:600; letter-spacing:.09em; text-transform:uppercase; color:var(--accent); }
  h1 { font-size:23px; font-weight:650; margin:4px 0 2px; letter-spacing:-.01em; }
  h2 { font-size:19px; font-weight:650; margin:0 0 2px; }
  h3 { font-size:15px; font-weight:650; margin:0; }
  .subtitle { color:var(--text-dim); font-size:13.5px; max-width:88ch; }
  b, strong { color:var(--text); font-weight:600; }
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
  .obj-grid { display:grid; grid-template-columns:88px repeat(4, minmax(250px,1fr)); gap:12px; min-width:1180px; }
  .col-head { font-size:12.5px; font-weight:650; color:var(--text); padding:0 2px 2px; align-self:end; }
  .col-head .hint { display:block; font-weight:400; font-size:10px; color:var(--text-faint); margin-top:2px; }
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


  /* aside + significance grid - same treatment as capture_comparison.html, so the two
     study pages read as one family. */
  .with-aside { display:grid; grid-template-columns:minmax(0,1fr) 260px; gap:18px; align-items:start; }
  @media (max-width:1100px) { .with-aside { grid-template-columns:minmax(0,1fr); } }
  .aside { background:var(--code-bg); border:1px solid var(--panel-border); border-left:3px solid var(--text-faint);
           border-radius:10px; padding:12px 14px; font-size:12.5px; color:var(--text-dim); }
  .aside b { color:var(--text); }
  .aside .k { display:block; font-size:11px; font-weight:650; letter-spacing:.07em; text-transform:uppercase;
              color:var(--text-faint); margin-bottom:5px; }
  .sig-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(310px,1fr)); gap:12px; }
  .sig-grid svg { width:100%; height:auto; }
  .ci-cell { color:var(--text-faint); font-size:11px; }

  .xtoggle { display:flex; gap:5px; align-items:center; }
  .curve-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(300px,1fr)); gap:14px; }
  .curve-panel svg { width:100%; height:auto; }

  footer { color:var(--text-faint); font-size:11px; padding-top:4px; }
</style>

<div class="page">
  <div>
    <div class="eyebrow">Frame-count ablation · gap-aware Chamfer (Accuracy / Completeness / F1)</div>
    <h1>How many photos does the reconstruction need?</h1>
    <div class="subtitle lede" style="max-width:92ch">
      <p>
        Anyone photographing an object has to decide how many shots to take. This asks where the payoff
        stops — and whether it stops in the same place for every method.
      </p>
      <p>
        <b>Two objects, opposite extremes</b> on both axes the project varies, the same pair as the
        capture-strategy study: the small, compact, semi-gloss bollard and the taller, flat-faced
        information sign under a mirroring cover. <b>Two families, one method each</b> — COLMAP matching
        features between views, MASt3R-GA regressing geometry from a learned prior.
      </p>
      <p>
        <b>Each larger set contains the smaller ones</b>, so a difference between them comes from the
        images added rather than from a new draw. That is the whole point of nesting: frame count is the
        only thing that changes.
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
    <div style="display:flex; align-items:baseline; flex-wrap:wrap; gap:14px;">
      <h2 id="curves-title">Accuracy, Completeness &amp; F1@3cm vs. number of photos</h2>
      <div class="tabs" id="thr-toggle">
        <button class="tab-btn active" data-thr="3">3 cm</button>
        <button class="tab-btn" data-thr="5">5 cm</button>
        <button class="tab-btn" data-thr="10">10 cm</button>
      </div>
    </div>
    <div class="xtoggle" id="obj-toggle"><span class="mono" style="font-size:11px; color:var(--text-faint);">object:</span></div>
    <div class="subtitle" id="curves-subtitle"></div>
    <div class="curve-grid" id="curve-grid"></div>
  </section>

  <hr class="sep">
  <section id="objects-root"></section>

  <hr class="sep">
  <section>
    <h2>Summary — object &times; N &times; method</h2>
    <div class="subtitle" style="max-width:92ch">
      Best F1 per group highlighted. The <b>95%&nbsp;CI</b> column is a spatial block bootstrap on F1
      (2000&nbsp;draws, 5&nbsp;cm blocks), precomputed at 3&nbsp;cm with each object's default gap-detection
      settings — it blanks out as soon as the threshold tabs or the tuner move off those.
    </div>
    <div class="grid-wrap"><div id="summary-table-wrap"></div></div>
    <div id="table-mode-note" style="font-size:11.5px; color:var(--text-faint);"></div>
  </section>

  <hr class="sep">
  <section>
    <div style="display:flex; align-items:baseline; gap:14px; flex-wrap:wrap;">
      <h2>Does adding photos actually change anything?</h2>
      <div class="tabs" id="sig-metric-toggle">
        <button class="tab-btn active" data-metric="F1">F1</button>
        <button class="tab-btn" data-metric="accuracy">Accuracy</button>
      </div>
    </div>
    <div class="subtitle" style="max-width:92ch">
      A curve that rises by a couple of points could just be luck of which surface patches happened to be
      covered. To tell, every pair of frame counts is re-scored 2000 times on resampled 5&nbsp;cm patches of the
      object, and the <i>paired</i> difference is taken — the same resampled patches feed both sides, so what is
      left is the effect of the added photos. <b>If the interval sits entirely to one side of 0</b>, the two frame
      counts genuinely differ. <b>If it straddles 0</b>, the extra photos bought nothing measurable. Computed at
      3&nbsp;cm, at default gap-detection settings.
    </div>
    <div class="with-aside">
      <div>
        <div id="sig-grid" class="sig-grid"></div>
        <div style="font-size:10.5px; color:var(--text-faint); text-align:center; margin-top:8px;">
          <span class="swatch" style="background:var(--best)"></span>more photos helped&nbsp;&nbsp;
          <span class="swatch" style="background:var(--red)"></span>more photos hurt&nbsp;&nbsp;
          <span class="swatch" style="background:var(--text-faint)"></span>within noise (95% CI spans 0)
          &nbsp;&middot;&nbsp; * = 95% CI excludes 0
        </div>
      </div>
      <div class="aside">
        <span class="k">The answer</span>
        <div id="sig-aside"></div>
      </div>
    </div>
  </section>


  <footer>information_sign_002: exp_109–114, exp_123–128 (COLMAP + MASt3R-GA swin-8 + MASt3R-GA logwin-7) · bollard_003: exp_115–122 (COLMAP + MASt3R-GA swin-8) · manual frame selection · src/registration/build_frame_count_study_page.py</footer>
</div>
"""


MAIN_JS = r"""<script>
const DATA = JSON.parse(document.getElementById('page-data').textContent);
const FLOOR_CM = DATA.floor_cm;
const RENDER_CAP = 8000;
const HEAT_VMAX = 15.0; // cm mapped to the top of the turbo scale
// Each object has its own `sizes` list (a small bollard and a big sign need very
// different N, so there's no one shared global SIZES) - panels/table/curves all index by
// an object's OWN obj.sizes, and colour by RANK within that list (0=smallest..3=largest),
// via each panel's precomputed `size_index`, not by the literal N value.

// ---------- grid-accelerated DBSCAN (Ester et al. 1996) ----------
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

// ---------- mat4 + WebGL viewer (Z-up, Open3D convention) ----------
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
  panelState[key].keptMask = new Uint8Array(panelState[key].candidateDist.length).fill(1);
}
const objTargetPos = {};
for (const o of DATA.objects) objTargetPos[o.id] = b64ToFloat32(o.target_pos);

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

// What the reader is shown. The browser only holds a capped subsample of each cloud
// (EMBED_CAP points per pool), and re-running DBSCAN on a thinned cloud finds fewer
// clusters, so the live gap mask UNDER-excludes and the live Accuracy reads low - on the
// sign's MASt3R panels, where 40k+ points sit in unscanned gaps, by up to 19 points.
// So: whenever the configuration is one Python actually scored on the full cloud
// (default gap settings, 3/5/10 cm), show Python's exact numbers - the ones in
// FINAL_results.xlsx, and the ones the bootstrap CIs belong to. The live estimate is for
// exploring with the tuner, where no exact answer exists; `exact:false` says which is on
// screen so the page can label it.
function atDefaults(objId) {
  const t = objTuner[objId], dcfg = DATA.objects.find(o => o.id === objId).dbscan;
  return !!t && t.applyDbscan && t.ft === dcfg.ft && t.eps === dcfg.eps && t.mp === dcfg.mp;
}
function shownMetrics(key, t) {
  const d = panelState[key].d;
  if (!atDefaults(d.object) || ![3, 5, 10].includes(t)) return { ...panelMetrics(key, t), exact: false };
  const e = d.default, k = `${t}cm`;
  return { accPct: e[`acc_${k}`], compPct: e[`comp_${k}`], f1: e[`f1_${k}`],
           nExcluded: e.n_excluded, rmse: t === 3 ? e.inlier_rmse_3cm : inlierRmse(key, t), exact: true };
}

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


// ---------- build the 3D grid ----------
const objRoot = document.getElementById('objects-root');
const panelApi = {};
const objTuner = {};

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


  const grid = block.querySelector(`#grid-${obj.id}`);
  grid.appendChild(document.createElement('div')); // corner
  obj.sizes.forEach((sz, idx) => {
    const h=document.createElement('div'); h.className='col-head';
    h.innerHTML = `N=${sz}`;
    grid.appendChild(h);
  });
  for (const method of methods) {
    const rh=document.createElement('div'); rh.className='row-head'; rh.textContent=DATA.method_label[method]; grid.appendChild(rh);
    for (const sz of obj.sizes) {
      const key = `${obj.id}__${method}__${sz}`;
      grid.appendChild(buildPanel(key));
    }
  }

  // Gap-detection settings are fixed per object (the values tuned in tuner.html), not
  // sliders: this page compares frame counts, so the gap handling has to stay constant.
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
    const m=shownMetrics(key,t);
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
  updateTable(); updateCurves();
}

// Metric threshold for the curves and the summary table. panelMetrics(key, t) takes any t,
// so switching recomputes both in the browser. The bootstrap CIs are precomputed at 3cm.
let activeThreshold = 3.0;

// The bootstrap CIs (and the pairwise test further down) were computed in Python at 3cm
// with each object's DEFAULT gap-detection settings. Move the tuner or the threshold tabs
// and the live number no longer belongs to that interval, so the CI is withheld rather
// than shown next to a value it was not computed for.
function ciValid(objId) { return activeThreshold === 3.0 && atDefaults(objId); }

// ---------- summary table ----------
function fmtReg(r){ return r==null ? '—' : (r*100).toFixed(1)+'%'; }
function buildTable() {
  const wrap=document.getElementById('summary-table-wrap');
  let h='<table class="summary"><thead><tr>'
    + '<th class="txt">Object</th><th class="txt">N</th><th class="txt">Method</th>'
    + '<th id="th-f1">F1@3cm</th><th>95% CI</th><th id="th-acc">Acc@3cm</th><th id="th-comp">Comp@3cm</th><th>Acc median</th><th>Comp median</th>'
    + '<th>reg-rate</th><th>#pts (raw→matched)</th><th>inlier RMSE@3cm</th><th>excl≈</th></tr></thead><tbody>';
  for (const obj of DATA.objects) {
    const methods=[...new Set(obj.panels.map(k=>panelState[k].d.method))];
    for (const method of methods) {
      for (const sz of obj.sizes) {
        const key=`${obj.id}__${method}__${sz}`; const d=panelState[key].d;
        h+=`<tr id="row-${key}" ${sz===obj.sizes[0]?'class="grouprule"':''}>`
          + `<td class="txt">${sz===obj.sizes[0]&&method===methods[0]?obj.title:''}</td>`
          + `<td class="txt">${sz}</td><td class="txt">${DATA.method_label[method]}</td>`
          + `<td class="f1cell" data-col="f1">–</td><td class="mono ci-cell" data-col="ci">–</td>`
          + `<td data-col="acc">–</td><td data-col="comp">–</td>`
          + `<td>${d.accuracy_median_cm.toFixed(2)}</td><td>${d.completeness_median_cm.toFixed(2)}</td>`
          + `<td>${fmtReg(d.reg_rate)}</td><td class="mono">${d.raw_points.toLocaleString('en-US')}→${d.matched_points.toLocaleString('en-US')}</td>`
          + `<td data-col="rmse">–</td><td data-col="excl">–</td></tr>`;
      }
    }
  }
  h+='</tbody></table>';
  wrap.innerHTML=h;
}
function updateTable() {
  // Say which numbers are on screen. Silently swapping exact for estimated would be worse
  // than either: the two differ by up to 19 points on the sign's MASt3R panels.
  const note = document.getElementById('table-mode-note');
  if (note) {
    const anyEstimate = DATA.objects.some(o => !atDefaults(o.id)) || ![3, 5, 10].includes(activeThreshold);
    note.innerHTML = anyEstimate
      ? `Some rows are the browser's <b>live estimate</b> from the embedded point subsample — the tuner is off `
        + `its defaults. A thinned cloud gives DBSCAN fewer clusters to find, so the gap mask under-excludes and `
        + `Accuracy reads low; return the tuner to its defaults for the exact figures.`
      : `Exact figures, computed on the full clouds — the same numbers as `
        + `<span class="mono">docs/tables/frame_count_study_summary.xlsx</span>. Move the tuner and the table `
        + `switches to the browser's live estimate from the embedded subsample.`;
  }
  // headers follow the threshold tabs - the columns did, but the labels used to stay at 3cm
  for (const [id, name] of [['th-f1','F1'], ['th-acc','Acc'], ['th-comp','Comp']]) {
    const th = document.getElementById(id);
    if (th) th.textContent = `${name}@${activeThreshold}cm`;
  }
  for (const obj of DATA.objects) {
    const methods=[...new Set(obj.panels.map(k=>panelState[k].d.method))];
    for (const method of methods) {
      let bestF1=-1, bestKey=null;
      const rows=[];
      for (const sz of obj.sizes) {
        const key=`${obj.id}__${method}__${sz}`; const m=shownMetrics(key,activeThreshold);
        rows.push({key,m}); if(m.f1>bestF1){ bestF1=m.f1; bestKey=key; }
      }
      for (const {key,m} of rows) {
        const tr=document.getElementById(`row-${key}`); if(!tr) continue;
        tr.querySelector('[data-col=f1]').textContent=m.f1.toFixed(1);
        const ciTd=tr.querySelector('[data-col=ci]'), dd=panelState[key].d;
        if (ciValid(obj.id)) {
          ciTd.textContent=`[${dd.default.f1_ci_lo.toFixed(1)}, ${dd.default.f1_ci_hi.toFixed(1)}]`;
          ciTd.title=`95% spatial block bootstrap CI on F1@3cm · ${DATA.bootstrap.n_draws} draws, ${DATA.bootstrap.block_cm} cm blocks`;
        } else {
          ciTd.textContent='—';
          ciTd.title='CI is precomputed at 3 cm with the default gap-detection settings; switch back to see it.';
        }
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

// ---------- basic curves: F1 / Accuracy / Completeness vs number of photos ----------
let curveObjId = DATA.objects.length ? DATA.objects[0].id : null; // which object's 3 panels are shown

function cssvar(v){ return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }

// colour per method for the curve charts - keyed by method id, with a fallback for any
// future method not in this list (falls back to the accent colour rather than crashing).
const METHOD_COLORVAR = { colmap: '--colmap', mast3r_ga: '--mastr', mast3r_ga_logwin7: '--mastr2' };
function methodColor(method) { return cssvar(METHOD_COLORVAR[method] || '--accent'); }

// one small-multiple line chart: `metricFn(key)` -> live {value, ciLo, ciHi} at threshold 3cm
function renderCurvePanel(container, obj, methods, title, metricKey) {
  const W = 460, H = 300, padL = 40, padR = 14, padT = 16, padB = 40;
  const plotW = W - padL - padR, plotH = H - padT - padB;

  // gather live points
  const series = methods.map(method => {
    const pts = obj.sizes.map(sz => {
      const key = `${obj.id}__${method}__${sz}`;
      const d = panelState[key].d;
      const m = shownMetrics(key, activeThreshold);
      const val = metricKey === 'f1' ? m.f1 : (metricKey === 'acc' ? m.accPct : m.compPct);
      return { x: sz, y: val, size: sz, n: d.raw_points, matched: d.matched_points,
               ciLo: d.default[`${metricKey}_ci_lo`], ciHi: d.default[`${metricKey}_ci_hi`] };
    }).filter(p => p.x != null && !isNaN(p.x));
    return { method, label: DATA.method_label[method], color: methodColor(method), pts };
  });

  // raw N: each object is plotted on its own axis, so absolute counts are readable
  const xMin = 0, xMax = Math.max(...obj.sizes) * 1.06;
  const X = v => padL + (v - xMin) / (xMax - xMin) * plotW;
  const Y = v => padT + plotH - (v / 100) * plotH;

  let s = '';
  for (let y = 0; y <= 100; y += 20) {
    const yy = Y(y);
    s += `<line x1="${padL}" y1="${yy}" x2="${W-padR}" y2="${yy}" stroke="${cssvar('--text-faint')}" stroke-opacity="0.22"/>`;
    s += `<text x="${padL-6}" y="${yy+3}" font-size="9.5" fill="${cssvar('--text-faint')}" text-anchor="end">${y}</text>`;
  }
  const xt = cssvar('--text-dim');
  obj.sizes.forEach(v => {
    s += `<text x="${X(v)}" y="${H-padB+14}" font-size="9.5" fill="${xt}" text-anchor="middle">${v}</text>`;
  });
  s += `<text x="${W/2}" y="${H-6}" font-size="10" fill="${xt}" text-anchor="middle">number of photos (N)</text>`;
  s += `<text x="12" y="${padT+plotH/2}" font-size="10" fill="${xt}" transform="rotate(-90 12 ${padT+plotH/2})" text-anchor="middle">${title} (%)</text>`;

  for (const sr of series) {
    if (sr.pts.length === 0) continue;
    const sorted = sr.pts.slice().sort((a,b)=>a.x-b.x);
    const path = sorted.map((p,i) => `${i===0?'M':'L'}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join(' ');
    s += `<path d="${path}" fill="none" stroke="${sr.color}" stroke-width="2.2"/>`;
  }

  // 95% block-bootstrap whiskers. Only drawn where the interval actually belongs to the
  // value plotted (3cm, default gap settings) - see ciValid(); otherwise the points stand
  // alone rather than carrying an interval computed for a different configuration.
  const showCI = ciValid(obj.id);
  if (showCI) {
    for (const sr of series) {
      for (const p of sr.pts) {
        if (p.ciLo == null || isNaN(p.ciLo)) continue;
        const px = X(p.x), yLo = Y(p.ciLo), yHi = Y(p.ciHi);
        s += `<line x1="${px.toFixed(1)}" y1="${yLo.toFixed(1)}" x2="${px.toFixed(1)}" y2="${yHi.toFixed(1)}" stroke="${sr.color}" stroke-width="1.6" stroke-opacity="0.55"/>`;
        for (const yy of [yLo, yHi]) {
          s += `<line x1="${(px-3.5).toFixed(1)}" y1="${yy.toFixed(1)}" x2="${(px+3.5).toFixed(1)}" y2="${yy.toFixed(1)}" stroke="${sr.color}" stroke-width="1.6" stroke-opacity="0.55"/>`;
        }
      }
    }
  }

  // circles + N-labels: computed across BOTH series together so labels that would land
  // on top of each other get nudged apart instead of overlapping into an unreadable smear.
  const allPts = [];
  for (const sr of series) for (const p of sr.pts) allPts.push({ ...p, color: sr.color, label: sr.label, px: X(p.x), py: Y(p.y) });
  allPts.sort((a, b) => a.px - b.px);
  const placedLabelY = [];
  for (const p of allPts) {
    let dy = -8, tries = 0;
    while (tries < 8 && placedLabelY.some(q => Math.abs(q.px - p.px) < 22 && Math.abs((p.py + dy) - q.ly) < 9)) {
      dy -= 10; tries++;
    }
    p.dy = dy;
    placedLabelY.push({ px: p.px, ly: p.py + dy });
  }
  for (const p of allPts) {
    const ciTxt = showCI && p.ciLo != null && !isNaN(p.ciLo) ? ` [95% CI ${p.ciLo.toFixed(1)}, ${p.ciHi.toFixed(1)}]` : '';
    s += `<circle cx="${p.px.toFixed(1)}" cy="${p.py.toFixed(1)}" r="4" fill="${p.color}"><title>${p.label} · N=${p.size} (${p.n.toLocaleString('en-US')}→${p.matched.toLocaleString('en-US')} pts): ${title}=${p.y.toFixed(1)}%${ciTxt}</title></circle>`;
    s += `<text x="${p.px.toFixed(1)}" y="${(p.py + p.dy).toFixed(1)}" font-size="9" fill="${p.color}" text-anchor="middle">N${p.size}</text>`;
  }

  const panel = document.createElement('div');
  panel.className = 'panel curve-panel';
  const legend = series.map(sr => `<span style="color:${sr.color}; font-weight:650;">&#9679;&nbsp;${sr.label}</span>`).join('&nbsp;&nbsp;');
  panel.innerHTML = `<div style="display:flex; justify-content:space-between; align-items:baseline; gap:8px; flex-wrap:wrap;">`
    + `<h3>${title} vs. N</h3><span style="font-size:10.5px;">${legend}</span></div>`
    + `<svg viewBox="0 0 ${W} ${H}">${s}</svg>`;
  container.appendChild(panel);
}

function updateCurves() {
  const grid = document.getElementById('curve-grid');
  grid.innerHTML = '';
  const obj = DATA.objects.find(o => o.id === curveObjId);
  if (!obj) return;
  const methods = [...new Set(obj.panels.map(k => panelState[k].d.method))];
  renderCurvePanel(grid, obj, methods, 'F1@3cm', 'f1');
  renderCurvePanel(grid, obj, methods, 'Accuracy@3cm', 'acc');
  renderCurvePanel(grid, obj, methods, 'Completeness@3cm', 'comp');
  const ciNote = ciValid(obj.id)
    ? `Whiskers are 95% spatial block-bootstrap intervals (${DATA.bootstrap.n_draws} draws, ${DATA.bootstrap.block_cm} cm blocks).`
    : atDefaults(obj.id)
      ? `Whiskers are hidden: the bootstrap CIs were computed at 3&nbsp;cm only.`
      : `Whiskers are hidden and the points are the browser's live estimate — the tuner is off this object's `
        + `default gap settings, which is what the CIs were computed at.`;
  document.getElementById('curves-subtitle').innerHTML =
    `<b>${obj.title}</b> — Accuracy and Completeness are shown separately from F1 because they tend to saturate `
    + `differently: completeness keeps climbing as new viewpoints close coverage gaps, while accuracy can plateau `
    + `early or even dip as MVS/GA fuses more hard-to-triangulate points. Live with the DBSCAN tuner below. `
    + ciNote;
}

// ---------- "does adding photos change anything?" (static, at default DBSCAN params) ----------
// Paired block-bootstrap differences between every two frame counts, computed once in
// Python (build_frame_count_study_page.py) at 3cm and shipped in DATA.n_significance.
// Deliberately NOT live with the tuner: the draws are not in the browser, so the panels
// stay at the default gap settings the intervals were computed for - same discipline as
// the significance section of capture_comparison.html.
let sigMetric = 'F1';

function sigRows(objId, method) {
  return DATA.n_significance.filter(r => r.object === objId && r.method === method && r.metric === sigMetric);
}
function sigColor(r) {
  if (r.includes_zero) return cssvar('--text-faint');
  return r.delta > 0 ? cssvar('--best') : cssvar('--red');
}

// One panel per (object, method): a row per pair of frame counts, dot at the difference,
// bar across its 95% CI, dashed line at 0.
function renderSigPanel(objId, method) {
  const obj = DATA.objects.find(o => o.id === objId);
  const rows = sigRows(objId, method);
  if (!rows.length) return null;

  const W = 452, padL = 86, padR = 108, padT = 20, padB = 30, rowH = 21;
  const H = padT + rows.length * rowH + padB;
  const plotW = W - padL - padR;
  const lo = Math.min(0, ...rows.map(r => r.ci_lo)), hi = Math.max(0, ...rows.map(r => r.ci_hi));
  const pad = Math.max((hi - lo) * 0.06, 0.4);
  const dLo = lo - pad, dHi = hi + pad;
  const X = v => padL + (v - dLo) / (dHi - dLo) * plotW;
  const tick = cssvar('--text-faint'), dim = cssvar('--text-dim');

  let s = '';
  const x0 = X(0);
  s += `<line x1="${x0.toFixed(1)}" y1="${padT - 6}" x2="${x0.toFixed(1)}" y2="${padT + rows.length * rowH}" stroke="${dim}" stroke-width="1.3" stroke-dasharray="3,3"/>`;
  s += `<text x="${x0.toFixed(1)}" y="${padT - 9}" font-size="9" fill="${dim}" text-anchor="middle">0</text>`;

  rows.forEach((r, i) => {
    const y = padT + i * rowH + rowH / 2;
    const col = sigColor(r), sig = !r.includes_zero;
    const xa = X(r.ci_lo), xb = X(r.ci_hi);
    s += `<line x1="${xa.toFixed(1)}" y1="${y}" x2="${xb.toFixed(1)}" y2="${y}" stroke="${col}" stroke-width="${sig ? 2 : 1.5}" stroke-opacity="${sig ? 0.85 : 0.5}"/>`;
    for (const xx of [xa, xb]) {
      s += `<line x1="${xx.toFixed(1)}" y1="${y - 4}" x2="${xx.toFixed(1)}" y2="${y + 4}" stroke="${col}" stroke-width="${sig ? 1.8 : 1.3}" stroke-opacity="${sig ? 0.85 : 0.5}"/>`;
    }
    s += `<circle cx="${X(r.delta).toFixed(1)}" cy="${y}" r="3.4" fill="${col}" fill-opacity="${sig ? 1 : 0.6}">`
      + `<title>${r.pair}: ${r.delta > 0 ? '+' : ''}${r.delta.toFixed(2)} pp, 95% CI [${r.ci_lo.toFixed(2)}, ${r.ci_hi.toFixed(2)}]</title></circle>`;
    // pair on the left, the numbers it stands for on the right
    s += `<text x="${padL - 8}" y="${y + 3.2}" font-size="9.5" fill="${dim}" text-anchor="end">${r.pair.replace(/ - /, ' − ')}</text>`;
    s += `<text x="${padL + plotW + 8}" y="${y + 3.2}" font-size="9.5" fill="${sig ? cssvar('--text') : tick}"`
      + ` font-weight="${sig ? 650 : 400}">${r.delta > 0 ? '+' : ''}${r.delta.toFixed(1)} [${r.ci_lo.toFixed(1)}, ${r.ci_hi.toFixed(1)}]${sig ? ' *' : ''}</text>`;
  });

  const yAxis = padT + rows.length * rowH + 12;
  s += `<line x1="${padL}" y1="${yAxis - 6}" x2="${padL + plotW}" y2="${yAxis - 6}" stroke="${tick}" stroke-opacity="0.3"/>`;
  const dec = (dHi - dLo) >= 20 ? 0 : 1;   // one rule per panel, so the tick row doesn't mix 1.8 with 11
  for (let k = 0; k <= 4; k++) {
    const v = dLo + (dHi - dLo) * k / 4;
    s += `<text x="${X(v).toFixed(1)}" y="${yAxis + 4}" font-size="9" fill="${tick}" text-anchor="middle">${v.toFixed(dec)}</text>`;
  }
  s += `<text x="${(padL + plotW / 2).toFixed(1)}" y="${H - 3}" font-size="8.5" fill="${tick}" text-anchor="middle">`
    + `&Delta; ${sigMetric === 'F1' ? 'F1' : 'Accuracy'}@3cm (pp) &middot; ${DATA.bootstrap.n_draws} paired bootstrap draws</text>`;

  const panel = document.createElement('div');
  panel.className = 'panel';
  panel.innerHTML = `<div style="font-weight:650; font-size:12.5px;">${obj.title.replace(/ \(.*\)$/, '')} &middot; ${DATA.method_label[method]}</div>`
    + `<svg viewBox="0 0 ${W} ${H}">${s}</svg>`;
  return panel;
}

// Where does the payoff stop? The smallest N past which no further increase is resolvable.
// Returns null when even the last step still moves the metric.
function plateauN(objId, method) {
  const obj = DATA.objects.find(o => o.id === objId);
  const rows = sigRows(objId, method);
  for (const n of obj.sizes.slice(0, -1)) {
    if (rows.filter(r => r.n_lo >= n).every(r => r.includes_zero)) return n;
  }
  return null;
}

function buildSigNarrative() {
  const metricTxt = sigMetric === 'F1' ? 'F1@3cm' : 'Accuracy@3cm';
  let h = `<div style="color:var(--text-faint); font-size:11px; margin-bottom:7px;">metric: ${metricTxt}</div>`;
  for (const obj of DATA.objects) {
    const methods = [...new Set(obj.panels.map(k => panelState[k].d.method))];
    const parts = methods.map(method => {
      const label = DATA.method_label[method];
      const rows = sigRows(obj.id, method);
      const plateau = plateauN(obj.id, method);
      const drops = rows.filter(r => !r.includes_zero && r.delta < 0);
      const first = rows.find(r => r.n_lo === obj.sizes[0] && r.n_hi === obj.sizes[1]);
      if (plateau === obj.sizes[0]) {
        return `<b>${label}</b> is flat from the start — nothing above N=${obj.sizes[0]} is resolvable`;
      } else if (plateau) {
        const gain = rows.filter(r => r.n_lo < plateau && r.n_hi <= plateau && !r.includes_zero)
                         .reduce((mx, r) => Math.max(mx, r.delta), 0);
        return `<b>${label}</b> gains up to N=${plateau} (${gain > 0 ? '+' : ''}${gain.toFixed(0)}&nbsp;pts at most), then stops`;
      } else if (drops.length) {
        const d = drops[drops.length - 1];
        return `<b>${label}</b> never settles — the last step is a resolvable <i>drop</i> `
             + `(${d.pair.replace(/ - /, ' − ')}: ${d.delta.toFixed(1)}&nbsp;pts)`;
      }
      return `<b>${label}</b> is still improving at N=${obj.sizes[obj.sizes.length - 1]}`
           + (first && !first.includes_zero ? ` (${first.delta > 0 ? '+' : ''}${first.delta.toFixed(0)}&nbsp;pts on the first step alone)` : '');
    });
    h += `<div style="margin-bottom:9px;"><b>${obj.title.replace(/ \(.*\)$/, '')}</b> — ${parts.join('; ')}.</div>`;
  }
  return h;
}

function renderSig() {
  const grid = document.getElementById('sig-grid');
  if (!grid) return;
  grid.innerHTML = '';
  for (const obj of DATA.objects) {
    const methods = [...new Set(obj.panels.map(k => panelState[k].d.method))];
    for (const method of methods) {
      const panel = renderSigPanel(obj.id, method);
      if (panel) grid.appendChild(panel);
    }
  }
  const aside = document.getElementById('sig-aside');
  if (aside) aside.innerHTML = buildSigNarrative();
}

document.querySelectorAll('#sig-metric-toggle .tab-btn').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('#sig-metric-toggle .tab-btn').forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  sigMetric = b.dataset.metric;
  renderSig();
}));

// ---------- interpretation (auto from the live numbers) ----------

// ---------- x-axis toggle wiring ----------
document.querySelectorAll('#xaxis-toggle .tab-btn').forEach(b => {
  b.addEventListener('click', () => {
    document.querySelectorAll('#xaxis-toggle .tab-btn').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    xMode = b.dataset.xmode;
    updateCurves();
  });
});

// ---------- object toggle wiring (section A shows one object's 3 panels at a time) ----------
const objToggle = document.getElementById('obj-toggle');
for (const obj of DATA.objects) {
  const b = document.createElement('button');
  b.className = 'tab-btn' + (obj.id === curveObjId ? ' active' : '');
  b.textContent = obj.title;
  b.dataset.objid = obj.id;
  b.addEventListener('click', () => {
    objToggle.querySelectorAll('.tab-btn').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    curveObjId = obj.id;
    updateCurves();
  });
  objToggle.appendChild(b);
}

// threshold toggle: recompute curves + table in place
document.querySelectorAll('#thr-toggle .tab-btn').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('#thr-toggle .tab-btn').forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  activeThreshold = parseFloat(b.dataset.thr);
  const h = document.getElementById('curves-title');
  if (h) h.textContent = `Accuracy, Completeness & F1@${activeThreshold}cm vs. number of photos`;
  updateTable(); updateCurves();
}));

// ---------- init ----------
buildTable();
renderSig();
for (const obj of DATA.objects) recomputeObject(obj.id);
const mq = window.matchMedia('(prefers-color-scheme: dark)');
mq.addEventListener && mq.addEventListener('change', ()=>{ updateCurves(); renderSig(); });
</script>
"""


HTML_TAIL = r"""
</body>
</html>
"""
