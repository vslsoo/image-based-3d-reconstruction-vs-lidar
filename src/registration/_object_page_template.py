"""Shared HTML/CSS/JS template for the per-object report pages (bus_stop_001.html,
bollard_003.html, etc. style). Extracted verbatim from site/bus_stop_sign_001.html so the
generic single-object 4-method Accuracy/Completeness/F1 viewer + DBSCAN tuner is not
re-implemented per object. See build_object_page.py for how the per-object data (
part1-data JSON) is computed and slotted in.

HEAD_TOP2 - lines 7-72 of the source page: everything between </head><body> and the opening
  of the .page div. 100% identical across every existing object page (checked by diff against
  bench_003.html) - contains only the CSS.
BODY_TEMPLATE - the static HTML shell (DBSCAN tuner section,
  Part 1 section, footer), with the handful of per-object bits replaced by tokens:
    __OBJ_ID__            - object id (page_id), appears in the footer path
    __OBJ_DISPLAY__        - human-facing display name (defaults to page_id), appears in the eyebrow
    __CALLOUT_BLOCK__      - optional callout <div> right under the subtitle (empty string if
                             the object has no special note, like bench_003)
    __CHECKBOX_CHECKED__   - ' checked' or '' - whether "Ignore DBSCAN" defaults on
    __CHECKBOX_NOTE__      - extra sentence(s) appended under the checkbox (may be empty)
MAIN_JS_AND_TAIL - line 166 (<script>) to EOF: the WebGL viewer, DBSCAN-in-JS, and Part 1
  panel-building logic. Fully data-driven off the PART1 JSON (see PART1 schema in
  build_object_page.py) - reused byte-for-byte, no per-object edits needed.
"""

HEAD_TOP2 = """\
</head>
<body>

<style>
  :root {
    /* forced light palette — matches the thesis-defense deck (white bg, forest-green accent) */
    --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084;
    --accent:#17805f; --accent-soft:#d9ece3; --green:#1aacb3; --red:#e16b3e; --ref-magenta:#2b2b28;
    --canvas-bg:#ffffff; --code-bg:#f5f4ef;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084; --accent:#17805f; --accent-soft:#d9ece3; --green:#1aacb3; --red:#e16b3e; --ref-magenta:#2b2b28; --code-bg:#f5f4ef; }
  }
  :root[data-theme="dark"] { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084; --accent:#17805f; --accent-soft:#d9ece3; --green:#1aacb3; --red:#e16b3e; --ref-magenta:#2b2b28; --code-bg:#f5f4ef; }
  :root[data-theme="light"] { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084; --accent:#17805f; --accent-soft:#d9ece3; --green:#1aacb3; --red:#e16b3e; --ref-magenta:#2b2b28; --code-bg:#f5f4ef; }

  * { box-sizing:border-box; }
  [hidden] { display:none !important; }   /* .slider-row/.legend set display:flex, which outranks it otherwise */
  body { margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; line-height:1.45; }
  .page { max-width:1520px; margin:0 auto; padding:28px 24px 72px; display:flex; flex-direction:column; gap:28px; }
  .eyebrow { font-size:11.5px; font-weight:600; letter-spacing:.09em; text-transform:uppercase; color:var(--accent); }
  h1 { font-size:23px; font-weight:650; margin:4px 0 2px; letter-spacing:-.01em; }
  h2 { font-size:18px; font-weight:650; margin:0 0 2px; }
  .subtitle { color:var(--text-dim); font-size:13.5px; max-width:82ch; }
  .mono { font-family:ui-monospace,"SF Mono","Cascadia Code",Menlo,Consolas,monospace; font-variant-numeric:tabular-nums; }
  section { display:flex; flex-direction:column; gap:14px; }
  hr.sep { border:none; border-top:1px solid var(--panel-border); margin:4px 0; }

  .params { font-size:12px; color:var(--text-faint); background:var(--code-bg); border:1px solid var(--panel-border); border-radius:10px; padding:11px 15px; }
  .params b { color:var(--text-dim); font-weight:600; }

  .grid-wrap { overflow-x:auto; }
  .grid1 { display:grid; grid-template-columns:repeat(auto-fit, minmax(300px, 1fr)); gap:14px; }

  .panel { background:var(--panel); border:1px solid var(--panel-border); border-radius:10px; padding:9px 9px 11px; display:flex; flex-direction:column; gap:7px; box-shadow:0 1px 2px rgba(24,26,23,0.05), 0 1px 8px rgba(24,26,23,0.03); }
  .tuner-panel { border-color:var(--accent); background:var(--accent-soft); box-shadow:0 2px 12px rgba(23,128,95,0.16); }
  canvas { width:100%; height:var(--canvas-h, 230px); display:block; border-radius:7px; background:var(--canvas-bg); touch-action:none; cursor:grab; }
  canvas:active { cursor:grabbing; }

  .tabs { display:flex; gap:5px; }
  .tab-btn, .toggle-btn { font-family:inherit; font-size:10.5px; padding:3px 9px; border-radius:6px; border:1px solid var(--panel-border); background:transparent; color:var(--text-dim); cursor:pointer; }
  .tab-btn:hover, .toggle-btn:hover { border-color:var(--accent); color:var(--text); }
  .tab-btn.active { background:var(--accent-soft); border-color:var(--accent); color:var(--text); font-weight:600; }
  .toggle-btn.active { background:var(--accent-soft); border-color: var(--ref-magenta); color:var(--text); font-weight:600; }

  .slider-row { display:flex; align-items:center; gap:8px; font-size:11px; color:var(--text-dim); }
  .slider-row input[type=range] { flex:1; accent-color:var(--accent); }
  .preset-btns { display:flex; gap:4px; }
  .preset-btn { font-size:10px; padding:2px 6px; border-radius:5px; border:1px solid var(--panel-border); background:transparent; color:var(--text-faint); cursor:pointer; }
  .preset-btn.active { border-color:var(--accent); color:var(--accent); font-weight:600; }

  .panel-stats { font-size:10.5px; color:var(--text-faint); }
  .panel-stats b { color:var(--text); font-weight:600; }
  .panel-stats .f1 { color:var(--accent); font-weight:700; font-size: 12px; }
  .panel-title { font-weight:650; font-size:13px; }

  .swatch { width:10px; height:10px; border-radius:3px; display:inline-block; margin-right:6px; vertical-align:-1px; border:1px solid var(--panel-border); }
  .legend { display:flex; flex-wrap:wrap; gap:2px 12px; font-size:10.5px; color:var(--text-faint); }
  .chip { display:inline-block; font-size:10.5px; color:var(--text-dim); background:var(--code-bg);
          border:1px solid var(--panel-border); border-radius:20px; padding:2px 9px; }

  .controls { display:grid; grid-template-columns:1fr 1fr 1fr; gap:16px; }
  .control { display:flex; flex-direction:column; gap:4px; }
  .control label { font-size:11.5px; color:var(--text-dim); display:flex; justify-content:space-between; }
  .control label .val { color:var(--accent); font-weight:700; font-family:ui-monospace,monospace; }
  .control input[type=range] { accent-color:var(--accent); }

  footer { color:var(--text-faint); font-size:11px; padding-top:4px; }
__NAV_CSS__
</style>

"""

BODY_TEMPLATE = """\
<div class="page">
  __SITE_NAV__
  <div>
    <div class="eyebrow">__OBJ_DISPLAY__ · gap-aware Chamfer</div>
    <h1>Accuracy / Completeness / F1 (reference-gap-aware)</h1>
    <div class="subtitle">
      Drag to rotate, scroll to zoom. The DBSCAN gap tuner below is a live gap-exclusion tuner that
      updates the Accuracy/Completeness/F1 panels further down as soon as any slider changes.
    </div>
__CALLOUT_BLOCK__  </div>

  <hr class="sep">

  <!-- ============ DBSCAN GAP TUNER (drives Part 1 below) ============ -->
  <section id="tuner-section">
    <h2>DBSCAN gap tuner</h2>
    <div class="subtitle">
      Controls which reconstruction points "far from the reference" are treated as a confirmed gap (excluded)
      vs. a single outlier (kept and penalised). Move any slider and the exclusion is recomputed for
      all methods, and the Accuracy/Completeness/F1 panels below update: both the cloud colouring and
      accuracy%/F1.
    </div>
    <div class="panel tuner-panel">
      <div class="controls">
        <div class="control">
          <label>far_threshold (candidate cutoff) <span class="val" id="ft-val">__FT_DEFAULT__.0cm</span></label>
          <input type="range" id="ft-slider" min="__FT_MIN__" max="__FT_MAX__" step="__FT_STEP__" value="__FT_DEFAULT__">
        </div>
        <div class="control">
          <label>eps (DBSCAN radius) <span class="val" id="eps-val">__EPS_DEFAULT__.0cm</span></label>
          <input type="range" id="eps-slider" min="__EPS_MIN__" max="__EPS_MAX__" step="__EPS_STEP__" value="__EPS_DEFAULT__">
        </div>
        <div class="control">
          <label>min_points <span class="val" id="mp-val">__MP_DEFAULT__</span></label>
          <input type="range" id="mp-slider" min="__MP_MIN__" max="__MP_MAX__" step="1" value="__MP_DEFAULT__">
        </div>
      </div>
      <label id="no-dbscan-row" style="display:flex; align-items:center; gap:8px; margin-top:12px; font-size:13px; font-weight:600; cursor:pointer; color:var(--text);">
        <input type="checkbox" id="no-dbscan-chk"__CHECKBOX_CHECKED__ style="width:16px; height:16px; cursor:pointer;">
        Ignore DBSCAN — count all points as-is (for objects without reference gaps)
      </label>
      <div style="font-size:11.5px; color:var(--text-faint); margin-top:4px; line-height:1.45;">
        When enabled, no far point is excluded as a “gap”: accuracy/F1 are computed over the whole cloud.
__CHECKBOX_NOTE__      </div>
      <div id="m3c2-tuner-note" hidden style="font-size:11.5px; color:var(--text-dim); margin-top:11px;
           line-height:1.45; border-left:3px solid var(--panel-border); padding-left:10px;"></div>
      <div id="tuner-stats" class="panel-stats mono" style="margin-top:10px;">Loading...</div>
    </div>
  </section>

  <hr class="sep">

  <!-- ============ PART 1 ============ -->
  <section id="part1-section">
    <h2>Accuracy / Completeness / F1 — gap-excluded (reactive to the tuner above), adjustable threshold t</h2>
    <details class="params">
      <summary style="cursor:pointer; color:var(--text-dim);">How these numbers are computed</summary>
      <div style="margin-top:8px;">
      <b>Pipeline:</b> aligned → density-matched (voxel = 1 cm, the grid the reference is delivered on) → gap-exclusion by
      the current tuner parameters above (only clusters are excluded; single outliers are kept and penalised).
      <b>Accuracy%/F1</b> are recomputed exactly (a population-weighted estimate over the true sizes of the "below floor"/
      "candidates" groups, since the two were subsampled at different rates — see the code). <b>Completeness%</b> is computed once against
      the FULL (non-excluded) reconstruction cloud and does not depend on the tuner — mathematically exact for t ≤
      far_threshold (for "good" target points the nearest neighbour physically cannot be an excludable gap point,
      since gap points are by construction farther than far_threshold from ANY target point); for t above far_threshold
      completeness may be slightly optimistic.
      </div>
    </details>
    <div id="m3c2-shared" hidden class="params" style="line-height:1.5;"></div>
    <div class="grid-wrap">
      <div class="grid1" id="part1-grid"></div>
    </div>
  </section>

  <footer>__OBJ_ID__ · outputs/density_matched/__OBJ_ID__/ · raw WebGL, no external libraries</footer>
</div>

"""

MAIN_JS_AND_TAIL = """\
<script>
const PART1 = JSON.parse(document.getElementById('part1-data').textContent);

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

function b64ToFloat32(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Float32Array(bytes.buffer);
}

// ---- mat4 helpers (Z-up, matches this project's Open3D convention) ----
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

const VERT_SRC = `
  attribute vec3 aPosition; attribute vec3 aColor;
  uniform mat4 uMVP; uniform float uPointSize;
  varying vec3 vColor;
  void main() { gl_Position = uMVP * vec4(aPosition, 1.0); gl_PointSize = uPointSize; vColor = aColor; }
`;
const FRAG_SRC = `
  precision mediump float; varying vec3 vColor;
  void main() { vec2 d = gl_PointCoord - vec2(0.5); if (dot(d,d) > 0.25) discard; gl_FragColor = vec4(vColor, 1.0); }
`;

function compileShader(gl, type, src) {
  const sh = gl.createShader(type); gl.shaderSource(sh, src); gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) console.error(gl.getShaderInfoLog(sh));
  return sh;
}

// Generic multi-layer point cloud viewer. layers[0] = "main" (positions fixed size,
// color can be swapped live via setLayerColor/setLayerData). layers[1..] = toggleable
// overlays (LiDAR/reconstruction reference overlay), fixed color.
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

  const state = layers.map(l => ({
    posBuf: makeBuffer(l.pos), colorBuf: makeBuffer(l.color), n: l.pos.length / 3, on: l.defaultOn !== false, sizeMul: l.sizeMul || 1,
  }));

  let minX=Infinity,minY=Infinity,minZ=Infinity,maxX=-Infinity,maxY=-Infinity,maxZ=-Infinity;
  for (const l of layers) for (let i = 0; i < l.pos.length; i += 3) {
    const x=l.pos[i],y=l.pos[i+1],z=l.pos[i+2];
    if (x<minX)minX=x; if (x>maxX)maxX=x; if (y<minY)minY=y; if (y>maxY)maxY=y; if (z<minZ)minZ=z; if (z>maxZ)maxZ=z;
  }
  const center = [(minX+maxX)/2, (minY+maxY)/2, (minZ+maxZ)/2];
  const diag = Math.hypot(maxX-minX, maxY-minY, maxZ-minZ) || 1;
  // Fit the camera to the object instead of to its 3D diagonal. A 2.5 m sign in a panel of
  // this shape was drawn at 1.35x its diagonal, which is a good distance for a compact object
  // and much too far for a thin tall one - the cloud came out a narrow strip with the detail
  // too small to read. This takes the vertical extent and the worst-case horizontal extent
  // over an orbit (the XY diagonal, since the camera turns), converts each into the distance
  // that just fits it in the current viewport, and keeps the larger with a 5% margin.
  const halfV = (maxZ - minZ) / 2 || diag / 2;
  const halfH = Math.hypot(maxX - minX, maxY - minY) / 2 || diag / 2;
  const FOV_Y = Math.PI / 4, MARGIN = 1.05;
  function fitDistance() {
    const aspect = (canvas.clientWidth || 1) / (canvas.clientHeight || 1);
    const tanY = Math.tan(FOV_Y / 2), tanX = tanY * aspect;
    return Math.max(halfV / tanY, halfH / tanX) * MARGIN;
  }
  let azimuth = 0.6, elevation = 0.35, distance = fitDistance();

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
      gl.bindBuffer(gl.ARRAY_BUFFER, s.posBuf);
      gl.enableVertexAttribArray(aPosition); gl.vertexAttribPointer(aPosition, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, s.colorBuf);
      gl.enableVertexAttribArray(aColor); gl.vertexAttribPointer(aColor, 3, gl.FLOAT, false, 0, 0);
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
  let userZoomed = false;
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    userZoomed = true;
    distance = Math.max(diag * 0.05, Math.min(diag * 6, distance * (1 + e.deltaY * 0.001)));
    draw();
  }, { passive: false });
  // a resize changes the aspect, so refit - unless the reader has zoomed by hand
  window.addEventListener('resize', () => { if (!userZoomed) distance = fitDistance(); draw(); });
  draw();

  return {
    draw,
    setLayer(idx, pos, color) {
      state[idx].n = pos.length / 3;
      gl.bindBuffer(gl.ARRAY_BUFFER, state[idx].posBuf); gl.bufferData(gl.ARRAY_BUFFER, pos, gl.DYNAMIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, state[idx].colorBuf); gl.bufferData(gl.ARRAY_BUFFER, color, gl.DYNAMIC_DRAW);
      draw();
    },
    setLayerColor(idx, color) {
      gl.bindBuffer(gl.ARRAY_BUFFER, state[idx].colorBuf); gl.bufferData(gl.ARRAY_BUFFER, color, gl.DYNAMIC_DRAW);
      draw();
    },
    setLayerOn(idx, on) { state[idx].on = on; draw(); },
  };
}

// Colorblind-checked status tones (validated with the dataviz skill's palette validator: all-pairs CVD deltaE >= 8, normal-vision floor >= 15).
const GREEN = [0.102, 0.675, 0.702];   // #1aacb3 - teal, not green: validated far from the error red
const RED = [0.882, 0.420, 0.243];     // #e16b3e - softened (white-blended) for a calmer look at high point density
const MAGENTA = [0.169, 0.169, 0.157];   // #2b2b28 - dark graphite, reserved for "reference/other-cloud overlay" everywhere

// M3C2's own diverging palette. Deliberately NOT the teal/orange used above for
// "within t / beyond t": those two colours already carry a meaning on this page, and M3C2
// answers a different question - which SIDE of the reference surface the reconstruction is
// on - so reusing them would quietly attach a second meaning to the same two colours.
// Blue and brick are far apart under every common colour-vision deficiency; the two greys
// are what a reader should NOT read a magnitude into, so they are kept unsaturated.
const M3C2_OUT_PALE = [0.898, 0.784, 0.769], M3C2_OUT_DEEP = [0.698, 0.094, 0.169];  // recon outside the ref
const M3C2_IN_PALE  = [0.769, 0.831, 0.898], M3C2_IN_DEEP  = [0.129, 0.400, 0.675];  // recon inside the ref
const M3C2_NOISE    = [0.588, 0.596, 0.573];   // |d| <= that point's own LoD95
// Dark, not pale: these points ARE the finding on some rows - 62% of VGGT's core points on
// the lamppost found nothing to pair with - and at the old near-background grey they read as
// haze over the object instead of as the largest fact on the panel.
const M3C2_NOPAIR   = [0.216, 0.231, 0.204];   // nothing to compare against in the cylinder
const M3C2_FULL_CM  = 10;                      // |d| at which the ramp reaches full saturation

// Grey is the whole point of the LoD: below it, the offset is not distinguishable from
// 1.96 x (roughness of the two clouds + this row's alignment error), so it must not read
// as a small-but-real difference. The 95% factor covers the alignment error too, which is
// why so much of a panel can be grey: the threshold has a floor of 1.96 x that error,
// 2.3-4.3 cm on these rows, before any surface roughness is added. Above it the ramp starts pale (just past the threshold) and
// deepens with the offset - a white midpoint would be invisible on a white canvas.
function m3c2Color(distCm, lodCm) {
  if (!Number.isFinite(distCm)) return M3C2_NOPAIR;
  if (Number.isFinite(lodCm) && Math.abs(distCm) <= lodCm) return M3C2_NOISE;
  const outside = distCm < 0;
  const pale = outside ? M3C2_OUT_PALE : M3C2_IN_PALE;
  const deep = outside ? M3C2_OUT_DEEP : M3C2_IN_DEEP;
  const k = Math.min(1, Math.abs(distCm) / M3C2_FULL_CM);
  return [pale[0] + (deep[0] - pale[0]) * k,
          pale[1] + (deep[1] - pale[1]) * k,
          pale[2] + (deep[2] - pale[2]) * k];
}
const rgbCss = c => `rgb(${c.map(v => Math.round(v * 255)).join(',')})`;

function solidColor(n, rgb) {
  const out = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) { out[i*3]=rgb[0]; out[i*3+1]=rgb[1]; out[i*3+2]=rgb[2]; }
  return out;
}
function thresholdColor(distCm, t) {
  const n = distCm.length, out = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const c = distCm[i] <= t ? GREEN : RED;
    out[i*3]=c[0]; out[i*3+1]=c[1]; out[i*3+2]=c[2];
  }
  return out;
}
function pctWithin(distCmFull, t) {
  let c = 0; for (let i = 0; i < distCmFull.length; i++) if (distCmFull[i] <= t) c++;
  return c / distCmFull.length * 100;
}

// ============ PART 1: accuracy/completeness/F1 (reactive to the DBSCAN tuner) ============
const METHOD_IDS = __METHOD_IDS_JSON__;
const FLOOR_CM = PART1.floor_cm;
const targetPosGlobal = b64ToFloat32(PART1.target_pos);

// A tall thin object (the sign is 2.5 m over a ~0.5 m footprint) in a panel wider than it is
// tall wastes most of the panel and leaves the cloud too small to read. Give those objects a
// taller canvas; compact and long-low ones keep the default.
function canvasHeightFor(posArr) {
  let minX=Infinity,minY=Infinity,minZ=Infinity,maxX=-Infinity,maxY=-Infinity,maxZ=-Infinity;
  for (let i=0;i<posArr.length;i+=3){ const x=posArr[i],y=posArr[i+1],z=posArr[i+2];
    if(x<minX)minX=x; if(x>maxX)maxX=x; if(y<minY)minY=y; if(y>maxY)maxY=y; if(z<minZ)minZ=z; if(z>maxZ)maxZ=z; }
  const foot = Math.max(maxX-minX, maxY-minY) || 1;
  const aspect = (maxZ-minZ) / foot;
  return aspect >= 2 ? 340 : (aspect >= 1.2 ? 280 : 220);
}

document.getElementById('part1-grid').style.setProperty('--canvas-h', canvasHeightFor(targetPosGlobal) + 'px');

const RENDER_CAP = 12000;   // total points drawn per panel, split between the two pools

// global tuner state, shared by all 4 panels
const FT_DEFAULT = __FT_DEFAULT__, EPS_DEFAULT = __EPS_DEFAULT__, MP_DEFAULT = __MP_DEFAULT__;
let farThreshold = FT_DEFAULT, epsCm = EPS_DEFAULT, minPts = MP_DEFAULT;
// Read the checkbox instead of assuming DBSCAN is on. On the pages whose honest default is
// "Ignore DBSCAN" (flashlight, bus_stop_sign) the box ships already checked, and hard-coding
// `true` here meant the page rendered a checked box while still excluding gap points - every
// number on it was a DBSCAN number, up to 33 points away from the reported one, until the
// reader toggled the box twice.
const DBSCAN_DEFAULT_ON = !document.getElementById('no-dbscan-chk').checked;
let applyDbscan = DBSCAN_DEFAULT_ON;

// M3C2 arrives in its own <script> block (build_object_page.py: m3c2_block) - it shares no
// pipeline with the Chamfer payload above, and an absent block just means no M3C2 tab.
const M3C2 = (() => {
  const el = document.getElementById('m3c2-data');
  try { return el ? JSON.parse(el.textContent) : null; } catch { return null; }
})();
let panelsOnM3c2 = 0;   // how many panels currently have the M3C2 tab open (drives the tuner)

const part1State = {};
METHOD_IDS.forEach(methodId => {
  const d = PART1[methodId];
  const m = M3C2 ? M3C2[methodId] : null;
  part1State[methodId] = {
    m3c2: m ? {
      ...m,
      pos: b64ToFloat32(m.pos),
      dist: b64ToFloat32(m.dist_cm),
      lod: b64ToFloat32(m.lod_cm),
    } : null,
    label: d.label,
    group: d.group,
    belowPos: b64ToFloat32(d.below_pos),
    belowDist: b64ToFloat32(d.below_dist_cm),
    candidatePos: b64ToFloat32(d.candidate_pos),
    candidateDist: b64ToFloat32(d.candidate_dist_cm),
    targetDist: b64ToFloat32(d.target_dist_cm), // completeness - static, see note in section 1's params box
    nSourceTotal: d.n_source_total,
    nBelowTrue: d.n_below_floor_true,
    nCandidatesTrue: d.n_candidates_true,
    keptMask: null, // Uint8Array over candidatePos, filled by recomputeExclusion() right below
  };
});
// Populate keptMask synchronously for every panel BEFORE any panel is built - each panel's
// requestAnimationFrame(refresh) below can otherwise fire before fullRecomputeFromTuner()'s
// setTimeout(…, 10) does (rAF often beats a 10ms timer, especially with few panels), reading
// a still-null keptMask and throwing. recomputeExclusion only needs part1State, not the DOM,
// so it's safe to run here, ahead of the panel-building loop.
METHOD_IDS.forEach(methodId => recomputeExclusion(methodId));

// Re-runs DBSCAN for one method's candidate pool under the CURRENT global
// far_threshold/eps/minPts, filling keptMask (1=kept/isolated, 0=excluded/clustered).
function recomputeExclusion(methodId) {
  const s = part1State[methodId];
  const n = s.candidateDist.length;
  if (!applyDbscan) { s.keptMask = new Uint8Array(n).fill(1); return; } // keep everything, no gap-exclusion
  const activeIdx = [];
  for (let i = 0; i < n; i++) if (s.candidateDist[i] > farThreshold) activeIdx.push(i);
  const pos = new Float32Array(activeIdx.length * 3);
  for (let k = 0; k < activeIdx.length; k++) {
    const i = activeIdx[k];
    pos[k*3] = s.candidatePos[i*3]; pos[k*3+1] = s.candidatePos[i*3+1]; pos[k*3+2] = s.candidatePos[i*3+2];
  }
  const { labels } = dbscan(pos, epsCm / 100, minPts);
  const keptMask = new Uint8Array(n).fill(1);
  for (let k = 0; k < activeIdx.length; k++) if (labels[k] !== -1) keptMask[activeIdx[k]] = 0;
  s.keptMask = keptMask;
}

// Population-weighted accuracy% at threshold t: below/candidates were subsampled at
// DIFFERENT rates from their true group sizes, so a naive concatenated count would
// over-weight whichever group was sampled more densely - this extrapolates each
// group's in-sample fraction back to its true count before combining.
function computeAccuracyPct(methodId, t) {
  const s = part1State[methodId];
  let belowWithin = 0;
  for (let i = 0; i < s.belowDist.length; i++) if (s.belowDist[i] <= t) belowWithin++;
  const belowWithinEst = s.nBelowTrue * (belowWithin / s.belowDist.length);

  let keptWithin = 0, keptTotal = 0;
  for (let i = 0; i < s.candidateDist.length; i++) {
    if (!s.keptMask[i]) continue;
    keptTotal++;
    if (s.candidateDist[i] <= t) keptWithin++;
  }
  const keptWithinEst = s.nCandidatesTrue * (keptWithin / s.candidateDist.length);
  const keptTotalEst = s.nCandidatesTrue * (keptTotal / s.candidateDist.length);

  const totalEst = s.nBelowTrue + keptTotalEst;
  return {
    pct: totalEst > 0 ? (belowWithinEst + keptWithinEst) / totalEst * 100 : 0,
    nExcludedEst: Math.round(s.nCandidatesTrue - keptTotalEst),
  };
}

// Exact per-panel metrics computed in Python over the FULL cloud
// (build_accuracy_f1_summary_table.py -> docs/tables/summary_all_objects_accuracy_f1.json,
// injected here by build_object_page.py --relayout). The browser only holds a capped
// subsample of each pool (EMBED_CAP), and re-running DBSCAN on a thinned cloud finds fewer
// clusters, so the live gap mask under-excludes and Accuracy reads low - on bus_stop's vggt
// panel, with 1.6M candidate points behind a 60k sample, by ~9 points. So while the tuner
// sits at this page's defaults, show Python's numbers; the live estimate is what the tuner
// is for, and only appears once it moves.
const EXACT = (() => {
  const el = document.getElementById('exact-data');
  try { return el ? JSON.parse(el.textContent) : null; } catch { return null; }
})();
function atTunerDefaults() {
  return applyDbscan === DBSCAN_DEFAULT_ON
    && (!applyDbscan || (farThreshold === FT_DEFAULT && epsCm === EPS_DEFAULT && minPts === MP_DEFAULT));
}
function shownMetrics(methodId, t) {
  const s = part1State[methodId];
  const e = EXACT && atTunerDefaults() && [3, 5, 10].includes(t) ? (EXACT.panels || {})[methodId] : null;
  if (e) {
    const k = `${t}cm`;
    return { accPct: e[`acc_${k}`], compPct: e[`comp_${k}`], f1Pct: e[`f1_${k}`], nExcluded: e.n_excluded, exact: true };
  }
  const acc = computeAccuracyPct(methodId, t);
  const compPct = pctWithin(s.targetDist, t);
  const f1Pct = (acc.pct + compPct) > 0 ? 2 * acc.pct * compPct / (acc.pct + compPct) : 0;
  return { accPct: acc.pct, compPct, f1Pct, nExcluded: acc.nExcludedEst, exact: false };
}

// What is drawn has to look like what the number says. Taking the FIRST RENDER_CAP points of
// each pool did neither: the two pools were drawn 1:1 whatever their real sizes (so a panel
// reading "74% within t" came out half red), and each was a contiguous slab of voxel order
// rather than a sample spread over the object. The budget is now split in proportion to the
// true population of each pool, each pool is strided, and the kept "beyond t" points are
// written first so a within-t point wins any depth tie.
function buildAccuracyRender(methodId, t) {
  const s = part1State[methodId];
  let kept = 0;
  for (let i = 0; i < s.keptMask.length; i++) if (s.keptMask[i]) kept++;
  const belowTrue = s.nBelowTrue;
  const keptTrue = s.candidateDist.length ? s.nCandidatesTrue * (kept / s.candidateDist.length) : 0;
  const total = belowTrue + keptTrue;
  const nKeptDraw = total > 0 ? Math.min(kept, Math.round(RENDER_CAP * keptTrue / total)) : 0;
  const nBelowDraw = Math.min(s.belowDist.length, RENDER_CAP - nKeptDraw);

  const pos = [], color = [];
  const push = (px, py, pz, dist) => {
    pos.push(px, py, pz);
    const c = dist <= t ? GREEN : RED;
    color.push(c[0], c[1], c[2]);
  };
  if (nKeptDraw > 0) {
    const step = kept / nKeptDraw;
    let seen = 0, drawn = 0;
    for (let i = 0; i < s.candidateDist.length && drawn < nKeptDraw; i++) {
      if (!s.keptMask[i]) continue;
      if (seen++ >= drawn * step) { push(s.candidatePos[i*3], s.candidatePos[i*3+1], s.candidatePos[i*3+2], s.candidateDist[i]); drawn++; }
    }
  }
  if (nBelowDraw > 0) {
    const step = s.belowDist.length / nBelowDraw;
    for (let k = 0; k < nBelowDraw; k++) {
      const i = Math.min(s.belowDist.length - 1, Math.floor(k * step));
      push(s.belowPos[i*3], s.belowPos[i*3+1], s.belowPos[i*3+2], s.belowDist[i]);
    }
  }
  return { pos: new Float32Array(pos), color: new Float32Array(color) };
}

// The M3C2 layer is drawn straight from the embedded sample - no pool weighting to undo
// (there is one pool), no exclusion mask to apply (M3C2 has none), so this only strides the
// sample down to the panel's point budget.
function buildM3c2Render(methodId, onlyUnpaired = false) {
  const m = part1State[methodId].m3c2;
  // "no pair" view: the same cloud with everything that DID pair dropped, so the shape of
  // what the method put where the reference has no surface is visible on its own.
  const idx = [];
  for (let i = 0; i < m.dist.length; i++) if (!onlyUnpaired || !Number.isFinite(m.dist[i])) idx.push(i);
  const n = idx.length;
  const draw = Math.min(n, RENDER_CAP);
  const pos = new Float32Array(draw * 3), color = new Float32Array(draw * 3);
  const step = draw ? n / draw : 1;
  for (let k = 0; k < draw; k++) {
    const i = idx[Math.min(n - 1, Math.floor(k * step))];
    pos[k*3] = m.pos[i*3]; pos[k*3+1] = m.pos[i*3+1]; pos[k*3+2] = m.pos[i*3+2];
    const c = m3c2Color(m.dist[i], m.lod[i]);
    color[k*3] = c[0]; color[k*3+1] = c[1]; color[k*3+2] = c[2];
  }
  return { pos, color };
}

// The part of the M3C2 explanation that is identical for all four panels: what the colours
// mean, that the core points are thinned, and that the tuner has nothing to do here. It used
// to be printed inside every panel, four times over, which is three times more reading for
// the same sentence. Per-row settings (D, d, this row's registration error) stay in the panel.
function fillM3c2SharedNote() {
  const el = document.getElementById('m3c2-shared');
  if (!el) return;
  const any = METHOD_IDS.map(id => part1State[id].m3c2).find(Boolean);
  if (!any) return;
  const sw = c => `<span class="swatch" style="background:${rgbCss(c)}"></span>`;
  el.innerHTML = `
    <div class="legend" style="margin-bottom:6px;">
      <span>${sw(M3C2_OUT_DEEP)}outside the reference</span>
      <span>${sw(M3C2_IN_DEEP)}inside it</span>
      <span>${sw(M3C2_NOISE)}below its LoD95</span>
      <span>${sw(M3C2_NOPAIR)}no pair — nothing to measure against</span>
    </div>
    <b>M3C2</b> measures along each core point's own surface normal, so it separates “the surface is
    displaced” from “the surface is missing”: a core point beside a hole in the reference finds nothing
    in its search cylinder and drops out instead of being scored. Those are the <b>no pair</b> points, and
    the <b>no pair</b> tab draws them alone — on some rows they are most of the cloud. Core points are
    thinned to ${any.voxel_cm.toFixed(0)} cm, so this view is sparser than the Accuracy one, and the DBSCAN
    tuner above does not apply: a gap in the reference removes itself here.`;
}

// Everything under an M3C2 panel: what the four colours mean, the three figures the results
// table also carries, how many core points had nothing to compare against, and the settings
// the run used - including this row's own registration error, which is the natural place for
// that assumption to become visible instead of living in a paragraph somewhere else.
function m3c2PanelBlock(m) {
  const num = v => (v ?? 0).toLocaleString('ru-RU');
  const pct = v => v == null ? '—' : v.toFixed(1) + '%';
  return `
    <div class="m3c2-only" hidden>
      <div class="panel-stats">
        median |d| = <b>${m.median_abs_cm == null ? '—' : m.median_abs_cm.toFixed(2) + ' cm'}</b>
        &nbsp;·&nbsp; <b>${pct(m.significant_pct)}</b> beyond LoD95
        &nbsp;·&nbsp; <b>${pct(m.outside_pct)}</b> of the paired points sit outside the reference<br>
        <b>${num(m.n_unpaired)}</b> of <b>${num(m.n_corepoints)}</b> core points had no pair in the cylinder
        <div style="margin-top:5px;"><span class="chip">M3C2: D=${m.D_cm.toFixed(0)} cm · d=${m.d_cm.toFixed(0)} cm
          · core points ${m.voxel_cm.toFixed(0)} cm · reg.err = ${m.reg_err_cm.toFixed(2)} cm (this row's alignment RMSE)</span></div>
        ${m.approx ? `<div style="margin-top:5px; color:var(--text-faint);">`
          + `${num(m.n_corepoints - Math.min(m.n_corepoints, m.dist.length))} core points are left out of the drawing `
          + `(an even subsample; the figures above are over all of them).</div>` : ''}
      </div>
    </div>`;
}

const part1Grid = document.getElementById('part1-grid');
const part1Panels = {};

let lastGroup = null;
for (const methodId of METHOD_IDS) {
  const s = part1State[methodId];
  if (s.group && s.group !== lastGroup) {
    lastGroup = s.group;
    const header = document.createElement('div');
    header.style.cssText = 'grid-column:1/-1; font-weight:650; font-size:13.5px; margin-top:10px; padding:8px 2px 4px; border-top:1px solid var(--panel-border); color:var(--text);';
    header.textContent = s.group;
    part1Grid.appendChild(header);
  }
  const panel = document.createElement('div');
  panel.className = 'panel';
  panel.innerHTML = `
    <div class="panel-title">${s.label}</div>
    <canvas></canvas>
    <div class="tabs">
      <button class="tab-btn active" data-tab="accuracy">Accuracy</button>
      <button class="tab-btn" data-tab="completeness">Completeness</button>
      ${s.m3c2 ? '<button class="tab-btn" data-tab="m3c2">M3C2</button>' : ''}
      ${s.m3c2 ? '<button class="tab-btn" data-tab="nopair">no pair</button>' : ''}
      <button class="toggle-btn" data-overlay>LiDAR ref</button>
    </div>
    <div class="slider-row chamfer-only">
      <span>t=</span><input type="range" min="0.5" max="15" step="0.1" value="3">
      <span class="mono thr-val">3.0cm</span>
      <div class="preset-btns">
        <button class="preset-btn active" data-t="3">3</button>
        <button class="preset-btn" data-t="5">5</button>
        <button class="preset-btn" data-t="10">10</button>
      </div>
    </div>
    <div class="panel-stats chamfer-only">
      <span class="tab-pct">-</span> within t &nbsp;·&nbsp; <span class="f1">F1=-</span>
      &nbsp;·&nbsp; <span class="chamfer">Chamfer —</span><br>
      <span class="mono">source n=${s.nSourceTotal} · target n=${PART1.n_target_total} · excluded≈<span class="excl-count">0</span></span>
    </div>
    ${s.m3c2 ? m3c2PanelBlock(s.m3c2) : ''}
  `;
  part1Grid.appendChild(panel);

  const canvas = panel.querySelector('canvas');
  const slider = panel.querySelector('input[type=range]');
  const thrVal = panel.querySelector('.thr-val');
  const tabPct = panel.querySelector('.tab-pct');
  const f1El = panel.querySelector('.f1');
  const exclEl = panel.querySelector('.excl-count');
  const chamferEl = panel.querySelector('.chamfer');
  const tabBtns = panel.querySelectorAll('.tab-btn');
  const overlayBtn = panel.querySelector('[data-overlay]');
  const presetBtns = panel.querySelectorAll('.preset-btn');

  let activeTab = 'accuracy';
  let viewer = null;

  function overlayFor() {
    // accuracy and M3C2 draw the reconstruction -> overlay the LiDAR; completeness draws the
    // LiDAR -> overlay the reconstruction
    if (activeTab !== 'completeness') return targetPosGlobal;
    const r = buildAccuracyRender(methodId, 1e9); // all kept points, color irrelevant for an overlay
    return r.pos;
  }

  function refresh() {
    const t = parseFloat(slider.value);
    const m = shownMetrics(methodId, t);
    tabPct.textContent = (activeTab === 'accuracy' ? m.accPct : m.compPct).toFixed(1) + '%';
    f1El.textContent = 'F1=' + m.f1Pct.toFixed(1) + '%';   // percent everywhere on the site
    exclEl.textContent = m.nExcluded.toLocaleString('ru-RU');
    // The symmetric Chamfer is a mean over all distances, computed in Python over the full
    // cloud - not a thing to re-estimate from the embedded subsample. So it is shown only
    // while the exact figures are (tuner at this page's defaults) and blanked otherwise,
    // the same rule the 95% CI column follows on frame_count_study.html.
    const exact = m.exact ? (EXACT && (EXACT.panels || {})[methodId]) : null;
    const chamfer = exact ? exact.chamfer_sym_cm : null;
    chamferEl.textContent = chamfer == null ? 'Chamfer —' : `Chamfer ${chamfer.toFixed(2)} cm`;
    chamferEl.title = chamfer == null
      ? 'the symmetric Chamfer distance is computed over the full cloud, so it is shown only at the default gap settings'
      : 'symmetric Chamfer: the mean of the two one-sided means, unsquared. Does not follow the t slider.';
    chamferEl.style.color = chamfer == null ? 'var(--text-faint)' : '';

    const main = activeTab === 'accuracy' ? buildAccuracyRender(methodId, t)
      : activeTab === 'm3c2' ? buildM3c2Render(methodId)
      : activeTab === 'nopair' ? buildM3c2Render(methodId, true)
      : { pos: targetPosGlobal, color: thresholdColor(s.targetDist, t) };

    if (!viewer) {
      viewer = makeViewer(canvas, [
        { pos: main.pos, color: main.color, defaultOn: true },
        { pos: overlayFor(), color: solidColor(overlayFor().length/3, MAGENTA), defaultOn: false, sizeMul: 0.85 },
      ]);
    } else {
      viewer.setLayer(0, main.pos, main.color);
      viewer.setLayer(1, overlayFor(), solidColor(overlayFor().length/3, MAGENTA));
      viewer.setLayerOn(1, overlayBtn.classList.contains('active'));
    }
  }

  part1Panels[methodId] = { refresh };
  requestAnimationFrame(refresh);

  slider.addEventListener('input', () => {
    thrVal.textContent = parseFloat(slider.value).toFixed(1) + 'cm';
    presetBtns.forEach(b => b.classList.toggle('active', parseFloat(b.dataset.t) === parseFloat(slider.value)));
    refresh();
  });
  presetBtns.forEach(b => b.addEventListener('click', () => {
    slider.value = b.dataset.t; slider.dispatchEvent(new Event('input'));
  }));
  tabBtns.forEach(b => b.addEventListener('click', () => {
    tabBtns.forEach(x => x.classList.remove('active')); b.classList.add('active');
    const previous = activeTab;
    activeTab = b.dataset.tab;
    if (activeTab !== previous) {
      // the t slider, the within-t/F1 line and the DBSCAN tuner all belong to the Chamfer
      // metrics; on the M3C2 tab they would sit there looking live while changing nothing
      const isM3c2 = t => t === 'm3c2' || t === 'nopair';
      panelsOnM3c2 += (isM3c2(activeTab) ? 1 : 0) - (isM3c2(previous) ? 1 : 0);
      panel.querySelectorAll('.chamfer-only').forEach(el => { el.hidden = isM3c2(activeTab); });
      panel.querySelectorAll('.m3c2-only').forEach(el => { el.hidden = !isM3c2(activeTab); });
      syncDbscanUiState();
    }
    refresh();
  }));
  overlayBtn.addEventListener('click', () => {
    overlayBtn.classList.toggle('active');
    viewer.setLayerOn(1, overlayBtn.classList.contains('active'));
  });
}

// ============ DBSCAN tuner controls (drive all 4 Part 1 panels above^) ============
// One line saying which numbers the panels are showing: Python's exact ones (tuner at this
// page's defaults) or the browser's live estimate (tuner moved). Silently swapping between
// them would be worse than either.
function sourceNote() {
  if (!EXACT) return '';
  return atTunerDefaults()
    ? ' &nbsp;·&nbsp; <span style="color:var(--text-faint)">panel figures are exact, computed over the full clouds '
      + '</span>'
    : ' &nbsp;·&nbsp; <span style="color:var(--text-faint)">panel figures are live estimates from the embedded point '
      + 'subsample — return the tuner to its defaults for the exact ones</span>';
}

function fullRecomputeFromTuner() {
  const tunerStats = document.getElementById('tuner-stats');
  if (!applyDbscan) {
    METHOD_IDS.forEach(methodId => { recomputeExclusion(methodId); part1Panels[methodId].refresh(); });
    tunerStats.innerHTML = '<b>DBSCAN off</b> — no point is excluded; accuracy/F1 are computed over the whole cloud.'
      + sourceNote();
    return;
  }
  tunerStats.textContent = 'Recomputing DBSCAN for all methods...';
  setTimeout(() => {
    const t0 = performance.now();
    const parts = [];
    METHOD_IDS.forEach(methodId => {
      recomputeExclusion(methodId);
      part1Panels[methodId].refresh();
      const s = part1State[methodId];
      let excluded = 0;
      for (let i = 0; i < s.candidateDist.length; i++) if (!s.keptMask[i]) excluded++;
      // exact count when the tuner is at defaults (same rule as the panels), estimate otherwise
      const m = shownMetrics(methodId, 3);
      const excludedEst = m.exact ? m.nExcluded : Math.round(s.nCandidatesTrue * (excluded / s.candidateDist.length));
      parts.push(`${s.label}: ${m.exact ? '' : '~'}${excludedEst.toLocaleString('ru-RU')} excluded `
                 + `(${(excludedEst/s.nSourceTotal*100).toFixed(1)}%)`);
    });
    const dt = (performance.now() - t0).toFixed(0);
    tunerStats.innerHTML = parts.join(' &nbsp;·&nbsp; ') + ` <span style="color:var(--text-faint)">(${dt}ms)</span>`
      + sourceNote();
  }, 10);
}

let tunerDebounce = null;
function onTunerChange() {
  clearTimeout(tunerDebounce);
  tunerDebounce = setTimeout(fullRecomputeFromTuner, 200);
}

const ftSlider = document.getElementById('ft-slider'), epsSlider = document.getElementById('eps-slider'), mpSlider = document.getElementById('mp-slider');
ftSlider.addEventListener('input', () => {
  farThreshold = parseFloat(ftSlider.value);
  document.getElementById('ft-val').textContent = farThreshold.toFixed(1) + 'cm';
  onTunerChange();
});
epsSlider.addEventListener('input', () => {
  epsCm = parseFloat(epsSlider.value);
  document.getElementById('eps-val').textContent = epsCm.toFixed(1) + 'cm';
  onTunerChange();
});
mpSlider.addEventListener('input', () => {
  minPts = parseInt(mpSlider.value, 10);
  document.getElementById('mp-val').textContent = minPts;
  onTunerChange();
});

const noDbscanChk = document.getElementById('no-dbscan-chk');
function syncDbscanUiState() {
  // grey out + disable the three sliders when they no longer affect anything: either DBSCAN
  // is off, or every panel is showing M3C2, which does not use it. Leaving them live-looking
  // on the M3C2 tab is the whole trap - a reader drags a slider, nothing moves, and concludes
  // either that the page is broken or that the M3C2 numbers depend on a setting. They do not.
  const allOnM3c2 = panelsOnM3c2 > 0 && panelsOnM3c2 === METHOD_IDS.length;
  const live = applyDbscan && !allOnM3c2;
  [ftSlider, epsSlider, mpSlider].forEach(sl => { sl.disabled = !live; });
  document.querySelector('#tuner-section .controls').style.opacity = live ? '1' : '0.4';

  const shared = document.getElementById('m3c2-shared');
  if (shared) shared.hidden = panelsOnM3c2 === 0;
  const note = document.getElementById('m3c2-tuner-note');
  note.hidden = panelsOnM3c2 === 0;
  if (panelsOnM3c2) {
    note.innerHTML = '<b>M3C2 does not use DBSCAN.</b> A gap in the reference excludes itself there: a core '
      + 'point beside one simply finds nothing to pair with inside its cylinder, and leaves the statistics '
      + 'instead of being scored as an error. '
      + (allOnM3c2
          ? 'Every panel is on the M3C2 tab, so these sliders currently change nothing.'
          : `${panelsOnM3c2} of ${METHOD_IDS.length} panels are on the M3C2 tab; the sliders below still drive `
            + 'the other ' + (METHOD_IDS.length - panelsOnM3c2) + '.');
  }
}
noDbscanChk.addEventListener('change', () => {
  applyDbscan = !noDbscanChk.checked;
  syncDbscanUiState();
  fullRecomputeFromTuner();
});
fillM3c2SharedNote();
syncDbscanUiState(); // reflect the default (checkbox starts checked = DBSCAN off)

fullRecomputeFromTuner();
</script>

</body>
</html>

"""
