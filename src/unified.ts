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
type PoseBasis = { model: string; bodyNames: string[]; muscleNames: string[];
  controls: Record<string, { angles: number[]; frames: Array<Pick<ModelFrame, 'bodies' | 'lengthsM'>> }> };
type MuscleSkin = { meshes: Array<{ name: string; modelMuscles: string[]; bodyIndices: [number, number, number]; weightOffset: number; vertexCount: number; axis: [number, number, number]; center: [number, number, number] }> };
type AnatomyBones = { bones: Array<{ name: string; bodyIndex: number }> };
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
          <button type="button" data-mode="bench" aria-pressed="false" disabled title="现有 OpenSim 肩肘几何尚不能构成合格卧推">卧推 · 待重建</button>
          <button type="button" data-mode="press" aria-pressed="false">实力举</button>
          <button type="button" data-mode="custom" aria-pressed="false">自定义姿态</button>
          <button type="button" id="unified-play" class="unified-button">▶ 播放</button>
        </div>
        <p class="unified-exercise-warning">卧推预设已暂停：当前全身 OpenSim 模型无法同时满足平躺、胸上方握杆与前臂在杠铃下方的几何条件。原轨迹保留作内部排查，不用于动作教学。</p>
        <div class="unified-progress"><input id="unified-timeline" type="range" min="0" max="100" value="0" disabled aria-label="动作相位" /><output id="unified-phase">静止</output></div>
        <div id="unified-custom" class="unified-custom" hidden>
          <p>拖动关节滑块或画面中的手、脚圆点。松开圆点后由同一份 OpenSim 模型求解姿态与 520 条肌肉肌腱路径。拖动单侧不会强制另一侧同步。</p>
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
      <label class="check"><input id="unified-bones" type="checkbox" checked /> 显示透视骨骼（同一 OpenSim 骨架）</label>
      <label class="check"><input id="unified-muscles" type="checkbox" /> 显示肌肉肌腱路径</label>
      <label class="check"><input id="unified-focus" type="checkbox" /> 仅突出变化最大的肌束</label>
      <label for="unified-group">查看区域</label>
      <select id="unified-group"><option value="all">全身 · 520 条</option><option value="leg">双腿 · 80 条</option><option value="trunk">躯干 · 约 360 条</option><option value="upper">肩臂 · 约 80 条</option></select>
      <label for="unified-surface">查看主要肌肉</label>
      <select id="unified-surface" aria-label="选择精细肌肉表面"></select>
      <label for="unified-muscle">选中一条路径</label>
      <select id="unified-muscle"></select>
      <section id="unified-major" class="unified-card unified-major" aria-live="polite"></section>
      <div id="unified-readout" class="unified-card" aria-live="polite"></div>
      <div id="unified-joints" class="unified-card" aria-live="polite"></div>
      <div class="unified-legend"><span><i style="background:#fa3658"></i>深红 · 变长较多</span><span><i style="background:#bc8089"></i>浅色 · 变化较小</span><span><i style="background:#24afd7"></i>深蓝 · 变短较多</span></div>
      <p class="unified-caveat">颜色和百分比来自 OpenSim 整条肌肉肌腱路径的几何长度：前半程比动作起点，回程比折返点；自定义模式比静止姿态。路径变短只表示收缩方向，不能直接等同肌纤维收缩、激活或发力。肌腹鼓起仍是外观示意，不随回程比较基准重置。</p>
      <p class="unified-caveat">源 OpenSim 模型缺 ${geometryAudit.missing.length} 个骨网格引用；骨骼透视层补用 Z-Anatomy 骨表面，所有骨段仍由同一 OpenSim 模型驱动。解剖配准误差见项目文档。</p>
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
const dragHandles = new Map<string, THREE.Mesh>();
for (const body of ['hand_r', 'hand_l', 'calcn_r', 'calcn_l']) {
  const isHand = body.startsWith('hand');
  const handle = new THREE.Mesh(new THREE.SphereGeometry(0.043, 16, 12),
    new THREE.MeshStandardMaterial({ color: isHand ? '#74e4e5' : '#f8ce80', emissive: isHand ? '#128b9c' : '#9b6c20',
      emissiveIntensity: 0.7, roughness: 0.3, depthTest: false }));
  handle.name = body;
  handle.renderOrder = 100;
  dragHandles.set(body, handle);
  handleGroup.add(handle);
}
const bench = new THREE.Group();
const benchMaterial = new THREE.MeshStandardMaterial({ color: '#405b69', roughness: 0.72 });
const benchPad = new THREE.Mesh(new THREE.BoxGeometry(1.15, 0.09, 0.37), benchMaterial);
benchPad.position.set(0.13, 0.69, 0);
bench.add(benchPad);
for (const x of [-0.31, 0.47]) {
  const leg = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.66, 0.04),
    new THREE.MeshStandardMaterial({ color: '#697984', metalness: 0.35, roughness: 0.45 }));
  leg.position.set(x, 0.34, 0);
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
let poseBasis: PoseBasis | undefined;
let customFrame: ModelFrame | undefined;
let customPreviewActive = false;
let mode: Mode = 'neutral';
let group: Group = 'all';
let phase = 0;
let selected = 0;
let playing = false;
let lastFrameTime = performance.now();
const bodyMeshes = new Map<string, THREE.Mesh[]>();
const anatomyBoneMeshes: Array<{ mesh: THREE.Mesh; bodyIndex: number; inverseNeutral: THREE.Matrix4 }> = [];
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
  const neutral = [185, 140, 147];
  const end = ratio >= 1 ? [250, 54, 88] : [36, 175, 215];
  const strength = Math.pow(Math.min(1, Math.abs(ratio - 1) / 0.2), 0.7);
  return `#${neutral.map((value, index) =>
    Math.round(value + (end[index] - value) * strength).toString(16).padStart(2, '0')).join('')}`;
}

function actionStartFrame(): ModelFrame {
  if (!data) throw new Error('OpenSim data is not loaded');
  return mode === 'neutral' || mode === 'custom' ? data.neutral : data.actions[mode][0];
}

function comparisonFrame(): ModelFrame {
  if (!data) throw new Error('OpenSim data is not loaded');
  return mode === 'neutral' || mode === 'custom' || phase <= 50
    ? actionStartFrame() : data.actions[mode][50];
}

function comparisonLabel(): string {
  return mode === 'neutral' || mode === 'custom' ? '静止姿态'
    : phase <= 50 ? '动作起点' : '折返点';
}

const anatomyLabels: Record<string, string> = {
  'Gluteus maximus': '臀大肌', 'Gluteus medius': '臀中肌',
  'Vastus intermedius': '股中间肌', 'Vastus lateralis': '股外侧肌',
  'Vastus medialis': '股内侧肌', 'Rectus femoris': '股直肌',
  'Semimembranosus': '半膜肌', 'Semitendinosus': '半腱肌',
  'Lateral head of gastrocnemius': '腓肠肌外侧头',
  'Medial head of gastrocnemius': '腓肠肌内侧头',
  'Soleus': '比目鱼肌', 'Tibialis anterior': '胫骨前肌',
  'Brachialis': '肱肌', 'Brachioradialis': '肱桡肌',
  'Long head of biceps brachii': '肱二头肌长头',
  'Short head of biceps brachii': '肱二头肌短头',
  'Long head of triceps brachii': '肱三头肌长头',
  'Lateral head of triceps brachii': '肱三头肌外侧头',
  'Medial head of triceps brachii': '肱三头肌内侧头',
  'Clavicular head of pectoralis major': '胸大肌锁骨部',
  'Sternocostal head of pectoralis major': '胸大肌胸肋部',
  '(Abdominal part of pectoralis major muscle)': '胸大肌腹部',
  'Clavicular part of deltoid': '三角肌前束',
  'Acromial part of deltoid': '三角肌中束',
  'Scapular spinal part of deltoid': '三角肌后束',
  'Latissimus dorsi': '背阔肌',
  'Ascending part of trapezius': '斜方肌下部',
  'Transverse part of trapezius': '斜方肌中部',
  'Descending part of trapezius': '斜方肌上部',
  'Rhomboid major': '大菱形肌', 'Serratus anterior': '前锯肌',
  'Rectus abdominis': '腹直肌', 'External abdominal oblique': '腹外斜肌',
  'Longissimus thoracis': '胸最长肌',
};

function updateMajorChanges(frame: ModelFrame, baseline: ModelFrame): Set<number> {
  if (!data) return new Set();
  const panel = element<HTMLElement>('#unified-major');
  if (mode === 'neutral') {
    panel.innerHTML = '<strong>主要肌群几何变化</strong><span>选择预设动作，或拖动自定义姿态，查看肌肉肌腱路径的变长与变短。</span>';
    delete panel.dataset.longer;
    delete panel.dataset.shorter;
    delete panel.dataset.reference;
    return new Set();
  }
  const candidates = new Map<string, { changes: number[]; indices: number[] }>();
  for (const [surfaceIndex, { mesh, modelIndices }] of surfaceMeshes.entries()) {
    const name = mesh.name.replace(/\.[rl]$/, '').replace(/ muscle$/, '');
    const valid = modelIndices.filter(index => index >= 0 && baseline.lengthsM[index] > 0);
    if (!valid.length) continue;
    const change = valid.reduce((sum, index) =>
      sum + 100 * (frame.lengthsM[index] / baseline.lengthsM[index] - 1), 0) / valid.length;
    const side = mode === 'custom' ? (mesh.name.endsWith('.l') ? ' · 左' : ' · 右') : '';
    const key = name + side;
    const item = candidates.get(key) ?? { changes: [], indices: [] };
    item.changes.push(change);
    item.indices.push(surfaceIndex);
    candidates.set(key, item);
  }
  const changes = [...candidates].map(([name, item]) => ({
    label: (anatomyLabels[name.replace(/ · [左右]$/, '')] ?? name) +
      (mode === 'custom' ? name.slice(-4) : ''),
    change: item.changes.reduce((sum, value) => sum + value, 0) / item.changes.length,
    surfaceIndex: item.indices[0], surfaceIndices: item.indices,
  }));
  const threshold = 1;
  const long = changes.filter(item => item.change >= threshold)
    .sort((a, b) => b.change - a.change);
  const short = changes.filter(item => item.change <= -threshold)
    .sort((a, b) => a.change - b.change);
  const buttons = (items: typeof changes, kind: 'longer' | 'shorter') =>
    items.length ? items.map(item => `<button type="button" class="major-row ${kind}" data-surface-index="${item.surfaceIndex}" aria-label="查看${item.label}"><span>${item.label}</span><b>${item.change >= 0 ? '+' : ''}${item.change.toFixed(1)}%</b></button>`).join('')
      : '<span class="major-empty">无明显变化（阈值 1%）</span>';
  const phaseLabel = mode === 'custom' ? '静止 → 自定义姿态'
    : phase <= 50 ? `动作起点 → ${phase}%` : `折返点 → ${phase}%`;
  const chest = mode === 'bench' ? changes.filter(item => item.label.startsWith('胸大肌')) : [];
  const chestMax = chest.length ? Math.max(...chest.map(item => Math.abs(item.change))) : 0;
  const scroll = [...panel.querySelectorAll<HTMLElement>('.major-list')].map(list => list.scrollTop);
  panel.innerHTML = `<strong>肌肉路径变化</strong><small>${phaseLabel} · ${mode === 'custom' ? '左右分别显示' : '双侧平均'} · 点击肌肉定位</small><div class="major-columns"><div><h3>变长 ${long.length}</h3><div class="major-list">${buttons(long, 'longer')}</div></div><div><h3>变短 ${short.length}</h3><div class="major-list">${buttons(short, 'shorter')}</div></div></div>${mode === 'bench' && chestMax < threshold && phase > 0 ? '<small>本模型此卧推轨迹的胸大肌路径变化很小；不能据此判断胸大肌不参与发力。</small>' : ''}<small>全部 ${changes.length} 块解剖肌束按几何长度着色；1% 以下只显示颜色深浅，不推断激活或力量。</small>`;
  [...panel.querySelectorAll<HTMLElement>('.major-list')].forEach((list, index) => {
    list.scrollTop = scroll[index] ?? 0;
  });
  panel.dataset.longer = long.map(item => item.label).join(',');
  panel.dataset.shorter = short.map(item => item.label).join(',');
  panel.dataset.reference = comparisonLabel();
  return new Set([...long.slice(0, 6), ...short.slice(0, 6)]
    .flatMap(item => item.surfaceIndices));
}

function updateReadout(frame: ModelFrame): void {
  if (!data) return;
  const name = data.muscleNames[selected];
  const current = frame.lengthsM[selected];
  const baseline = comparisonFrame().lengthsM[selected];
  const neutral = data.neutral.lengthsM[selected];
  const ratio = current / baseline;
  const change = (ratio - 1) * 100;
  const anatomical = surfaceMeshes.find(item => item.modelIndices.includes(selected))?.mesh.name;
  element('#unified-readout').innerHTML = `<strong>${name}</strong>${anatomical ? `<span>对应表面：${anatomical}</span>` : ''}<span>当前 OpenSim 肌肉肌腱路径长度 ${(current * 100).toFixed(1)} cm</span><span>${comparisonLabel()}长度 ${(baseline * 100).toFixed(1)} cm</span><span class="${change > 2.5 ? 'longer' : change < -2.5 ? 'shorter' : ''}">相对${comparisonLabel()} ${change >= 0 ? '+' : ''}${change.toFixed(1)}%</span>${mode === 'neutral' || mode === 'custom' ? '' : `<small>站立静止参考长度 ${(neutral * 100).toFixed(1)} cm</small>`}`;
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
  stage.dataset.anatomyBones = String(anatomyBoneMeshes.length);
  stage.dataset.selectedLengthM = String(current);
}

function updateFrame(): void {
  const frame = currentFrame();
  if (!data || !frame) return;
  const baselineFrame = comparisonFrame();
  const shapeFrame = actionStartFrame();
  const majorIndices = updateMajorChanges(frame, baselineFrame);
  const focusMajor = element<HTMLInputElement>('#unified-focus').checked && majorIndices.size > 0;
  const majorModelIndices = new Set([...majorIndices].flatMap(index => surfaceMeshes[index].modelIndices));
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
  for (const { mesh, bodyIndex, inverseNeutral } of anatomyBoneMeshes) {
    const current = frame.bodies[bodyIndex];
    matrix.set(
      current.r[0], current.r[1], current.r[2], current.p[0],
      current.r[3], current.r[4], current.r[5], current.p[1],
      current.r[6], current.r[7], current.r[8], current.p[2], 0, 0, 0, 1);
    mesh.matrix.multiplyMatrices(matrix, inverseNeutral);
    mesh.matrixWorldNeedsUpdate = true;
  }
  scene.updateMatrixWorld(true);
  skinSkeleton?.update();
  handleGroup.visible = mode === 'custom';
  for (const [name, handle] of dragHandles) {
    const point = frame.bodies[data.bodyNames.indexOf(name)].p;
    handle.position.set(...point);
  }
  bench.visible = mode === 'bench';
  bar.visible = mode === 'bench' || mode === 'press';
  if (bar.visible) {
    const right = frame.bodies[data.bodyNames.indexOf('hand_r')].p;
    const left = frame.bodies[data.bodyNames.indexOf('hand_l')].p;
    bar.position.set((right[0] + left[0]) / 2,
      (right[1] + left[1]) / 2 + 0.02, 0);
  }
  for (const [surfaceIndex, { mesh, modelIndices }] of surfaceMeshes.entries()) {
    const average = modelIndices.reduce((sum, index) =>
      sum + frame.lengthsM[index] / baselineFrame.lengthsM[index], 0) / modelIndices.length;
    const material = mesh.material as THREE.MeshStandardMaterial;
    material.color.set(focusMajor && !majorIndices.has(surfaceIndex) && !modelIndices.includes(selected)
      ? '#715a62' : colour(average));
    material.emissive.set(modelIndices.includes(selected) ? '#4e282e' : '#000000');
    material.emissiveIntensity = 0.55;
    const shapeRatio = modelIndices.reduce((sum, index) =>
      sum + frame.lengthsM[index] / shapeFrame.lengthsM[index], 0) / modelIndices.length;
    mesh.morphTargetInfluences![0] = Math.min(1, Math.max(0, (1 - shapeRatio) * 4));
    mesh.visible = group === 'all' || modelIndices.some(index => groupOf(index) === group);
  }
  surfacesGroup.visible = element<HTMLInputElement>('#unified-surfaces').checked;
  const showPaths = element<HTMLInputElement>('#unified-muscles').checked && !customPreviewActive;
  if (showPaths) {
    frame.paths.forEach((path, index) => {
      const line = muscleLines[index];
      const positions = line.geometry.getAttribute('position') as THREE.BufferAttribute;
      for (let i = 0; i < path.length; i++) positions.setXYZ(i, ...path[i]);
      line.geometry.setDrawRange(0, path.length);
      positions.needsUpdate = true;
      line.geometry.computeBoundingSphere();
      const ratio = frame.lengthsM[index] / baselineFrame.lengthsM[index];
      (line.material as THREE.LineBasicMaterial).color.set(index === selected ? '#ffe0a2'
        : focusMajor && !majorModelIndices.has(index) ? '#45606d' : colour(ratio));
      line.visible = group === 'all' || groupOf(index) === group;
    });
    const path = frame.paths[selected];
    highlight.geometry.dispose();
    highlight.geometry = new THREE.TubeGeometry(
      new THREE.CatmullRomCurve3(path.map(point => new THREE.Vector3(...point))),
      Math.max(16, path.length * 5), 0.008, 6, false);
  } else {
    for (const line of muscleLines) line.visible = false;
  }
  highlight.visible = showPaths && (group === 'all' || groupOf(selected) === group);
  bonesGroup.visible = element<HTMLInputElement>('#unified-bones').checked;
  element('#unified-phase').textContent = mode === 'neutral' ? '静止' : mode === 'custom' ? '实时' : `${phase}%`;
  element('#unified-status').textContent = `${data.model} · ${mode === 'neutral' ? '静止' : mode === 'custom' ? '自定义姿态' : `${phase}% ${mode}`} · 同一模型`;
  stage.dataset.preview = String(mode === 'custom' && customPreviewActive);
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
function matrixFromBody(body: BodyFrame): THREE.Matrix4 {
  const { p, r } = body;
  return new THREE.Matrix4().set(r[0], r[1], r[2], p[0], r[3], r[4], r[5], p[1],
    r[6], r[7], r[8], p[2], 0, 0, 0, 1);
}

function previewCustomPose(): ModelFrame | undefined {
  if (!data || !poseBasis) return undefined;
  const pelvisIndex = data.bodyNames.indexOf('pelvis');
  const heelIndices = [data.bodyNames.indexOf('calcn_r'), data.bodyNames.indexOf('calcn_l')];
  const samples = jointSliders.map(input => {
    const name = input.dataset.joint!;
    const source = poseBasis!.controls[name];
    if (!source) throw new Error(`Missing OpenSim pose sample for ${name}`);
    const angle = Number(input.value) * Math.PI / 180;
    let lower = 0;
    while (lower < source.angles.length - 2 && source.angles[lower + 1] < angle) lower++;
    const upper = lower + 1;
    const t = THREE.MathUtils.clamp((angle - source.angles[lower]) /
      (source.angles[upper] - source.angles[lower]), 0, 1);
    const from = source.frames[lower], to = source.frames[upper];
    const neutralPelvis = data!.neutral.bodies[pelvisIndex].p;
    const pelvisShift = new THREE.Vector3(...from.bodies[pelvisIndex].p)
      .lerp(new THREE.Vector3(...to.bodies[pelvisIndex].p), t)
      .sub(new THREE.Vector3(...neutralPelvis));
    return { name, angle, from, to, t, pelvisShift };
  });
  const bodies = data.bodyNames.map((_, bodyIndex) => {
    const base = matrixFromBody(data!.neutral.bodies[bodyIndex]);
    const inverse = base.clone().invert();
    const combined = base.clone();
    for (const sample of samples) {
      const from = matrixFromBody(sample.from.bodies[bodyIndex]);
      const to = matrixFromBody(sample.to.bodies[bodyIndex]);
      const fromPosition = new THREE.Vector3();
      const fromRotation = new THREE.Quaternion();
      const fromScale = new THREE.Vector3();
      const toPosition = new THREE.Vector3();
      const toRotation = new THREE.Quaternion();
      const toScale = new THREE.Vector3();
      from.decompose(fromPosition, fromRotation, fromScale);
      to.decompose(toPosition, toRotation, toScale);
      const interpolated = new THREE.Matrix4().compose(
        fromPosition.lerp(toPosition, sample.t).sub(sample.pelvisShift),
        fromRotation.slerp(toRotation, sample.t),
        new THREE.Vector3(1, 1, 1));
      combined.multiply(inverse.clone().multiply(interpolated));
    }
    const p = new THREE.Vector3().setFromMatrixPosition(combined);
    const e = combined.elements;
    return { p: [p.x, p.y, p.z] as [number, number, number],
      r: [e[0], e[4], e[8], e[1], e[5], e[9], e[2], e[6], e[10]] };
  });
  const lengthsM = data.neutral.lengthsM.map((neutral, muscleIndex) => {
    let logRatio = 0;
    for (const sample of samples) {
      const from = sample.from.lengthsM[muscleIndex];
      const to = sample.to.lengthsM[muscleIndex];
      const estimate = THREE.MathUtils.lerp(from, to, sample.t);
      logRatio += Math.log(estimate / neutral);
    }
    return neutral * Math.exp(logRatio);
  });
  if (element<HTMLInputElement>('#unified-plant-feet').checked) {
    const target = new THREE.Vector3();
    const actual = new THREE.Vector3();
    for (const index of heelIndices) {
      target.add(new THREE.Vector3(...data.neutral.bodies[index].p));
      actual.add(new THREE.Vector3(...bodies[index].p));
    }
    target.multiplyScalar(0.5);
    actual.multiplyScalar(0.5);
    const offset = target.sub(actual);
    for (const body of bodies) {
      body.p[0] += offset.x;
      body.p[1] += offset.y;
    }
  }
  const coordinates: Record<string, number> = {};
  for (const sample of samples) {
    if (sample.name === 'pelvis_tilt') coordinates.pelvis_tilt = sample.angle;
    else {
      coordinates[`${sample.name}_r`] = sample.angle;
      coordinates[`${sample.name}_l`] = sample.name === 'shoulder_elv'
        ? -sample.angle : sample.angle;
    }
  }
  return { bodies, lengthsM, coordinates, paths: [] };
}

let poseTimer: number | undefined;
let poseRequest = 0;
let poseBusy = false;
let posePending = false;
const individualCoordinates: Record<string, number> = {};
function requestCustomPose(): void {
  if (mode !== 'custom') return;
  const requestId = ++poseRequest;
  const preview = previewCustomPose();
  if (preview) {
    customFrame = preview;
    customPreviewActive = true;
    updateFrame();
    element('#unified-live-status').textContent = '即时预览：OpenSim 采样插值；完整路径正在精确重算…';
  }
  if (poseTimer !== undefined) window.clearTimeout(poseTimer);
  poseTimer = window.setTimeout(async () => {
    if (poseBusy) {
      posePending = true;
      return;
    }
    poseBusy = true;
    const controls = Object.fromEntries(jointSliders.map(input =>
      [input.dataset.joint!, Number(input.value) * Math.PI / 180]));
    if (!preview) element('#unified-live-status').textContent = 'OpenSim 正在计算姿态…';
    try {
      const response = await fetch('/api/pose', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ controls, coordinates: individualCoordinates,
          plantFeet: element<HTMLInputElement>('#unified-plant-feet').checked }) });
      const result = await response.json() as { frame?: ModelFrame; error?: string };
      if (!response.ok || !result.frame) throw new Error(result.error ?? `HTTP ${response.status}`);
      if (requestId !== poseRequest || mode !== 'custom') return;
      customFrame = result.frame;
      customPreviewActive = false;
      element('#unified-live-status').textContent = '已由 OpenSim 精确重新计算';
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
  }, 70);
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
  const hit = pickRay.intersectObjects([...dragHandles.values()], false)[0];
  if (!hit) return;
  const handle = hit.object as THREE.Mesh;
  const normal = new THREE.Vector3();
  camera.getWorldDirection(normal);
  draggingHand = { handle, plane: new THREE.Plane().setFromNormalAndCoplanarPoint(
    normal, handle.position) };
  orbit.enabled = false;
  renderer.domElement.setPointerCapture(event.pointerId);
  element('#unified-live-status').textContent = `拖动${handle.name.endsWith('_r') ? '右' : '左'}${handle.name.startsWith('hand') ? '手' : '脚'}；松开后由 OpenSim 求解`;
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
  const part = handle.name.startsWith('hand') ? '手部' : '脚部';
  element('#unified-live-status').textContent = `OpenSim 正在拟合${part}目标…`;
  void (async () => {
    try {
      const response = await fetch('/api/ik', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ controls, coordinates: individualCoordinates,
          plantFeet: element<HTMLInputElement>('#unified-plant-feet').checked,
          body: handle.name, target }) });
      const result = await response.json() as { frame?: ModelFrame;
        solvedCoordinates?: Record<string, number>; targetErrorM?: number; error?: string };
      if (!response.ok || !result.frame || !result.solvedCoordinates)
        throw new Error(result.error ?? `HTTP ${response.status}`);
      if (requestId !== poseRequest || mode !== 'custom') return;
      customFrame = result.frame;
      customPreviewActive = false;
      Object.assign(individualCoordinates, result.solvedCoordinates);
      element('#unified-live-status').textContent = (result.targetErrorM ?? 0) < 0.05
        ? `${part}目标已由 OpenSim 求解；对侧关节未同步改变`
        : `${part}目标超出可达范围；最近姿态距目标 ${((result.targetErrorM ?? 0) * 100).toFixed(1)} cm`;
      updateFrame();
    } catch (error) {
      element('#unified-live-status').textContent =
        `${part}求解失败：${error instanceof Error ? error.message : String(error)}`;
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
    delete individualCoordinates[`${input.dataset.joint}_r`];
    delete individualCoordinates[`${input.dataset.joint}_l`];
    requestCustomPose();
  });
}
element<HTMLInputElement>('#unified-plant-feet').addEventListener('change', requestCustomPose);

for (const button of document.querySelectorAll<HTMLButtonElement>('[data-mode]')) {
  button.addEventListener('click', () => {
    mode = button.dataset.mode as Mode;
    if (mode !== 'custom') customPreviewActive = false;
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
element<HTMLElement>('#unified-major').addEventListener('click', event => {
  const target = (event.target as HTMLElement).closest<HTMLButtonElement>('[data-surface-index]');
  if (!target) return;
  const chosen = surfaceMeshes[Number(target.dataset.surfaceIndex)];
  if (!chosen) return;
  selected = chosen.modelIndices[0];
  group = 'all';
  groupSelect.value = 'all';
  syncMuscleOptions();
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
element<HTMLInputElement>('#unified-focus').addEventListener('change', updateFrame);

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
    for (const [name, key] of [['hand_r', 'handRightScreen'], ['calcn_r', 'footRightScreen']] as const) {
      const handle = dragHandles.get(name);
      if (!handle) continue;
      const screen = handle.position.clone().project(camera);
      const rect = renderer.domElement.getBoundingClientRect();
      stage.dataset[key] = `${rect.left + (screen.x + 1) * rect.width / 2},${rect.top + (1 - screen.y) * rect.height / 2}`;
    }
  }
  renderer.render(scene, camera);
  requestAnimationFrame(render);
}
requestAnimationFrame(render);

async function load(): Promise<void> {
  const [response, gltf, surfaceGltf, boneGltf, skinResponse, weightResponse, boneResponse, basisResponse] = await Promise.all([
    fetch('/data/unified_opensim_reference.json?v=140'),
    new GLTFLoader().loadAsync('/models/unified_opensim_skeleton.glb'),
    new GLTFLoader().loadAsync('/models/unified_muscle_surfaces.glb?v=140'),
    new GLTFLoader().loadAsync('/models/unified_anatomy_bones.glb?v=140'),
    fetch('/data/unified_muscle_skin.json?v=140'),
    fetch('/data/unified_muscle_weights.bin?v=140'),
    fetch('/data/unified_anatomy_bones.json?v=140'),
    fetch('/data/unified_pose_basis.json?v=140'),
  ]);
  if (!response.ok) throw new Error(`OpenSim frame data HTTP ${response.status}`);
  if (!skinResponse.ok || !weightResponse.ok || !boneResponse.ok || !basisResponse.ok) throw new Error('精细骨肌或实时预览数据缺失');
  data = await response.json() as Reference;
  poseBasis = await basisResponse.json() as PoseBasis;
  if (poseBasis.model !== data.model || poseBasis.bodyNames.length !== data.bodyNames.length
    || poseBasis.muscleNames.length !== data.muscleNames.length)
    throw new Error('OpenSim 姿态采样与主模型不一致');
  const skin = await skinResponse.json() as MuscleSkin;
  const anatomy = await boneResponse.json() as AnatomyBones;
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
    if (essential) essentialsGroup.add(mesh);
    const entries = bodyMeshes.get(body) ?? [];
    entries.push(mesh);
    bodyMeshes.set(body, entries);
  });
  if (bodyMeshes.size < 20) throw new Error(`only ${bodyMeshes.size} OpenSim bodies have source meshes; nodes: ${gltf.scene.children.slice(0, 5).map(child => child.name).join(', ')}`);
  const anatomyByName = new Map(anatomy.bones.map(entry =>
    [THREE.PropertyBinding.sanitizeNodeName(entry.name), entry]));
  boneGltf.scene.updateMatrixWorld(true);
  boneGltf.scene.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return;
    const entry = anatomyByName.get(object.name);
    if (!entry) return;
    const geometry = object.geometry.clone();
    geometry.applyMatrix4(object.matrixWorld);
    const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({
      color: '#e4e3cd', emissive: '#9ba997', emissiveIntensity: 0.12,
      side: THREE.DoubleSide, roughness: 0.72, transparent: true,
      opacity: 0.28, depthTest: false, depthWrite: false,
    }));
    mesh.name = entry.name;
    mesh.matrixAutoUpdate = false;
    mesh.renderOrder = 20;
    bonesGroup.add(mesh);
    const neutral = data!.neutral.bodies[entry.bodyIndex];
    const inverseNeutral = new THREE.Matrix4().set(
      neutral.r[0], neutral.r[1], neutral.r[2], neutral.p[0],
      neutral.r[3], neutral.r[4], neutral.r[5], neutral.p[1],
      neutral.r[6], neutral.r[7], neutral.r[8], neutral.p[2], 0, 0, 0, 1).invert();
    anatomyBoneMeshes.push({ mesh, bodyIndex: entry.bodyIndex, inverseNeutral });
  });
  if (anatomyBoneMeshes.length !== anatomy.bones.length)
    throw new Error(`仅加载 ${anatomyBoneMeshes.length}/${anatomy.bones.length} 个解剖骨表面`);
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
  // The source atlas supplies cervical vertebrae but no outer neck muscles.
  // This small connective envelope closes the visible gap and follows the
  // same OpenSim thoracic1/head_neck transforms as the anatomical surfaces.
  const neckGeometry = new THREE.CylinderGeometry(0.063, 0.086, 0.14, 24, 8);
  const neckPosition = neckGeometry.getAttribute('position') as THREE.BufferAttribute;
  const neckIndices = new Uint16Array(neckPosition.count * 4);
  const neckWeights = new Float32Array(neckPosition.count * 4);
  const thoracicIndex = data.bodyNames.indexOf('thoracic1');
  const headIndex = data.bodyNames.indexOf('head_neck');
  for (let index = 0; index < neckPosition.count; index++) {
    const t = THREE.MathUtils.clamp((neckPosition.getY(index) + 0.07) / 0.14, 0, 1);
    neckPosition.setXYZ(index,
      neckPosition.getX(index) - 0.096 - 0.014 * t,
      neckPosition.getY(index) + 1.44,
      neckPosition.getZ(index));
    const headWeight = THREE.MathUtils.smoothstep(t, 0.15, 0.85);
    neckIndices[index * 4] = thoracicIndex;
    neckIndices[index * 4 + 1] = headIndex;
    neckWeights[index * 4] = 1 - headWeight;
    neckWeights[index * 4 + 1] = headWeight;
  }
  neckPosition.needsUpdate = true;
  neckGeometry.computeVertexNormals();
  neckGeometry.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(neckIndices, 4));
  neckGeometry.setAttribute('skinWeight', new THREE.Float32BufferAttribute(neckWeights, 4));
  const neckEnvelope = new THREE.SkinnedMesh(neckGeometry, new THREE.MeshStandardMaterial({
    color: '#aa797d', roughness: 0.72, side: THREE.DoubleSide,
  }));
  neckEnvelope.name = 'OpenSim-bound neck envelope';
  neckEnvelope.frustumCulled = false;
  neckEnvelope.bindMode = 'detached';
  neckEnvelope.bind(skinSkeleton, new THREE.Matrix4());
  surfacesGroup.add(neckEnvelope);
  stage.dataset.neckEnvelope = 'true';
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
    // Large cross-joint endpoint weights pull these short bellies away from
    // the bone at deep flexion. Keep their central body anchor dominant.
    const anchorStrength = /Short head of biceps brachii|gastrocnemius/.test(entry.name)
      ? 0.55 : 0.82;
    for (let i = 0; i < count; i++) {
      const u = weights[entry.weightOffset + i] / 255;
      const smooth = (a: number, b: number, value: number): number => {
        const t = THREE.MathUtils.clamp((value - a) / (b - a), 0, 1);
        return t * t * (3 - 2 * t);
      };
      const origin = anchorStrength * (1 - smooth(0.03, 0.38, u));
      const insertion = anchorStrength * smooth(0.62, 0.97, u);
      indices[i * 4] = entry.bodyIndices[0];
      indices[i * 4 + 1] = entry.bodyIndices[1];
      indices[i * 4 + 2] = entry.bodyIndices[2];
      influences[i * 4] = origin;
      influences[i * 4 + 1] = 1 - origin - insertion;
      influences[i * 4 + 2] = insertion;
    }
    geometry.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(indices, 4));
    geometry.setAttribute('skinWeight', new THREE.Float32BufferAttribute(influences, 4));
    const position = geometry.getAttribute('position') as THREE.BufferAttribute;
    const bulge = new Float32Array(count * 3);
    const center = new THREE.Vector3(...entry.center);
    const axis = new THREE.Vector3(...entry.axis).normalize();
    const vertex = new THREE.Vector3();
    for (let i = 0; i < count; i++) {
      vertex.fromBufferAttribute(position, i);
      const u = weights[entry.weightOffset + i] / 255;
      const radial = vertex.clone().sub(center);
      radial.addScaledVector(axis, -radial.dot(axis));
      vertex.addScaledVector(radial, 0.08 * Math.sin(Math.PI * u));
      bulge.set([vertex.x, vertex.y, vertex.z], i * 3);
    }
    geometry.morphAttributes.position = [new THREE.Float32BufferAttribute(bulge, 3)];
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
