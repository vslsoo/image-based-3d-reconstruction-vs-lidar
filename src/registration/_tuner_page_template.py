"""Shared HTML/CSS/JS shell for site/tuner.html, extracted verbatim so the exploratory
per-object/per-method DBSCAN tuner (single WebGL viewer, object+method tab selectors, live
gap-cluster recompute) is not re-implemented per rebuild. See build_tuner_page.py for how the
DATA blob (one entry per capture) is computed and slotted in.

TUNER_HEAD - everything up to (and including) the blank line right before the tuner-data
  script tag: doctype/head/CSS/page shell (Object/Method tab containers, canvas, controls,
  legend, stats bar). No per-object bits in here - object/method tabs are built by JS from
  DATA's keys.
TUNER_TAIL - from the opening <script> (JS body) to EOF: WebGL viewer, JS-side DBSCAN,
  object/method tab wiring, slider handling. Fully data-driven off DATA - reused byte-for-byte.
"""

TUNER_HEAD = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DBSCAN gap-cluster tuner — all objects</title>
</head>
<body>

<style>
  :root {
    /* forced light palette — matches the thesis-defense deck (white bg, forest-green accent) */
    --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084;
    --accent:#17805f; --accent-soft:#d9ece3; --ref-magenta:#2b2b28; --canvas-bg:#ffffff; --code-bg:#f5f4ef;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084; --accent:#17805f; --accent-soft:#d9ece3; --ref-magenta:#2b2b28; --code-bg:#f5f4ef; }
  }
  :root[data-theme="dark"] { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084; --accent:#17805f; --accent-soft:#d9ece3; --ref-magenta:#2b2b28; --code-bg:#f5f4ef; }
  :root[data-theme="light"] { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084; --accent:#17805f; --accent-soft:#d9ece3; --ref-magenta:#2b2b28; --code-bg:#f5f4ef; }

  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; line-height:1.45; }
  .page { max-width:980px; margin:0 auto; padding:28px 24px 72px; display:flex; flex-direction:column; gap:18px; }
  .eyebrow { font-size:11.5px; font-weight:600; letter-spacing:.09em; text-transform:uppercase; color:var(--accent); }
  h1 { font-size:22px; font-weight:650; margin:4px 0 2px; letter-spacing:-.01em; }
  .subtitle { color:var(--text-dim); font-size:13.5px; max-width:80ch; }
  .mono { font-family:ui-monospace,"SF Mono","Cascadia Code",Menlo,Consolas,monospace; font-variant-numeric:tabular-nums; }

  .method-tabs { display:flex; gap:6px; flex-wrap:wrap; }
  .method-btn { font-family:inherit; font-size:12.5px; padding:6px 14px; border-radius:8px; border:1px solid var(--panel-border); background:var(--panel); color:var(--text-dim); cursor:pointer; }
  .method-btn:hover { border-color:var(--accent); color:var(--text); }
  .method-btn.active { background:var(--accent-soft); border-color:var(--accent); color:var(--text); font-weight:650; }

  .panel { background:var(--panel); border:1px solid var(--panel-border); border-radius:12px; padding:14px; display:flex; flex-direction:column; gap:12px; box-shadow:0 1px 2px rgba(24,26,23,0.05), 0 1px 8px rgba(24,26,23,0.03); }
  canvas { width:100%; height:440px; display:block; border-radius:9px; background:var(--canvas-bg); touch-action:none; cursor:grab; }
  canvas:active { cursor:grabbing; }

  .controls { display:grid; grid-template-columns:1fr 1fr 1fr; gap:16px; }
  .control { display:flex; flex-direction:column; gap:4px; }
  .control label { font-size:11.5px; color:var(--text-dim); display:flex; justify-content:space-between; }
  .control label .val { color:var(--accent); font-weight:700; font-family:ui-monospace,monospace; }
  .control input[type=range] { accent-color:var(--accent); }

  .legend { display:flex; gap:18px; flex-wrap:wrap; font-size:11.5px; color:var(--text-dim); }
  .swatch { width:10px; height:10px; border-radius:3px; display:inline-block; margin-right:6px; vertical-align:-1px; }

  .stats-bar { display:flex; flex-wrap:wrap; gap:18px 28px; font-size:12.5px; color:var(--text-dim); background:var(--code-bg); border:1px solid var(--panel-border); border-radius:9px; padding:10px 14px; }
  .stats-bar b { color:var(--text); }
  .stats-bar .n-clusters { color:var(--accent); font-weight:700; }

  .summary { font-size:12.5px; color:var(--text-faint); background:var(--code-bg); border:1px solid var(--panel-border); border-radius:9px; padding:10px 14px; }
  .summary b { color:var(--text-dim); }
  .approx-note { color:var(--accent); font-size:11px; }

  footer { color:var(--text-faint); font-size:11px; padding-top:4px; }
__NAV_CSS__
</style>

<div class="page">
  __SITE_NAV__
  <div>
    <div class="eyebrow">gap-cluster DBSCAN tuner · all objects</div>
    <h1>Live tuning of eps / min_points / far_threshold</h1>
    <div class="subtitle">
      Pick an object and method, move the sliders, drag to rotate, watch the clusters. The far_threshold/eps ranges
      adapt automatically to each object's distance scale when you switch. This is an approximate explorer; the final
      gap-excluded clouds are computed on the full data separately via
      <code class="mono">remove_reference_gap_points.py</code> (without approximation,
      see the note below about subsampling).
    </div>
  </div>

  <div style="font-size:11px; color:var(--text-faint); margin-bottom:-6px;">Object</div>
  <div class="method-tabs" id="object-tabs"></div>
  <div style="font-size:11px; color:var(--text-faint); margin-top:4px; margin-bottom:-6px;">Method</div>
  <div class="method-tabs" id="method-tabs">
    <button class="method-btn" id="refonly-toggle" style="order:1; margin-left:auto; border-color:var(--ref-magenta); color:var(--ref-magenta);">Reference only</button>
    <button class="method-btn" id="lidar-toggle" style="order:2; border-color:var(--ref-magenta); color:var(--ref-magenta);">LiDAR ref</button>
  </div>

  <div class="panel">
    <canvas id="canvas"></canvas>
    <div class="controls">
      <div class="control">
        <label>far_threshold (candidate cutoff) <span class="val" id="ft-val">10.0cm</span></label>
        <input type="range" id="ft-slider" min="1" max="20" step="0.5" value="10">
      </div>
      <div class="control">
        <label>eps (DBSCAN radius) <span class="val" id="eps-val">2.0cm</span></label>
        <input type="range" id="eps-slider" min="0.5" max="8" step="0.1" value="2">
      </div>
      <div class="control">
        <label>min_points <span class="val" id="mp-val">10</span></label>
        <input type="range" id="mp-slider" min="2" max="40" step="1" value="10">
      </div>
    </div>
    <div class="legend">
      <span><span class="swatch" style="background:#c9cdc2"></span>rest of the cloud (context, outside candidates)</span>
      <span><span class="swatch" style="background:#d4af00"></span>candidate but isolated — kept (penalised)</span>
      <span><span class="swatch" style="background:#e16b3e"></span>in a cluster — will be excluded</span>
      <span><span class="swatch" style="background:#2b2b28"></span>“LiDAR ref” button above — reference overlay</span>
      <span>“Reference only” — hides the reconstruction entirely, shows just the raw LiDAR scan</span>
    </div>
    <div class="stats-bar" id="stats-bar">Loading...</div>
    <div class="summary" id="summary-text"></div>
  </div>

  <footer>approximate tuning tool (JS DBSCAN on a subsample of candidates) · final numbers are computed on the full data via src/registration/remove_reference_gap_points.py</footer>
</div>

"""

TUNER_TAIL = """\
<script>
const DATA = JSON.parse(document.getElementById('tuner-data').textContent);

function b64ToFloat32(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Float32Array(bytes.buffer);
}

// ---- mat4 helpers (Z-up) ----
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
const VERT_SRC = `attribute vec3 aPosition; attribute vec3 aColor; uniform mat4 uMVP; uniform float uPointSize; varying vec3 vColor;
  void main() { gl_Position = uMVP * vec4(aPosition, 1.0); gl_PointSize = uPointSize; vColor = aColor; }`;
const FRAG_SRC = `precision mediump float; varying vec3 vColor;
  void main() { vec2 d = gl_PointCoord - vec2(0.5); if (dot(d,d) > 0.25) discard; gl_FragColor = vec4(vColor, 1.0); }`;
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
  function makeBuffer(data) { const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW); return b; }
  const state = layers.map(l => ({ posBuf: makeBuffer(l.pos), colorBuf: makeBuffer(l.color), n: l.pos.length / 3, on: l.defaultOn !== false, sizeMul: l.sizeMul || 1 }));

  let minX=Infinity,minY=Infinity,minZ=Infinity,maxX=-Infinity,maxY=-Infinity,maxZ=-Infinity;
  for (const l of layers) for (let i = 0; i < l.pos.length; i += 3) {
    const x=l.pos[i],y=l.pos[i+1],z=l.pos[i+2];
    if (x<minX)minX=x; if (x>maxX)maxX=x; if (y<minY)minY=y; if (y>maxY)maxY=y; if (z<minZ)minZ=z; if (z>maxZ)maxZ=z;
  }
  const center = [(minX+maxX)/2, (minY+maxY)/2, (minZ+maxZ)/2];
  const diag = Math.hypot(maxX-minX, maxY-minY, maxZ-minZ) || 1;
  let azimuth = 0.6, elevation = 0.35, distance = diag * 1.3;

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = canvas.clientWidth * dpr, h = canvas.clientHeight * dpr;
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  }
  function draw() {
    resize();
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.enable(gl.DEPTH_TEST);
    gl.clearColor(1, 1, 1, 1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    const eye = [
      center[0] + distance * Math.cos(elevation) * Math.cos(azimuth),
      center[1] + distance * Math.cos(elevation) * Math.sin(azimuth),
      center[2] + distance * Math.sin(elevation),
    ];
    const view = mat4LookAt(eye, center, [0, 0, 1]);
    const proj = mat4Perspective(Math.PI / 4, canvas.width / canvas.height, diag * 0.01, diag * 10);
    const mvp = mat4Multiply(proj, view);
    gl.useProgram(prog);
    gl.uniformMatrix4fv(uMVP, false, mvp);
    const baseSize = Math.max(2.2, Math.min(canvas.width, canvas.height) / 185);
    for (const s of state) {
      if (!s.on || s.n === 0) continue;
      gl.uniform1f(uPointSize, baseSize * s.sizeMul);
      gl.bindBuffer(gl.ARRAY_BUFFER, s.posBuf); gl.enableVertexAttribArray(aPosition); gl.vertexAttribPointer(aPosition, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, s.colorBuf); gl.enableVertexAttribArray(aColor); gl.vertexAttribPointer(aColor, 3, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.POINTS, 0, s.n);
    }
  }
  let dragging = false, lastX = 0, lastY = 0;
  canvas.addEventListener('pointerdown', e => { dragging = true; lastX = e.clientX; lastY = e.clientY; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener('pointerup', () => dragging = false);
  canvas.addEventListener('pointermove', e => {
    if (!dragging) return;
    azimuth += (e.clientX - lastX) * 0.008;
    elevation = Math.max(-1.5, Math.min(1.5, elevation - (e.clientY - lastY) * 0.008));
    lastX = e.clientX; lastY = e.clientY; draw();
  });
  canvas.addEventListener('wheel', e => { e.preventDefault(); distance = Math.max(diag*0.1, Math.min(diag*6, distance*(1+e.deltaY*0.001))); draw(); }, { passive: false });
  window.addEventListener('resize', draw);
  draw();
  return {
    draw,
    setLayer(idx, pos, color) {
      state[idx].n = pos.length / 3;
      gl.bindBuffer(gl.ARRAY_BUFFER, state[idx].posBuf); gl.bufferData(gl.ARRAY_BUFFER, pos, gl.DYNAMIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, state[idx].colorBuf); gl.bufferData(gl.ARRAY_BUFFER, color, gl.DYNAMIC_DRAW);
      draw();
    },
    setLayerOn(idx, on) { state[idx].on = on; draw(); },
  };
}

function solidColor(n, rgb) {
  const out = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) { out[i*3]=rgb[0]; out[i*3+1]=rgb[1]; out[i*3+2]=rgb[2]; }
  return out;
}

const CONTEXT_COLOR = [0.788, 0.804, 0.761];  // #c9cdc2 - light, receded (reads as translucent against the white canvas)
const ISOLATED_COLOR = [0.831, 0.686, 0.000];  // #d4af00 - validated distinct from CLUSTER_COLOR under deuteranopia
const CLUSTER_COLOR = [0.882, 0.420, 0.243];  // #e16b3e - red, "will be excluded" (matches the site's status red elsewhere)
const LIDAR_COLOR = [0.169, 0.169, 0.157];      // #2b2b28 - dark graphite, reserved for reference overlay only
let lidarOn = false;
let refOnlyMode = false; // "Reference only": hides the reconstruction layers (0-2), forces the LiDAR layer (3) on at full size

// ---- grid-accelerated DBSCAN (standard Ester et al. 1996, border points absorbed into clusters) ----
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
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) for (let dz = -1; dz <= 1; dz++) {
      const c = grid.get(keyOf(ix+dx, iy+dy, iz+dz));
      if (!c) continue;
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
    const seeds = neighbors.slice();
    let qi = 0;
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

// ============ wiring ============
const objectTabs = document.getElementById('object-tabs');
const methodTabs = document.getElementById('method-tabs');
const OBJECT_IDS = Object.keys(DATA);
const METHOD_IDS = ['mast3r_ga', 'vggt', 'colmap', 'hloc_colmap'];
let currentObject = OBJECT_IDS[0];
let currentMethod = 'mast3r_ga';
let viewer = null;
let cache = {}; // cache[objectId][methodId | 'lidarRef']

OBJECT_IDS.forEach(id => {
  const btn = document.createElement('button');
  btn.className = 'method-btn' + (id === currentObject ? ' active' : '');
  btn.textContent = DATA[id].label;
  btn.addEventListener('click', () => {
    if (id === currentObject) return;
    document.querySelectorAll('#object-tabs .method-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentObject = id;
    currentMethod = 'mast3r_ga';
    document.querySelectorAll('#method-tabs .method-btn[data-method]').forEach(b => b.classList.toggle('active', b.dataset.method === currentMethod));
    applyObjectConfig();
    loadMethod();
  });
  objectTabs.appendChild(btn);
});

METHOD_IDS.forEach(id => {
  const btn = document.createElement('button');
  btn.className = 'method-btn' + (id === currentMethod ? ' active' : '');
  btn.dataset.method = id;
  btn.textContent = DATA[currentObject].methods[id].label;
  btn.addEventListener('click', () => {
    document.querySelectorAll('#method-tabs .method-btn[data-method]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentMethod = id;
    if (refOnlyMode) { refOnlyMode = false; setRefOnlyVisuals(); setControlsEnabled(true); }
    loadMethod();
  });
  methodTabs.appendChild(btn);
});

function applyObjectConfig() {
  const cfg = DATA[currentObject];
  const ftSlider = document.getElementById('ft-slider'), epsSlider = document.getElementById('eps-slider');
  ftSlider.min = cfg.far_threshold.min; ftSlider.max = cfg.far_threshold.max;
  ftSlider.step = cfg.far_threshold.step; ftSlider.value = cfg.far_threshold.default;
  epsSlider.min = cfg.eps.min; epsSlider.max = cfg.eps.max;
  epsSlider.step = cfg.eps.step; epsSlider.value = cfg.eps.default;
  document.getElementById('ft-val').textContent = cfg.far_threshold.default.toFixed(1) + 'cm';
  document.getElementById('eps-val').textContent = cfg.eps.default.toFixed(1) + 'cm';
}

function getMethodData(objId, methodId) {
  if (!cache[objId]) cache[objId] = {};
  if (!cache[objId][methodId]) {
    const d = DATA[objId].methods[methodId];
    cache[objId][methodId] = {
      candidatePos: b64ToFloat32(d.candidate_pos),
      candidateDist: b64ToFloat32(d.candidate_dist_cm),
      contextPos: b64ToFloat32(d.context_pos),
      meta: d,
    };
  }
  return cache[objId][methodId];
}
function getLidarRefPos(objId) {
  if (!cache[objId]) cache[objId] = {};
  if (!cache[objId].lidarRef) cache[objId].lidarRef = b64ToFloat32(DATA[objId].methods.lidar_ref_pos);
  return cache[objId].lidarRef;
}

function loadMethod() {
  const md = getMethodData(currentObject, currentMethod);
  const lidarPos = getLidarRefPos(currentObject);
  if (!viewer) {
    viewer = makeViewer(document.getElementById('canvas'), [
      { pos: md.contextPos, color: solidColor(md.contextPos.length/3, CONTEXT_COLOR), defaultOn: true },
      { pos: new Float32Array(0), color: new Float32Array(0), defaultOn: true },
      { pos: new Float32Array(0), color: new Float32Array(0), defaultOn: true },
      { pos: lidarPos, color: solidColor(lidarPos.length/3, LIDAR_COLOR), defaultOn: lidarOn, sizeMul: 0.85 },
    ]);
  } else {
    viewer.setLayer(0, md.contextPos, solidColor(md.contextPos.length/3, CONTEXT_COLOR));
    viewer.setLayer(3, lidarPos, solidColor(lidarPos.length/3, LIDAR_COLOR));
    viewer.setLayerOn(3, lidarOn);
  }
  applyRefOnlyVisibility();
  recompute();
}

// "Reference only": hides the reconstruction (layers 0-2) and forces the LiDAR layer (3) on,
// regardless of the separate "LiDAR ref" overlay toggle - independent of currentMethod, so
// switching objects while active just keeps showing that object's raw reference alone.
function applyRefOnlyVisibility() {
  if (!viewer) return;
  const showRecon = !refOnlyMode;
  viewer.setLayerOn(0, showRecon);
  viewer.setLayerOn(1, showRecon);
  viewer.setLayerOn(2, showRecon);
  viewer.setLayerOn(3, refOnlyMode ? true : lidarOn);
}
function setRefOnlyVisuals() {
  refOnlyBtn.style.background = refOnlyMode ? 'var(--ref-magenta)' : 'transparent';
  refOnlyBtn.style.color = refOnlyMode ? '#ffffff' : 'var(--ref-magenta)';
  refOnlyBtn.style.fontWeight = refOnlyMode ? '700' : '400';
}
function setControlsEnabled(enabled) {
  ['ft-slider', 'eps-slider', 'mp-slider'].forEach(id => { document.getElementById(id).disabled = !enabled; });
  document.querySelector('.controls').style.opacity = enabled ? '1' : '0.4';
}

const lidarBtn = document.getElementById('lidar-toggle');
lidarBtn.addEventListener('click', () => {
  lidarOn = !lidarOn;
  lidarBtn.style.background = lidarOn ? 'var(--ref-magenta)' : 'transparent';
  lidarBtn.style.color = lidarOn ? '#0a0d13' : 'var(--ref-magenta)';
  lidarBtn.style.fontWeight = lidarOn ? '700' : '400';
  if (!refOnlyMode && viewer) viewer.setLayerOn(3, lidarOn);
});

const refOnlyBtn = document.getElementById('refonly-toggle');
refOnlyBtn.addEventListener('click', () => {
  refOnlyMode = !refOnlyMode;
  setRefOnlyVisuals();
  setControlsEnabled(!refOnlyMode);
  applyRefOnlyVisibility();
  recompute();
});

let recomputeTimer = null;
function recompute() {
  clearTimeout(recomputeTimer);
  if (refOnlyMode) {
    document.getElementById('stats-bar').innerHTML = '<b>Reference only</b> — no reconstruction loaded, DBSCAN tuning does not apply.';
    document.getElementById('summary-text').textContent = '';
    return;
  }
  if (!viewer) return; // WebGL unavailable - nothing to recompute into
  recomputeTimer = setTimeout(() => {
    const md = getMethodData(currentObject, currentMethod);
    const ft = parseFloat(document.getElementById('ft-slider').value);
    const eps = parseFloat(document.getElementById('eps-slider').value) / 100; // cm -> m
    const minPts = parseInt(document.getElementById('mp-slider').value, 10);

    const idx = [];
    for (let i = 0; i < md.candidateDist.length; i++) if (md.candidateDist[i] > ft) idx.push(i);
    const n = idx.length;
    const pos = new Float32Array(n * 3);
    for (let k = 0; k < n; k++) { const i = idx[k]; pos[k*3]=md.candidatePos[i*3]; pos[k*3+1]=md.candidatePos[i*3+1]; pos[k*3+2]=md.candidatePos[i*3+2]; }

    const t0 = performance.now();
    const { labels, nClusters } = dbscan(pos, eps, minPts);
    const t1 = performance.now();

    let nClustered = 0;
    for (let k = 0; k < n; k++) if (labels[k] !== -1) nClustered++;
    const nIsolated = n - nClustered;

    const clusterPos = new Float32Array(nClustered * 3), clusterColor = new Float32Array(nClustered * 3);
    const isoPos = new Float32Array(nIsolated * 3), isoColor = new Float32Array(nIsolated * 3);
    let ci = 0, ii = 0;
    for (let k = 0; k < n; k++) {
      if (labels[k] !== -1) {
        clusterPos[ci*3]=pos[k*3]; clusterPos[ci*3+1]=pos[k*3+1]; clusterPos[ci*3+2]=pos[k*3+2];
        clusterColor[ci*3]=CLUSTER_COLOR[0]; clusterColor[ci*3+1]=CLUSTER_COLOR[1]; clusterColor[ci*3+2]=CLUSTER_COLOR[2];
        ci++;
      } else {
        isoPos[ii*3]=pos[k*3]; isoPos[ii*3+1]=pos[k*3+1]; isoPos[ii*3+2]=pos[k*3+2];
        isoColor[ii*3]=ISOLATED_COLOR[0]; isoColor[ii*3+1]=ISOLATED_COLOR[1]; isoColor[ii*3+2]=ISOLATED_COLOR[2];
        ii++;
      }
    }
    // Candidates that fall *below* the current far_threshold are not clustered, but they
    // must still be drawn - otherwise lowering the slider's floor below EMBED_FLOOR_CM
    // would make the 1-5cm band disappear from the viewer entirely. Render them with the
    // context layer, which is exactly what they are at this threshold.
    const ctxN = md.contextPos.length / 3;
    const belowIdx = [];
    for (let i = 0; i < md.candidateDist.length; i++) if (md.candidateDist[i] <= ft) belowIdx.push(i);
    const ctxPos = new Float32Array((ctxN + belowIdx.length) * 3);
    ctxPos.set(md.contextPos, 0);
    for (let k = 0; k < belowIdx.length; k++) {
      const i = belowIdx[k], o = (ctxN + k) * 3;
      ctxPos[o] = md.candidatePos[i*3]; ctxPos[o+1] = md.candidatePos[i*3+1]; ctxPos[o+2] = md.candidatePos[i*3+2];
    }
    viewer.setLayer(0, ctxPos, solidColor(ctxPos.length / 3, CONTEXT_COLOR));
    viewer.setLayer(1, isoPos, isoColor);
    viewer.setLayer(2, clusterPos, clusterColor);

    const meta = md.meta;
    const scaleNote = meta.is_approx
      ? `<span class="approx-note">estimate on a subsample of candidates (${meta.n_candidates_embedded} of the true ${meta.n_candidates_true} points &gt;${meta.embed_floor_cm}cm) — fractions/percentages are approximate; final exact numbers are computed on the full data separately</span>`
      : `<span style="color:var(--text-faint)">exact numbers — candidates &lt;= embedding budget, no subsampling</span>`;

    document.getElementById('stats-bar').innerHTML =
      `n candidates (t&gt;${ft.toFixed(1)}cm) = <b>${n}</b> &nbsp;·&nbsp; `
      + `in clusters (will be excluded) = <b>${nClustered}</b> (${n?(nClustered/n*100).toFixed(1):'0.0'}%) &nbsp;·&nbsp; `
      + `isolated (kept) = <b>${nIsolated}</b> &nbsp;·&nbsp; `
      + `clusters: <span class="n-clusters">${nClusters}</span> &nbsp;·&nbsp; `
      + `<span style="color:var(--text-faint)">DBSCAN: ${(t1-t0).toFixed(0)}ms</span>`;

    document.getElementById('summary-text').innerHTML =
      `<b>Current parameters:</b> far_threshold=${ft.toFixed(1)}cm, eps=${(eps*100).toFixed(1)}cm, min_points=${minPts}. ${scaleNote}`;
  }, 180);
}

['ft-slider', 'eps-slider', 'mp-slider'].forEach(id => {
  document.getElementById(id).addEventListener('input', e => {
    document.getElementById(id.replace('slider','val')).textContent =
      id === 'mp-slider' ? e.target.value : parseFloat(e.target.value).toFixed(1) + 'cm';
    recompute();
  });
});

applyObjectConfig();
loadMethod();
</script>

</body>
</html>

"""
