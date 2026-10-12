import './unified.css';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import geometryAudit from '../docs/data/unified_opensim_geometry.json';

type BodyFrame = { p: [number, number, number]; r: number[] };
type ModelFrame = {
  bodies: BodyFrame[];
  paths: Array<Array<[number, number, number]>>;
  lengthsM: number[];
  coordinates: Record<string, number>;
};
type Reference = {
  model: string;
  bodyNames: string[];
  muscleNames: string[];
  neutral: ModelFrame;
  actions: Record<'squat' | 'bench' | 'press', ModelFrame[]>;
};
type Mode = 'neutral' | 'squat' | 'bench' | 'press';
type Group = 'all' | 'leg' | 'trunk' | 'upper';

const host = document.querySelector<HTMLDivElement>('#unified-app');
if (!host) throw new Error('missing unified-app');
host.innerHTML = `
  <div class="unified-shell">
    <main class="unified-main">
      <header class="unified-top">
        <small>OPEN SIM · 单一模型实验台</small>
        <h1>同一套骨骼与肌肉，查看静止和动作</h1>
        <p>80 个体段 · 520 条肌肉肌腱路径。静止与三个预设动作均由同一个 OpenSim 模型计算，不切换解剖来源。</p>
      </header>
      <div id="unified-stage" class="unified-stage" role="group" aria-label="可旋转、缩放的 OpenSim 全身模型">
        <div class="unified-overlay"><strong id="unified-status">正在加载 OpenSim 全身模型…</strong><span>拖动空白处旋转 · 滚轮或双指缩放 · 触摸可操作</span></div>
      </div>
      <div class="unified-controls">
        <div class="unified-tabs" role="group" aria-label="模型动作">
          <button type="button" data-mode="neutral" aria-pressed="true">静止</button>
          <button type="button" data-mode="squat" aria-pressed="false">深蹲</button>
          <button type="button" data-mode="bench" aria-pressed="false">卧推</button>
          <button type="button" data-mode="press" aria-pressed="false">实力举</button>
          <button type="button" id="unified-play" class="unified-button">▶ 播放</button>
        </div>
        <div class="unified-progress"><input id="unified-timeline" type="range" min="0" max="100" value="0" disabled aria-label="动作相位" /><output id="unified-phase">静止</output></div>
      </div>
    </main>
    <aside class="unified-side">
      <h2>模型层</h2>
      <p>骨段、关节、520 条肌肉及所有姿势都由同一份 <code>cyclistFullBodyMuscle.osim</code> 定义或计算。骨网格只读取该模型明确引用的几何文件，其中 19 个同名文件从 Pose2Sim 的 OpenSim 几何库补齐。</p>
      <label class="check"><input id="unified-bones" type="checkbox" checked /> 显示源模型骨网格</label>
      <label class="check"><input id="unified-muscles" type="checkbox" checked /> 显示肌肉路径</label>
      <label for="unified-group">查看区域</label>
      <select id="unified-group"><option value="all">全身 · 520 条</option><option value="leg">双腿 · 80 条</option><option value="trunk">躯干 · 约 360 条</option><option value="upper">肩臂 · 约 80 条</option></select>
      <label for="unified-muscle">选中一条路径</label>
      <select id="unified-muscle"></select>
      <div id="unified-readout" class="unified-card" aria-live="polite"></div>
      <div id="unified-joints" class="unified-card" aria-live="polite"></div>
      <div class="unified-legend"><span><i style="background:#f36d72"></i>路径变长</span><span><i style="background:#69c8dc"></i>路径变短</span><span><i style="background:#b77f83"></i>接近静止长度</span></div>
      <p class="unified-caveat">这些线是 OpenSim 肌肉肌腱路径，不是精细肌肉表面。目前的动作角度是教学预设，没有拟合真实卧推、深蹲或实力举；此模型的肩关节范围不足以完成完整过顶举。颜色只表示整条路径长度变化，没有计算激活、肌肉力或个人发力点。</p>
      <p class="unified-caveat">还有 ${geometryAudit.missing.length} 个骨网格引用缺文件；另有 ${geometryAudit.excluded.length} 节胸椎在该模型里显示于头骨上方，已从画面中排除。空白位置没有用另一套模型补画。补入的其余同名网格尚未逐个验证配准。</p>
      <p><a href="https://github.com/ross-wilkinson/opensim-model-fullBodyMuscleActuated" target="_blank" rel="noreferrer">主 OpenSim 模型 ↗</a> · <a href="https://github.com/perfanalytics/pose2sim" target="_blank" rel="noreferrer">补充几何来源 ↗</a> · <a href="/models/NOTICE-unified-opensim.txt">许可说明</a></p>
    </aside>
  </div>`;

const element = <T extends HTMLElement>(selector: string): T => {
  const result = document.querySelector<T>(selector);
  if (!result) throw new Error(`missing ${selector}`);
  return result;
};
const stage = element<HTMLDivElement>('#unified-stage');
const timeline = element<HTMLInputElement>('#unified-timeline');
const play = element<HTMLButtonElement>('#unified-play');
const groupSelect = element<HTMLSelectElement>('#unified-group');
const muscleSelect = element<HTMLSelectElement>('#unified-muscle');
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setClearColor('#091723');
stage.prepend(renderer.domElement);
const scene = new THREE.Scene();
scene.add(new THREE.AmbientLight('#d7e5ef', 1.75));
const light = new THREE.DirectionalLight('#ffffff', 2.1);
light.position.set(2, 4, 3);
scene.add(light);
const floor = new THREE.GridHelper(4, 20, '#274454', '#173344');
floor.position.y = -0.03;
scene.add(floor);
const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 100);
camera.position.set(2.8, 1.2, 0.35);
const orbit = new OrbitControls(camera, renderer.domElement);
orbit.target.set(0, 0.91, 0);
orbit.enableDamping = true;
orbit.minDistance = 1.2;
orbit.maxDistance = 8;
orbit.update();

function setDefaultCamera(nextMode: Mode): void {
  const positions: Record<Mode, [number, number, number]> = {
    neutral: [2.8, 1.2, 0.35],
    squat: [1.75, 1.2, 2.35],
    bench: [0.65, 1.45, 2.9],
    press: [2.8, 1.2, 0.35],
  };
  camera.position.set(...positions[nextMode]);
  orbit.target.set(0, nextMode === 'squat' ? 0.79 : 0.91, 0);
  orbit.update();
}

const bonesGroup = new THREE.Group();
const musclesGroup = new THREE.Group();
scene.add(bonesGroup, musclesGroup);
let data: Reference | undefined;
let mode: Mode = 'neutral';
let group: Group = 'all';
let phase = 0;
let selected = 0;
let playing = false;
let lastFrameTime = performance.now();
const bodyMeshes = new Map<string, THREE.Mesh[]>();
const muscleLines: THREE.Line[] = [];
const highlight = new THREE.Mesh(new THREE.BufferGeometry(),
  new THREE.MeshStandardMaterial({ color: '#ffe0a2', emissive: '#a7551a', roughness: 0.55 }));
musclesGroup.add(highlight);

function currentFrame(): ModelFrame | undefined {
  if (!data) return undefined;
  return mode === 'neutral' ? data.neutral : data.actions[mode][phase];
}

function groupOf(index: number): Group {
  if (index < 80) return 'leg';
  if (index < 446) return 'trunk';
  return 'upper';
}

function colour(ratio: number): string {
  if (ratio > 1.025) return '#f36d72';
  if (ratio < 0.975) return '#69c8dc';
  return '#b77f83';
}

function updateReadout(frame: ModelFrame): void {
  if (!data) return;
  const name = data.muscleNames[selected];
  const current = frame.lengthsM[selected];
  const baseline = data.neutral.lengthsM[selected];
  const ratio = current / baseline;
  const change = (ratio - 1) * 100;
  element('#unified-readout').innerHTML = `<strong>${name}</strong><span>当前 OpenSim 肌肉肌腱长度 ${(current * 100).toFixed(1)} cm</span><span>静止长度 ${(baseline * 100).toFixed(1)} cm</span><span class="${change > 2.5 ? 'longer' : change < -2.5 ? 'shorter' : ''}">相对静止 ${change >= 0 ? '+' : ''}${change.toFixed(1)}%</span>`;
  const labels: Record<Mode, Array<[string, string]>> = {
    neutral: [],
    squat: [['hip_flexion_r', '右髋屈曲'], ['knee_angle_r', '右膝屈曲'], ['ankle_angle_r', '右踝角']],
    bench: [['shoulder_elv_r', '右肩升举参数'], ['elbow_flex_r', '右肘屈曲']],
    press: [['shoulder_elv_r', '右肩升举参数'], ['elbow_flex_r', '右肘屈曲']],
  };
  element('#unified-joints').innerHTML = mode === 'neutral'
    ? '<strong>关节预设</strong><span>静止参考姿态</span>'
    : `<strong>关节预设 · ${phase}%</strong>${labels[mode].map(([key, label]) =>
      `<span>${label} ${(frame.coordinates[key] * 180 / Math.PI).toFixed(1)}°</span>`).join('')}<small>人为设定的角度，不是动作测量结果</small>`;
  stage.dataset.model = data.model;
  stage.dataset.mode = mode;
  stage.dataset.phase = String(phase);
  stage.dataset.muscles = String(data.muscleNames.length);
  stage.dataset.bodies = String(data.bodyNames.length);
  stage.dataset.selectedLengthM = String(current);
}

function updateFrame(): void {
  const frame = currentFrame();
  if (!data || !frame) return;
  const reference = data;
  const matrix = new THREE.Matrix4();
  data.bodyNames.forEach((name, index) => {
    const { p, r } = frame.bodies[index];
    matrix.set(r[0], r[1], r[2], p[0], r[3], r[4], r[5], p[1],
      r[6], r[7], r[8], p[2], 0, 0, 0, 1);
    for (const mesh of bodyMeshes.get(name) ?? []) {
      mesh.matrix.copy(matrix);
      mesh.matrixWorldNeedsUpdate = true;
    }
  });
  frame.paths.forEach((path, index) => {
    const line = muscleLines[index];
    const positions = line.geometry.getAttribute('position') as THREE.BufferAttribute;
    for (let i = 0; i < path.length; i++) positions.setXYZ(i, ...path[i]);
    line.geometry.setDrawRange(0, path.length);
    positions.needsUpdate = true;
    line.geometry.computeBoundingSphere();
    const ratio = frame.lengthsM[index] / reference.neutral.lengthsM[index];
    (line.material as THREE.LineBasicMaterial).color.set(index === selected ? '#ffe0a2' : colour(ratio));
    line.visible = element<HTMLInputElement>('#unified-muscles').checked
      && (group === 'all' || groupOf(index) === group);
  });
  const path = frame.paths[selected];
  highlight.geometry.dispose();
  highlight.geometry = new THREE.TubeGeometry(
    new THREE.CatmullRomCurve3(path.map(point => new THREE.Vector3(...point))),
    Math.max(16, path.length * 5), 0.008, 6, false);
  highlight.visible = element<HTMLInputElement>('#unified-muscles').checked
    && (group === 'all' || groupOf(selected) === group);
  bonesGroup.visible = element<HTMLInputElement>('#unified-bones').checked;
  element('#unified-phase').textContent = mode === 'neutral' ? '静止' : `${phase}%`;
  element('#unified-status').textContent = `${data.model} · ${mode === 'neutral' ? '静止' : `${phase}% ${mode}`} · 同一模型`;
  updateReadout(frame);
}

function syncMuscleOptions(): void {
  if (!data) return;
  const indices = data.muscleNames.map((_, index) => index)
    .filter(index => group === 'all' || groupOf(index) === group);
  if (!indices.includes(selected)) selected = indices[0];
  muscleSelect.innerHTML = indices.map(index =>
    `<option value="${index}"${index === selected ? ' selected' : ''}>${data?.muscleNames[index]}</option>`).join('');
  updateFrame();
}

for (const button of document.querySelectorAll<HTMLButtonElement>('[data-mode]')) {
  button.addEventListener('click', () => {
    mode = button.dataset.mode as Mode;
    setDefaultCamera(mode);
    if (data) {
      const defaultMuscle: Record<Mode, string> = {
        neutral: 'glmax1_r', squat: 'glmax1_r', bench: 'PECM1', press: 'DELT2',
      };
      const index = data.muscleNames.indexOf(defaultMuscle[mode]);
      if (index >= 0) selected = index;
      group = 'all';
      groupSelect.value = 'all';
      syncMuscleOptions();
    }
    phase = 0;
    timeline.value = '0';
    timeline.disabled = mode === 'neutral';
    playing = false;
    play.textContent = '▶ 播放';
    document.querySelectorAll<HTMLButtonElement>('[data-mode]').forEach(item =>
      item.setAttribute('aria-pressed', String(item === button)));
    updateFrame();
  });
}
timeline.addEventListener('input', () => {
  phase = Number(timeline.value);
  playing = false;
  play.textContent = '▶ 播放';
  updateFrame();
});
play.addEventListener('click', () => {
  if (mode === 'neutral') element<HTMLButtonElement>('[data-mode="squat"]').click();
  playing = !playing;
  play.textContent = playing ? 'Ⅱ 暂停' : '▶ 播放';
  lastFrameTime = performance.now();
});
groupSelect.addEventListener('change', () => {
  group = groupSelect.value as Group;
  syncMuscleOptions();
});
muscleSelect.addEventListener('change', () => {
  selected = Number(muscleSelect.value);
  updateFrame();
});
element<HTMLInputElement>('#unified-bones').addEventListener('change', updateFrame);
element<HTMLInputElement>('#unified-muscles').addEventListener('change', updateFrame);

new ResizeObserver(() => {
  const rect = stage.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  camera.aspect = rect.width / rect.height;
  camera.updateProjectionMatrix();
  renderer.setSize(rect.width, rect.height, false);
}).observe(stage);

function render(now: number): void {
  if (playing && data && mode !== 'neutral') {
    const delta = Math.min(100, now - lastFrameTime);
    const next = (phase + Math.max(1, Math.round(delta / 28))) % 101;
    if (next !== phase) {
      phase = next;
      timeline.value = String(phase);
      updateFrame();
    }
  }
  lastFrameTime = now;
  orbit.update();
  renderer.render(scene, camera);
  requestAnimationFrame(render);
}
requestAnimationFrame(render);

async function load(): Promise<void> {
  const [response, gltf] = await Promise.all([
    fetch('/data/unified_opensim_reference.json'),
    new GLTFLoader().loadAsync('/models/unified_opensim_skeleton.glb'),
  ]);
  if (!response.ok) throw new Error(`OpenSim frame data HTTP ${response.status}`);
  data = await response.json() as Reference;
  if (data.bodyNames.length !== 80 || data.muscleNames.length !== 520
    || data.actions.squat.length !== 101 || data.actions.bench.length !== 101
    || data.actions.press.length !== 101) throw new Error('OpenSim export is incomplete');
  const sourceBodyByNode = new Map(geometryAudit.present.map(entry =>
    [THREE.PropertyBinding.sanitizeNodeName(entry.node), entry.body]));
  gltf.scene.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return;
    const body = sourceBodyByNode.get(object.name);
    if (!body) return;
    const mesh = new THREE.Mesh(object.geometry, new THREE.MeshStandardMaterial({
      color: '#dfd9c7', side: THREE.DoubleSide, roughness: 0.7,
    }));
    mesh.name = object.name;
    mesh.matrixAutoUpdate = false;
    bonesGroup.add(mesh);
    const entries = bodyMeshes.get(body) ?? [];
    entries.push(mesh);
    bodyMeshes.set(body, entries);
  });
  if (bodyMeshes.size < 20) throw new Error(`only ${bodyMeshes.size} OpenSim bodies have source meshes; nodes: ${gltf.scene.children.slice(0, 5).map(child => child.name).join(', ')}`);
  const allFrames = [data.neutral, ...Object.values(data.actions).flat()];
  for (let index = 0; index < data.muscleNames.length; index++) {
    const capacity = Math.max(...allFrames.map(frame => frame.paths[index].length));
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(capacity * 3), 3));
    const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({
      color: '#b77f83', transparent: true, opacity: 0.78,
    }));
    line.name = data.muscleNames[index];
    musclesGroup.add(line);
    muscleLines.push(line);
  }
  selected = data.muscleNames.indexOf('glmax1_r');
  if (selected < 0) selected = 0;
  syncMuscleOptions();
  stage.dataset.ready = 'true';
  stage.dataset.sourceMeshes = String(geometryAudit.present.length);
  stage.dataset.missingSourceMeshes = String(geometryAudit.missing.length);
  stage.dataset.excludedSourceMeshes = String(geometryAudit.excluded.length);
}

load().catch(error => {
  element('#unified-status').textContent = `模型加载失败：${error instanceof Error ? error.message : String(error)}`;
  stage.dataset.ready = 'error';
});

if ('serviceWorker' in navigator && location.protocol !== 'file:') {
  void navigator.serviceWorker.register('/sw.js').catch(() => {
    // Online viewing and the bundled Android WebView do not require SW registration.
  });
}
