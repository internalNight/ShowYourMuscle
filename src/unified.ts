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
type MuscleSkin = { meshes: Array<{ name: string; modelMuscles: string[]; bodyIndices: [number, number]; weightOffset: number; vertexCount: number }> };
type Mode = 'neutral' | 'squat' | 'bench' | 'press' | 'custom';
type Group = 'all' | 'leg' | 'trunk' | 'upper';

const host = document.querySelector<HTMLDivElement>('#unified-app');
if (!host) throw new Error('missing unified-app');
host.innerHTML = `
  <div class="unified-shell">
    <main class="unified-main">
      <header class="unified-top">
        <small>OPEN SIM · 单一模型实验台</small>
        <h1>同一套骨骼与肌肉，查看静止和动作</h1>
        <p>OpenSim 驱动骨骼与 520 条肌肉肌腱路径；精细肌肉表面来自 Z-Anatomy，绑定到同一套骨段，随动作一起变形。</p>
      </header>
      <div id="unified-stage" class="unified-stage" role="group" aria-label="可旋转、缩放的 OpenSim 全身模型">
        <div class="unified-overlay"><strong id="unified-status">正在加载 OpenSim 全身模型…</strong><span>拖动空白处旋转 · 滚轮或双指缩放 · 触摸可操作</span></div>
      </div>
      <div class="unified-controls">
        <div class="unified-tabs" role="group" aria-label="模型动作">
          <button type="button" data-mode="neutral" aria-pressed="true">静止</button>
          <button type="button" data-mode="squat" aria-pressed="false">徒手深蹲</button>
          <button type="button" data-mode="bench" aria-pressed="false">卧推</button>
          <button type="button" data-mode="press" aria-pressed="false">实力举</button>
          <button type="button" data-mode="custom" aria-pressed="false">自定义姿态</button>
          <button type="button" id="unified-play" class="unified-button">▶ 播放</button>
        </div>
        <div class="unified-progress"><input id="unified-timeline" type="range" min="0" max="100" value="0" disabled aria-label="动作相位" /><output id="unified-phase">静止</output></div>
        <div id="unified-custom" class="unified-custom" hidden>
          <p>拖动关节滑块或画面中的手部圆点。松开圆点后由同一份 OpenSim 模型求解姿态与 520 条肌肉肌腱路径。左右两侧同步。</p>
          <div class="unified-sliders">
            <label>躯干前后倾 <input data-joint="pelvis_tilt" type="range" min="-75" max="75" value="0" /><output>0°</output></label>
            <label>髋屈曲 <input data-joint="hip_flexion" type="range" min="-25" max="114" value="0" /><output>0°</output></label>
            <label>膝屈曲 <input data-joint="knee_angle" type="range" min="0" max="135" value="0" /><output>0°</output></label>
            <label>踝角 <input data-joint="ankle_angle" type="range" min="-34" max="28" value="0" /><output>0°</output></label>
            <label>抬臂平面 <input data-joint="elv_angle" type="range" min="-85" max="85" value="0" /><output>0°</output></label>
            <label>肩升举 <input data-joint="shoulder_elv" type="range" min="0" max="174" value="0" /><output>0°</output></label>
            <label>肘屈曲 <input data-joint="elbow_flex" type="range" min="0" max="140" value="0" /><output>0°</output></label>
          </div>
          <label class="check"><input id="unified-plant-feet" type="checkbox" checked /> 保持脚跟着地</label>
          <span id="unified-live-status">等待 OpenSim 实时姿态服务…</span>
        </div>
      </div>
    </main>
    <aside class="unified-side">
      <h2>模型层</h2>
      <p>动作骨架与肌肉肌腱长度来自 <code>cyclistFullBodyMuscle.osim</code>；Z-Anatomy 精细肌肉表面经骨骼配准后绑定到该 OpenSim 骨架。所有姿态使用同一套绑定表面。</p>
      <label class="check"><input id="unified-surfaces" type="checkbox" checked /> 显示精细肌肉表面</label>
      <label class="check"><input id="unified-bones" type="checkbox" /> 显示 OpenSim 骨网格</label>
      <label class="check"><input id="unified-muscles" type="checkbox" /> 显示肌肉肌腱路径</label>
      <label for="unified-group">查看区域</label>
      <select id="unified-group"><option value="all">全身 · 520 条</option><option value="leg">双腿 · 80 条</option><option value="trunk">躯干 · 约 360 条</option><option value="upper">肩臂 · 约 80 条</option></select>
      <label for="unified-surface">查看主要肌肉</label>
      <select id="unified-surface" aria-label="选择精细肌肉表面"></select>
      <label for="unified-muscle">选中一条路径</label>
      <select id="unified-muscle"></select>
      <div id="unified-readout" class="unified-card" aria-live="polite"></div>
      <div id="unified-joints" class="unified-card" aria-live="polite"></div>
      <div class="unified-legend"><span><i style="background:#f36d72"></i>肌腱路径变长</span><span><i style="background:#69c8dc"></i>肌腱路径变短</span><span><i style="background:#b77f83"></i>接近静止长度</span></div>
      <p class="unified-caveat">表面变形是两端骨段的线性蒙皮，用于观察位置与外形；颜色表示对应 OpenSim 肌肉肌腱整条路径的长度变化，不等于激活或力量。动作轨迹是教学预设，尚未计算关节反力或发力点。</p>
      <p class="unified-caveat">源 OpenSim 模型仍缺 ${geometryAudit.missing.length} 个骨网格引用；另有 ${geometryAudit.excluded.length} 节胸椎因源几何错位被排除。Z-Anatomy 表面与 OpenSim 骨网格并非同源解剖，配准误差见项目文档。</p>
      <p><a href="https://github.com/ross-wilkinson/opensim-model-fullBodyMuscleActuated" target="_blank" rel="noreferrer">OpenSim 模型 ↗</a> · <a href="https://github.com/Z-Anatomy/Models-of-human-anatomy" target="_blank" rel="noreferrer">Z-Anatomy ↗</a> · <a href="/models/NOTICE-z-anatomy.txt">表面许可</a></p>
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
const surfaceSelect = element<HTMLSelectElement>('#unified-surface');
const muscleSelect = element<HTMLSelectElement>('#unified-muscle');
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setClearColor('#091723');
stage.prepend(renderer.domElement);
const scene = new THREE.Scene();
scene.add(new THREE.AmbientLight('#d7e5ef', 0.85));
const light = new THREE.DirectionalLight('#ffffff', 2.8);
light.position.set(2, 4, 3);
scene.add(light);
const rimLight = new THREE.DirectionalLight('#8bd8eb', 1.25);
rimLight.position.set(-3, 2, -2);
scene.add(rimLight);
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
    press: [3.65, 1.28, 0.35],
    custom: [2.8, 1.2, 0.35],
  };
  camera.position.set(...positions[nextMode]);
  orbit.target.set(0, nextMode === 'squat' ? 0.79 : nextMode === 'press' ? 1.01 : 0.91, 0);
  orbit.update();
}

const bonesGroup = new THREE.Group();
const essentialsGroup = new THREE.Group();
const musclesGroup = new THREE.Group();
const surfacesGroup = new THREE.Group();
scene.add(bonesGroup, essentialsGroup, musclesGroup, surfacesGroup);
const handleGroup = new THREE.Group();
scene.add(handleGroup);
const handHandles = new Map<string, THREE.Mesh>();
for (const body of ['hand_r', 'hand_l']) {
  const handle = new THREE.Mesh(new THREE.SphereGeometry(0.043, 16, 12),
    new THREE.MeshStandardMaterial({ color: '#74e4e5', emissive: '#128b9c',
      emissiveIntensity: 0.7, roughness: 0.3, depthTest: false }));
  handle.name = body;
  handle.renderOrder = 100;
  handHandles.set(body, handle);
  handleGroup.add(handle);
}
const bench = new THREE.Group();
const benchMaterial = new THREE.MeshStandardMaterial({ color: '#405b69', roughness: 0.72 });
const benchPad = new THREE.Mesh(new THREE.BoxGeometry(1.15, 0.09, 0.37), benchMaterial);
benchPad.position.set(0.13, 0.48, 0);
bench.add(benchPad);
for (const x of [-0.31, 0.47]) {
  const leg = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.44, 0.04),
    new THREE.MeshStandardMaterial({ color: '#697984', metalness: 0.35, roughness: 0.45 }));
  leg.position.set(x, 0.23, 0);
  bench.add(leg);
}
scene.add(bench);
const bar = new THREE.Group();
const steel = new THREE.MeshStandardMaterial({ color: '#c5d3d9', metalness: 0.68, roughness: 0.28 });
const plateMaterial = new THREE.MeshStandardMaterial({ color: '#2b4351', metalness: 0.45, roughness: 0.4 });
const shaft = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 1.35, 12), steel);
shaft.rotation.x = Math.PI / 2;
bar.add(shaft);
for (const z of [-0.48, 0.48]) {
  const plate = new THREE.Mesh(new THREE.CylinderGeometry(0.105, 0.105, 0.045, 24), plateMaterial);
  plate.rotation.x = Math.PI / 2;
  plate.position.z = z;
  bar.add(plate);
}
scene.add(bar);
let data: Reference | undefined;
let customFrame: ModelFrame | undefined;
let mode: Mode = 'neutral';
let group: Group = 'all';
let phase = 0;
let selected = 0;
let playing = false;
let lastFrameTime = performance.now();
const bodyMeshes = new Map<string, THREE.Mesh[]>();
const muscleLines: THREE.Line[] = [];
const surfaceMeshes: Array<{ mesh: THREE.SkinnedMesh; modelIndices: number[] }> = [];
let skinBones: THREE.Bone[] = [];
let skinSkeleton: THREE.Skeleton | undefined;
const highlight = new THREE.Mesh(new THREE.BufferGeometry(),
  new THREE.MeshStandardMaterial({ color: '#ffe0a2', emissive: '#a7551a', roughness: 0.55 }));
musclesGroup.add(highlight);

function currentFrame(): ModelFrame | undefined {
  if (!data) return undefined;
  if (mode === 'custom') return customFrame ?? data.neutral;
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
  const anatomical = surfaceMeshes.find(item => item.modelIndices.includes(selected))?.mesh.name;
  element('#unified-readout').innerHTML = `<strong>${name}</strong>${anatomical ? `<span>对应表面：${anatomical}</span>` : ''}<span>当前 OpenSim 肌肉肌腱长度 ${(current * 100).toFixed(1)} cm</span><span>静止长度 ${(baseline * 100).toFixed(1)} cm</span><span class="${change > 2.5 ? 'longer' : change < -2.5 ? 'shorter' : ''}">相对静止 ${change >= 0 ? '+' : ''}${change.toFixed(1)}%</span>`;
  const labels: Record<Mode, Array<[string, string]>> = {
    neutral: [],
    squat: [['hip_flexion_r', '右髋屈曲'], ['knee_angle_r', '右膝屈曲'], ['ankle_angle_r', '右踝角']],
    bench: [['shoulder_elv_r', '右肩升举参数'], ['elbow_flex_r', '右肘屈曲']],
    press: [['shoulder_elv_r', '右肩升举参数'], ['elbow_flex_r', '右肘屈曲']],
    custom: [['hip_flexion_r', '右髋屈曲'], ['knee_angle_r', '右膝屈曲'],
      ['shoulder_elv_r', '右肩升举'], ['elbow_flex_r', '右肘屈曲']],
  };
  element('#unified-joints').innerHTML = mode === 'neutral'
    ? '<strong>关节预设</strong><span>静止参考姿态</span>'
    : `<strong>${mode === 'custom' ? '自定义关节姿态' : `关节预设 · ${phase}%`}</strong>${labels[mode].map(([key, label]) =>
      `<span>${label} ${((frame.coordinates[key] ?? 0) * 180 / Math.PI).toFixed(1)}°</span>`).join('')}<small>${mode === 'custom' ? 'OpenSim 实时重新计算；未求解运动力' : '人为设定的角度，不是动作测量结果'}</small>`;
  stage.dataset.model = data.model;
  stage.dataset.mode = mode;
  stage.dataset.phase = String(phase);
  stage.dataset.muscles = String(data.muscleNames.length);
  stage.dataset.bodies = String(data.bodyNames.length);
  stage.dataset.surfaceMeshes = String(surfaceMeshes.length);
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
    if (skinBones[index]) {
      skinBones[index].matrix.copy(matrix);
      skinBones[index].matrixWorldNeedsUpdate = true;
    }
  });
  scene.updateMatrixWorld(true);
  skinSkeleton?.update();
  handleGroup.visible = mode === 'custom';
  for (const [name, handle] of handHandles) {
    const point = frame.bodies[data.bodyNames.indexOf(name)].p;
    handle.position.set(...point);
  }
  bench.visible = mode === 'bench';
  bar.visible = mode === 'bench' || mode === 'press';
  if (bar.visible) {
    const right = frame.bodies[data.bodyNames.indexOf('hand_r')].p;
    const left = frame.bodies[data.bodyNames.indexOf('hand_l')].p;
    bar.position.set((right[0] + left[0]) / 2, (right[1] + left[1]) / 2 + 0.025, 0);
  }
  for (const { mesh, modelIndices } of surfaceMeshes) {
    const average = modelIndices.reduce((sum, index) =>
      sum + frame.lengthsM[index] / reference.neutral.lengthsM[index], 0) / modelIndices.length;
    const material = mesh.material as THREE.MeshStandardMaterial;
    material.color.set(colour(average));
    material.emissive.set(modelIndices.includes(selected) ? '#4e282e' : '#000000');
    material.emissiveIntensity = 0.55;
    mesh.visible = group === 'all' || modelIndices.some(index => groupOf(index) === group);
  }
  surfacesGroup.visible = element<HTMLInputElement>('#unified-surfaces').checked;
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
  element('#unified-phase').textContent = mode === 'neutral' ? '静止' : mode === 'custom' ? '实时' : `${phase}%`;
  element('#unified-status').textContent = `${data.model} · ${mode === 'neutral' ? '静止' : mode === 'custom' ? '自定义姿态' : `${phase}% ${mode}`} · 同一模型`;
  updateReadout(frame);
}

function syncMuscleOptions(): void {
  if (!data) return;
  const indices = data.muscleNames.map((_, index) => index)
    .filter(index => group === 'all' || groupOf(index) === group);
  if (!indices.includes(selected)) selected = indices[0];
  muscleSelect.innerHTML = indices.map(index =>
    `<option value="${index}"${index === selected ? ' selected' : ''}>${data?.muscleNames[index]}</option>`).join('');
  const surfaceIndex = surfaceMeshes.findIndex(item => item.modelIndices.includes(selected));
  if (surfaceIndex >= 0) surfaceSelect.value = String(surfaceIndex);
  updateFrame();
}

const customPanel = element<HTMLDivElement>('#unified-custom');
element('#unified-joints').after(customPanel);
const jointSliders = [...document.querySelectorAll<HTMLInputElement>('[data-joint]')];
let poseTimer: number | undefined;
let poseRequest = 0;
let poseBusy = false;
let posePending = false;
function requestCustomPose(): void {
  if (mode !== 'custom') return;
  if (poseTimer !== undefined) window.clearTimeout(poseTimer);
  poseTimer = window.setTimeout(async () => {
    if (poseBusy) {
      posePending = true;
      return;
    }
    poseBusy = true;
    const requestId = ++poseRequest;
    const controls = Object.fromEntries(jointSliders.map(input =>
      [input.dataset.joint!, Number(input.value) * Math.PI / 180]));
    element('#unified-live-status').textContent = 'OpenSim 正在计算姿态…';
    try {
      const response = await fetch('/api/pose', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ controls,
          plantFeet: element<HTMLInputElement>('#unified-plant-feet').checked }) });
      const result = await response.json() as { frame?: ModelFrame; error?: string };
      if (!response.ok || !result.frame) throw new Error(result.error ?? `HTTP ${response.status}`);
      if (requestId !== poseRequest || mode !== 'custom') return;
      customFrame = result.frame;
      element('#unified-live-status').textContent = '已由 OpenSim 实时重新计算';
      updateFrame();
    } catch (error) {
      if (requestId !== poseRequest || mode !== 'custom') return;
      element('#unified-live-status').textContent =
        `实时服务不可用：${error instanceof Error ? error.message : String(error)}。运行 live_pose_server.py 后刷新页面。`;
    } finally {
      poseBusy = false;
      if (posePending && mode === 'custom') {
        posePending = false;
        requestCustomPose();
      }
    }
  }, 130);
}
const pickRay = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let draggingHand: { handle: THREE.Mesh; plane: THREE.Plane } | undefined;
function setPointer(event: PointerEvent): void {
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.set((event.clientX - rect.left) / rect.width * 2 - 1,
    -(event.clientY - rect.top) / rect.height * 2 + 1);
  pickRay.setFromCamera(pointer, camera);
}
renderer.domElement.addEventListener('pointerdown', event => {
  if (mode !== 'custom') return;
  setPointer(event);
  const hit = pickRay.intersectObjects([...handHandles.values()], false)[0];
  if (!hit) return;
  const handle = hit.object as THREE.Mesh;
  const normal = new THREE.Vector3();
  camera.getWorldDirection(normal);
  draggingHand = { handle, plane: new THREE.Plane().setFromNormalAndCoplanarPoint(
    normal, handle.position) };
  orbit.enabled = false;
  renderer.domElement.setPointerCapture(event.pointerId);
  element('#unified-live-status').textContent = `拖动${handle.name === 'hand_r' ? '右' : '左'}手；松开后由 OpenSim 求解`;
});
renderer.domElement.addEventListener('pointermove', event => {
  if (!draggingHand) return;
  setPointer(event);
  pickRay.ray.intersectPlane(draggingHand.plane, draggingHand.handle.position);
});
renderer.domElement.addEventListener('pointerup', event => {
  if (!draggingHand) return;
  const { handle } = draggingHand;
  const target = handle.position.toArray();
  draggingHand = undefined;
  orbit.enabled = true;
  if (renderer.domElement.hasPointerCapture(event.pointerId))
    renderer.domElement.releasePointerCapture(event.pointerId);
  if (poseTimer !== undefined) window.clearTimeout(poseTimer);
  posePending = false;
  const requestId = ++poseRequest;
  const controls = Object.fromEntries(jointSliders.map(input =>
    [input.dataset.joint!, Number(input.value) * Math.PI / 180]));
  element('#unified-live-status').textContent = 'OpenSim 正在拟合手部目标…';
  void (async () => {
    try {
      const response = await fetch('/api/ik', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ controls,
          plantFeet: element<HTMLInputElement>('#unified-plant-feet').checked,
          body: handle.name, target }) });
      const result = await response.json() as { frame?: ModelFrame;
        solvedControls?: Record<string, number>; targetErrorM?: number; error?: string };
      if (!response.ok || !result.frame || !result.solvedControls)
        throw new Error(result.error ?? `HTTP ${response.status}`);
      if (requestId !== poseRequest || mode !== 'custom') return;
      customFrame = result.frame;
      for (const input of jointSliders) {
        const solved = result.solvedControls[input.dataset.joint!];
        if (solved === undefined) continue;
        input.value = String(Math.round(solved * 180 / Math.PI));
        if (input.nextElementSibling) input.nextElementSibling.textContent = `${input.value}°`;
      }
      element('#unified-live-status').textContent = (result.targetErrorM ?? 0) < 0.05
        ? '手部目标已由 OpenSim 求解'
        : `目标超出可达范围；最近姿态距目标 ${((result.targetErrorM ?? 0) * 100).toFixed(1)} cm`;
      updateFrame();
    } catch (error) {
      element('#unified-live-status').textContent =
        `手部求解失败：${error instanceof Error ? error.message : String(error)}`;
      updateFrame();
    }
  })();
});
renderer.domElement.addEventListener('pointercancel', () => {
  draggingHand = undefined;
  orbit.enabled = true;
  updateFrame();
});
for (const input of jointSliders) {
  input.addEventListener('input', () => {
    const output = input.nextElementSibling;
    if (output) output.textContent = `${input.value}°`;
    requestCustomPose();
  });
}
element<HTMLInputElement>('#unified-plant-feet').addEventListener('change', requestCustomPose);

for (const button of document.querySelectorAll<HTMLButtonElement>('[data-mode]')) {
  button.addEventListener('click', () => {
    mode = button.dataset.mode as Mode;
    setDefaultCamera(mode);
    if (data) {
      const defaultMuscle: Record<Mode, string> = {
        neutral: 'glmax1_r', squat: 'glmax1_r', bench: 'PECM1', press: 'DELT2', custom: 'glmax1_r',
      };
      const index = data.muscleNames.indexOf(defaultMuscle[mode]);
      if (index >= 0) selected = index;
      group = 'all';
      groupSelect.value = 'all';
      syncMuscleOptions();
    }
    phase = 0;
    timeline.value = '0';
    timeline.disabled = mode === 'neutral' || mode === 'custom';
    playing = false;
    play.textContent = '▶ 播放';
    play.disabled = mode === 'custom';
    customPanel.hidden = mode !== 'custom';
    if (mode === 'custom') requestCustomPose();
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
  if (mode === 'custom') return;
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
surfaceSelect.addEventListener('change', () => {
  const chosen = surfaceMeshes[Number(surfaceSelect.value)];
  if (!chosen) return;
  selected = chosen.modelIndices[0];
  group = 'all';
  groupSelect.value = 'all';
  syncMuscleOptions();
});
element<HTMLInputElement>('#unified-bones').addEventListener('change', updateFrame);
element<HTMLInputElement>('#unified-muscles').addEventListener('change', updateFrame);
element<HTMLInputElement>('#unified-surfaces').addEventListener('change', updateFrame);

new ResizeObserver(() => {
  const rect = stage.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  camera.aspect = rect.width / rect.height;
  camera.updateProjectionMatrix();
  renderer.setSize(rect.width, rect.height, false);
}).observe(stage);

function render(now: number): void {
  if (playing && data && mode !== 'neutral' && mode !== 'custom') {
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
  if (mode === 'custom') {
    const handle = handHandles.get('hand_r');
    if (handle) {
      const screen = handle.position.clone().project(camera);
      const rect = renderer.domElement.getBoundingClientRect();
      stage.dataset.handRightScreen = `${rect.left + (screen.x + 1) * rect.width / 2},${rect.top + (1 - screen.y) * rect.height / 2}`;
    }
  }
  renderer.render(scene, camera);
  requestAnimationFrame(render);
}
requestAnimationFrame(render);

async function load(): Promise<void> {
  const [response, gltf, surfaceGltf, skinResponse, weightResponse] = await Promise.all([
    fetch('/data/unified_opensim_reference.json'),
    new GLTFLoader().loadAsync('/models/unified_opensim_skeleton.glb'),
    new GLTFLoader().loadAsync('/models/unified_muscle_surfaces.glb'),
    fetch('/data/unified_muscle_skin.json'),
    fetch('/data/unified_muscle_weights.bin'),
  ]);
  if (!response.ok) throw new Error(`OpenSim frame data HTTP ${response.status}`);
  if (!skinResponse.ok || !weightResponse.ok) throw new Error('精细肌肉绑定数据缺失');
  data = await response.json() as Reference;
  const skin = await skinResponse.json() as MuscleSkin;
  const weights = new Uint8Array(await weightResponse.arrayBuffer());
  if (data.bodyNames.length !== 80 || data.muscleNames.length !== 520
    || data.actions.squat.length !== 101 || data.actions.bench.length !== 101
    || data.actions.press.length !== 101) throw new Error('OpenSim export is incomplete');
  const sourceBodyByNode = new Map(geometryAudit.present.map(entry =>
    [THREE.PropertyBinding.sanitizeNodeName(entry.node), entry.body]));
  gltf.scene.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return;
    const body = sourceBodyByNode.get(object.name);
    if (!body) return;
    const essential = /^(head_neck|talus_[rl]|calcn_[rl]|toes_[rl]|hand_[rl])$/.test(body);
    const mesh = new THREE.Mesh(object.geometry, new THREE.MeshStandardMaterial({
      color: essential ? '#d2c7b0' : '#dfd9c7', side: THREE.DoubleSide, roughness: 0.7,
    }));
    mesh.name = object.name;
    mesh.matrixAutoUpdate = false;
    (essential ? essentialsGroup : bonesGroup).add(mesh);
    const entries = bodyMeshes.get(body) ?? [];
    entries.push(mesh);
    bodyMeshes.set(body, entries);
  });
  if (bodyMeshes.size < 20) throw new Error(`only ${bodyMeshes.size} OpenSim bodies have source meshes; nodes: ${gltf.scene.children.slice(0, 5).map(child => child.name).join(', ')}`);
  skinBones = data.bodyNames.map((name, index) => {
    const bone = new THREE.Bone();
    bone.name = `opensim:${name}`;
    bone.matrixAutoUpdate = false;
    const { p, r } = data!.neutral.bodies[index];
    bone.matrix.set(r[0], r[1], r[2], p[0], r[3], r[4], r[5], p[1],
      r[6], r[7], r[8], p[2], 0, 0, 0, 1);
    scene.add(bone);
    return bone;
  });
  scene.updateMatrixWorld(true);
  const inverses = skinBones.map(bone => bone.matrixWorld.clone().invert());
  skinSkeleton = new THREE.Skeleton(skinBones, inverses);
  const skinByName = new Map(skin.meshes.map(entry =>
    [THREE.PropertyBinding.sanitizeNodeName(entry.name), entry]));
  surfaceGltf.scene.updateMatrixWorld(true);
  surfaceGltf.scene.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return;
    const entry = skinByName.get(object.name);
    if (!entry) return;
    const geometry = object.geometry.clone();
    geometry.applyMatrix4(object.matrixWorld);
    geometry.computeVertexNormals();
    const count = geometry.getAttribute('position').count;
    if (count !== entry.vertexCount) throw new Error(`${entry.name}: GLB 顶点数与绑定表不一致`);
    const indices = new Uint16Array(count * 4);
    const influences = new Float32Array(count * 4);
    for (let i = 0; i < count; i++) {
      const u = weights[entry.weightOffset + i] / 255;
      indices[i * 4] = entry.bodyIndices[0];
      indices[i * 4 + 1] = entry.bodyIndices[1];
      influences[i * 4] = 1 - u;
      influences[i * 4 + 1] = u;
    }
    geometry.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(indices, 4));
    geometry.setAttribute('skinWeight', new THREE.Float32BufferAttribute(influences, 4));
    const material = new THREE.MeshStandardMaterial({ color: '#b77f83',
      roughness: 0.57, metalness: 0, side: THREE.DoubleSide });
    const mesh = new THREE.SkinnedMesh(geometry, material);
    mesh.name = entry.name;
    mesh.frustumCulled = false;
    mesh.bindMode = 'detached';
    mesh.bind(skinSkeleton!, new THREE.Matrix4());
    surfacesGroup.add(mesh);
    surfaceMeshes.push({ mesh, modelIndices: entry.modelMuscles.map(name => data!.muscleNames.indexOf(name)) });
  });
  if (surfaceMeshes.length !== skin.meshes.length) throw new Error(`仅加载 ${surfaceMeshes.length}/${skin.meshes.length} 个精细肌肉表面`);
  surfaceSelect.innerHTML = surfaceMeshes.map((item, index) =>
    `<option value="${index}">${item.mesh.name.replace(/\.r$/, ' · 右').replace(/\.l$/, ' · 左')}</option>`).join('');
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
