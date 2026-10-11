import './style.css';
import { Capacitor } from '@capacitor/core';
import { Directory, Encoding, Filesystem } from '@capacitor/filesystem';
import { Share } from '@capacitor/share';
import { AnatomyPrototype, createPose, profileSegmentDimensions, registeredArmThicknessScale,
  registeredCalfThicknessScale, registeredChestThicknessScale, registeredThighThicknessScale,
  registeredWaistThicknessScale,
  squatKneeFlexionDeg, type JointMomentOverlay, type OpenSimFrame, type PoseOverrides,
  type RegisteredMuscleColorMode } from './model';
import { barbellGravityMoments, benchBarbellMomentScenarios, squatBalanceEstimate, squatVerticalSupportScenario } from './mechanics';
import squatEvidence from './data/squat_evidence.json';
import pressEmgStudy from './data/press_emg_study.json';
import standingPressStudy from './data/standing_press_study.json';
import demoMotionProtocol from './data/demo_motion_protocol.json';
import benchVelocityBenchmark from './data/bench_velocity_benchmark.json';
import benchLateralStudy from './data/bench_lateral_force_study.json';
import benchCapacityEvidence from '../docs/data/bench_repetition_capacity_benchmark.json';
const benchSampleLateralPercents = [...benchLateralStudy.subjectMeanLateralPercentOfAssumedVertical]
  .sort((a, b) => a - b);
const benchMedianLateralPercent = (benchSampleLateralPercents[4] + benchSampleLateralPercents[5]) / 2;
import { advanceBenchPhase, benchPlaybackTiming, type BenchTempoMode } from './tempo';
import { squatStudyJointMoments } from './study-moments';
import { measurementDiagramHtml } from './measurement-diagram';
import {
  bodyFields, exercises, loadProfile, loadTraining, parseProfile, saveProfile, saveTraining,
  estimatedOneRepMax, makeLocalBackup, parseLocalBackup, trainingVariations, trainingRanges,
  trainingEquipments, trainingEquipmentLabel, entersBarbellCapacityPool,
  type BodyProfile, type ExerciseId, type TrainingEntry, type TrainingEquipment, type ViewMode,
} from './domain';

const app = document.querySelector<HTMLDivElement>('#app');
if (!app) throw new Error('找不到应用根节点');

// The one place the build names itself. It has to stay in sync with CACHE in public/sw.js (checked by
// scripts/check-shipped-package-audit.mjs), and the footer prints it so on-device feedback can say which
// build it came from. On the native container there is no service worker, so the footer is the only
// place this identity appears there.
const buildCache = 'muscle-atlas-v133';

let profile: BodyProfile = loadProfile();
let pressTrajectoryProfile: BodyProfile | undefined;
let pressTrajectoryDescription = '';
let training: TrainingEntry[] = loadTraining();
// The list shows the five most recent records by default. These two only change what is displayed: the
// stored records and the 1RM pool are untouched, and neither is persisted, so no new storage key exists.
let trainingFilter: ExerciseId | 'all' = 'all';
let trainingShowAll = false;
// Search text and sort order, like the filter, only change what the list displays: neither is stored, no
// storage key is added, and neither touches a saved record or the capacity estimate.
let trainingQuery = '';
let trainingSort: 'recent' | 'load' | 'estimate' = 'recent';
const savedExercise = localStorage.getItem('muscle-atlas-exercise-v1');
let exercise: ExerciseId = savedExercise === 'bench' || savedExercise === 'press'
  ? savedExercise : 'squat';
const loads: Record<ExerciseId, number> = { squat: 20, bench: 20, press: 20 };
const savedSquatBarOffsetCm = Number(localStorage.getItem('muscle-atlas-squat-bar-offset-cm-v1'));
let squatBarOffsetCm = Number.isFinite(savedSquatBarOffsetCm) && [-6, 0, 6].includes(savedSquatBarOffsetCm)
  ? savedSquatBarOffsetCm : 0;
const storedSquatDepth = localStorage.getItem('muscle-atlas-squat-depth-deg-v1');
let squatDepthDeg: number | undefined = storedSquatDepth !== null && [75, 117].includes(Number(storedSquatDepth))
  ? Number(storedSquatDepth) : undefined;
const storedCycleDuration = Number(localStorage.getItem('muscle-atlas-cycle-duration-s-v1'));
let cycleDurationS = [2, 4].includes(storedCycleDuration)
  ? storedCycleDuration : demoMotionProtocol.cycleDurationS;
const storedBenchTempo = localStorage.getItem('muscle-atlas-bench-tempo-v1');
let benchTempoMode: BenchTempoMode = storedBenchTempo === 'study50' || storedBenchTempo === 'study75'
  ? storedBenchTempo : 'teaching';
try {
  const saved = JSON.parse(localStorage.getItem('muscle-atlas-loads-v1') ?? '{}') as Partial<Record<ExerciseId, number>>;
  for (const id of Object.keys(loads) as ExerciseId[]) {
    if (typeof saved[id] === 'number' && Number.isFinite(saved[id]) && saved[id] >= 0 && saved[id] <= 300) loads[id] = saved[id];
  }
} catch { /* Keep default demonstration loads. */ }
let view: ViewMode = 'length';
let squatDemandMode: 'barbell' | 'study' = 'barbell';
let phase = 0;
let playing = false;
let showBones = true;
let showMuscles = true;
let showOutline = true;
let referenceMode = false;
let poseEditMode = false;
let poseOverrides: PoseOverrides = {};
let registeredBonesMode = false;
let tsmUpperBonesMode = false;
let registeredColorMode: RegisteredMuscleColorMode = 'identity';
let lastFrame = 0;
type OpenSimLookup = { schemaVersion: number; status: string; maximumPolylineErrorM: number; frames: OpenSimFrame[] };
type ReferenceExercise = ExerciseId;
const opensimLookups: Partial<Record<ReferenceExercise, OpenSimLookup>> = {};
const opensimLoading = new Set<ReferenceExercise>();
const opensimErrors = new Set<ReferenceExercise>();
let selectedOpenSimMuscle = exercise === 'squat' ? 'vas_int_r' : 'PectoralisMajorThorax_M';
let selectedIllustrativeMuscle = exercise === 'squat' ? '左竖脊肌' : '左胸大肌';
let showAllTsmMuscles = false;
const opensimLabels: Record<string, string> = {
  bifemsh_r: '股二头肌短头', med_gas_r: '腓肠肌内侧头', glut_max2_r: '臀大肌（模型单束）',
  psoas_r: '腰大肌', rect_fem_r: '股直肌', semimem_r: '半膜肌', soleus_r: '比目鱼肌',
  tib_ant_r: '胫骨前肌', vas_int_r: '股中间肌',
};
const tsmLabels: Record<string, string> = {
  TrapeziusScapula_M: '斜方肌 · 肩胛中束', TrapeziusScapula_S: '斜方肌 · 肩胛上束',
  TrapeziusScapula_I: '斜方肌 · 肩胛下束', TrapeziusClavicle_S: '斜方肌 · 锁骨束',
  SerratusAnterior_I: '前锯肌 · 下束', SerratusAnterior_M: '前锯肌 · 中束',
  SerratusAnterior_S: '前锯肌 · 上束', Rhomboideus_S: '菱形肌 · 上束',
  Rhomboideus_I: '菱形肌 · 下束', LevatorScapulae: '肩胛提肌',
  Coracobrachialis: '喙肱肌', DeltoideusClavicle_A: '三角肌 · 前束',
  DeltoideusScapula_P: '三角肌 · 后束', DeltoideusScapula_M: '三角肌 · 中束',
  LatissimusDorsi_S: '背阔肌 · 上束', LatissimusDorsi_M: '背阔肌 · 中束',
  LatissimusDorsi_I: '背阔肌 · 下束', PectoralisMajorClavicle_S: '胸大肌 · 锁骨束',
  PectoralisMajorThorax_I: '胸大肌 · 下束', PectoralisMajorThorax_M: '胸大肌 · 中束',
  TeresMajor: '大圆肌', Infraspinatus_I: '冈下肌 · 下束',
  Infraspinatus_S: '冈下肌 · 上束', PectoralisMinor: '胸小肌',
  TeresMinor: '小圆肌', Subscapularis_S: '肩胛下肌 · 上束',
  Subscapularis_M: '肩胛下肌 · 中束', Subscapularis_I: '肩胛下肌 · 下束',
  Supraspinatus_P: '冈上肌 · 后束', Supraspinatus_A: '冈上肌 · 前束',
  TRIlong: '肱三头肌 · 长头', BIC_long: '肱二头肌 · 长头', BIC_brevis: '肱二头肌 · 短头',
};
const referenceLabels: Record<string, string> = {
  Clavicle: '锁骨', Scapula: '肩胛骨', Humerus: '肱骨', Radius: '桡骨', Ulna: '尺骨',
  Femur: '股骨', Tibia: '胫骨', Fibula: '腓骨', 'Hip bone': '髋骨', Sacrum: '骶骨',
  'Body of sternum': '胸骨体', 'Manubrium of sternum': '胸骨柄',
  'Clavicular head of pectoralis major muscle': '胸大肌锁骨部',
  'Sternocostal head of pectoralis major muscle': '胸大肌胸肋部',
  '(Abdominal part of pectoralis major muscle)': '胸大肌腹部',
  'Acromial part of deltoid muscle': '三角肌肩峰部',
  'Clavicular part of deltoid muscle': '三角肌锁骨部',
  'Scapular spinal part of deltoid muscle': '三角肌肩胛冈部',
  'Long head of biceps brachii': '肱二头肌长头', 'Short head of biceps brachii': '肱二头肌短头',
  'Lateral head of triceps brachii': '肱三头肌外侧头',
  'Long head of triceps brachii': '肱三头肌长头',
  'Medial head of triceps brachii': '肱三头肌内侧头',
  'Gluteus maximus muscle': '臀大肌', 'Gluteus medius muscle': '臀中肌',
  'Rectus abdominis muscle': '腹直肌', 'External abdominal oblique muscle': '腹外斜肌',
  'Rectus femoris muscle': '股直肌', 'Vastus intermedius muscle': '股中间肌',
  'Vastus lateralis muscle': '股外侧肌', 'Vastus medialis muscle': '股内侧肌',
  'Long head of biceps femoris': '股二头肌长头', 'Short head of biceps femoris': '股二头肌短头',
  'Semimembranosus muscle': '半膜肌', 'Semitendinosus muscle': '半腱肌',
  'Lateral head of gastrocnemius': '腓肠肌外侧头',
  'Medial head of gastrocnemius': '腓肠肌内侧头', 'Soleus muscle': '比目鱼肌',
  'Tibialis anterior muscle': '胫骨前肌', 'Latissimus dorsi muscle': '背阔肌',
  'Ascending part of trapezius muscle': '斜方肌下部',
  'Transverse part of trapezius muscle': '斜方肌中部',
  'Descending part of trapezius muscle': '斜方肌上部',
  'Serratus anterior muscle': '前锯肌', 'Rhomboid major muscle': '大菱形肌',
  'Brachialis muscle': '肱肌', 'Brachioradialis muscle': '肱桡肌',
  'Longissimus thoracis muscle': '胸最长肌',
};
function referenceDisplayName(raw: string): string {
  const explicitSide = raw.match(/[._]([lr])$/i)?.[1]?.toLowerCase();
  const separatedBase = raw.replace(/[._][lr]$/i, '').replaceAll('_', ' ');
  // The GLB exporter also emits some names with a bare trailing l/r.
  const bareBase = raw.slice(0, -1).replaceAll('_', ' ');
  const bareSide = !explicitSide && /[lr]$/i.test(raw) && referenceLabels[bareBase]
    ? raw.slice(-1).toLowerCase() : undefined;
  const side = explicitSide ?? bareSide;
  const base = bareSide ? bareBase : separatedBase;
  return `${side === 'l' ? '左' : side === 'r' ? '右' : ''}${referenceLabels[base] ?? base} · ${base}`;
}
const offlineInitial = Capacitor.isNativePlatform() ? '资源已内置' : import.meta.env.PROD ? '离线包准备中' : '开发预览';

const fieldHtml = bodyFields.map(field => `
  <label class="field">
    <span>${field.label}${field.required ? '<b aria-label="必填"> *</b>' : ''}</span>
    <input name="${field.key}" type="number" inputmode="decimal" min="${field.min}" max="${field.max}" step="${field.step ?? 1}" ${field.required ? 'required' : ''} value="${profile[field.key] ?? ''}" />
  </label>
`).join('');

type StudyEmgCurve = { p25: number[]; median: number[]; p75: number[] };
function studyEmgChart(label: string, channel: 'RRF' | 'RVL' | 'RBF'): string {
  const curve: StudyEmgCurve = squatEvidence.phaseEmgStudyCurves[channel];
  const x = (index: number) => 8 + (index + 1) * 284 / 100;
  const max = Math.max(1.5, ...curve.p75) * 1.05;
  const y = (value: number) => 70 - Math.max(0, Math.min(max, value)) * 58 / max;
  const line = curve.median.map((value, index) => `${index ? 'L' : 'M'}${x(index).toFixed(1)} ${y(value).toFixed(1)}`).join(' ');
  const top = curve.p75.map((value, index) => `${index ? 'L' : 'M'}${x(index).toFixed(1)} ${y(value).toFixed(1)}`).join(' ');
  const bottom = curve.p25.map((_, index) => {
    const reverse = 98 - index;
    return `L${x(reverse).toFixed(1)} ${y(curve.p25[reverse]).toFixed(1)}`;
  }).join(' ');
  return `<div class="emg-study-chart"><strong>${label}</strong><svg viewBox="0 0 300 84" role="img" aria-label="${label}：公开自重深蹲样本标准化肌电，实线为十二人中位数，阴影为四分位范围">
    <line class="emg-baseline" x1="8" y1="${y(1).toFixed(1)}" x2="292" y2="${y(1).toFixed(1)}" />
    <line class="emg-turnaround" x1="150" y1="8" x2="150" y2="70" />
    <path class="emg-band" d="${top} ${bottom} Z" />
    <path class="emg-median" d="${line}" />
    <line data-emg-phase-marker x1="8" y1="7" x2="8" y2="71" />
    <text x="8" y="82">下蹲</text><text x="150" y="82" text-anchor="middle">最深</text><text x="292" y="82" text-anchor="end">起身</text>
  </svg></div>`;
}

type StudyJointMomentCurve = { p10: number[]; median: number[]; p90: number[] };
function studyJointMomentChart(label: string, joint: 'rightHip' | 'rightKnee'): string {
  const curve: StudyJointMomentCurve = squatEvidence.phaseJointMomentStudyCurves[joint];
  const x = (index: number) => 8 + (index + 1) * 284 / 100;
  const low = Math.min(0, ...curve.p10);
  const high = Math.max(0, ...curve.p90);
  const span = high - low || 1;
  const y = (value: number) => 70 - (value - low) * 58 / span;
  const line = curve.median.map((value, index) => `${index ? 'L' : 'M'}${x(index).toFixed(1)} ${y(value).toFixed(1)}`).join(' ');
  return `<div class="joint-study-chart"><strong>${label}</strong><svg viewBox="0 0 300 84" role="img" aria-label="${label}：十二人自重深蹲的源逆动力学净关节力矩中位曲线，单位牛顿米每千克">
    <line class="joint-zero" x1="8" y1="${y(0).toFixed(1)}" x2="292" y2="${y(0).toFixed(1)}" />
    <line class="joint-turnaround" x1="150" y1="8" x2="150" y2="70" />
    <path class="joint-median" d="${line}" />
    <line data-joint-phase-marker x1="8" y1="7" x2="8" y2="71" />
    <text x="8" y="82">下蹲</text><text x="150" y="82" text-anchor="middle">最深</text><text x="292" y="82" text-anchor="end">起身</text>
  </svg></div>`;
}

const pressEmgRows = [
  { key: 'pectoralis_clavicular', label: '胸大肌锁骨部' },
  { key: 'deltoid_anterior', label: '三角肌前束' },
  { key: 'deltoid_middle', label: '三角肌中束' },
  { key: 'deltoid_posterior', label: '三角肌后束' },
  { key: 'triceps_lateral', label: '肱三头肌外侧头' },
  { key: 'trapezius_upper', label: '斜方肌上束' },
] as const;

app.innerHTML = `
  <header class="site-header">
    <div class="brand"><span class="brand-mark">◆</span><div><strong>肌动图谱</strong><small>个人化肌骨动作教学 · 原型</small></div></div>
    <div class="header-status"><span class="prototype-badge">研究原型 v0.1</span><span id="offline-status" class="offline-status" role="status">${offlineInitial}</span></div>
  </header>
  <main class="layout">
    <section class="intro">
      <p class="eyebrow">从自己的身体开始理解动作</p>
      <h1>看见动作里的<br><em>长度变化</em>与<em>发力需求</em></h1>
      <p>输入身体参数，查看三维动作示意、肌肉路径长度变化和杠铃重力力臂。真正的肌肉发力估算仍在建模阶段。</p>
    </section>

    <section class="workspace" aria-label="模型工作台">
      <div class="viewer-panel">
        <div class="viewer-topline"><span class="live-dot"></span><span>三维模型 · 可拖动旋转</span><span id="asset-tag" class="viewer-tag">Blender 模型加载中</span></div>
        <div class="viewer-toolbar">
          <div class="view-tabs" role="group" aria-label="观察视图">
            <button type="button" class="view-tab selected" data-view="length" aria-pressed="true">路径长度</button>
            <button type="button" class="view-tab" data-view="opensim" aria-pressed="false">OpenSim 参考</button>
            <button type="button" class="view-tab" data-view="demand" aria-pressed="false">负重力学</button>
          </div>
          <label id="squat-demand-mode-control" class="load-control" hidden><span>深蹲力学显示</span><select id="squat-demand-mode" aria-label="选择深蹲力学依据"><option value="barbell">橙环 · 当前杠铃重力情景</option><option value="study">紫环 · 12 人自重深蹲研究参考</option></select></label>
          <div class="layers">
            <label><input id="bones-toggle" type="checkbox" checked /> 骨骼</label>
            <label><input id="muscles-toggle" type="checkbox" checked /> 肌肉示意</label>
            <label><input id="outline-toggle" type="checkbox" checked /> 半透明外表层</label>
            <label><input id="registered-bones-toggle" type="checkbox" /> 右腿六块骨骼＋八块肌肉 · 研究形变</label>
            <label id="tsm-upper-bones-control" hidden><input id="tsm-upper-bones-toggle" type="checkbox" /> 右臂三骨＋肱二头肌／胸大肌／三角肌研究层</label>
          </div>
          <label id="registered-color-control" class="registered-color-control" hidden><span>研究层肌肉颜色</span><select id="registered-color-mode" aria-label="研究层肌肉颜色"><option value="identity">按结构区分</option><option value="path-length">按模型路径长度</option></select></label>
          <button id="reference-toggle" type="button" class="button ghost reference-button">查看静态解剖参考</button>
        </div>
        <div id="viewer" class="viewer" role="group" tabindex="0" aria-label="可旋转的三维骨骼与肌肉示意模型：方向键左右旋转、上下俯仰，加号减号或 PageUp／PageDown 缩放"></div>
        <div id="viewer-research-readout" class="viewer-research-readout" data-output="viewer-research-readout" data-status="research_reference" data-source="squat_study_joint_moments" hidden></div>
        <div class="viewer-bottomline"><span id="viewer-instruction">拖动旋转 · 滚轮缩放</span><span id="model-status">几何示意</span></div>
      </div>

      <div class="control-panel">
        <section class="panel-section">
          <div class="section-heading"><span class="step-number">01</span><h2>选择动作</h2></div>
          <div class="exercise-tabs" role="group" aria-label="预设动作">
            ${Object.entries(exercises).map(([id, info]) => `<button type="button" class="exercise-tab${id === exercise ? ' selected' : ''}" data-exercise="${id}" aria-pressed="${id === exercise ? 'true' : 'false'}">${info.label}</button>`).join('')}
          </div>
          <div class="timeline-header"><span id="exercise-cue">下蹲 → 起身</span><strong id="phase-label">0%</strong></div>
          <input id="timeline" class="timeline" type="range" min="0" max="100" value="0" aria-label="动作进度" />
          <div class="timeline-actions"><button id="play-button" type="button" class="button ghost">▶ 播放</button><span>拖动时间轴逐帧观察</span></div>
          <div class="pose-edit-actions"><button id="pose-edit-toggle" type="button" class="button ghost" aria-pressed="false">自由摆姿</button><button id="pose-reset" type="button" class="button ghost" hidden>恢复当前预设姿势</button></div>
          <p id="pose-edit-note" class="load-note" hidden>拖动模型上的蓝色或金色圆点调整双手、双脚。骨段长度保持不变；颜色表示相对当前预设姿势的近似路径长度变化。手机上可直接触摸拖动。点选空白处仍可旋转视角。</p>
          <label id="cycle-duration-control" class="load-control"><span>一组动作周期 · 示意时长</span><select id="cycle-duration" aria-label="预设动作周期时长"><option value="2">较快 · 2.0 秒</option><option value="2.8">默认 · 2.8 秒</option><option value="4">较慢 · 4.0 秒</option></select></label>
          <p id="cycle-duration-note" class="load-note" data-output="cycle-duration-note" data-status="illustrative" data-source="preset_playback_timing">只控制预设动作播放速度；没有测量你的实际动作。动态力示意目前仅用于深蹲。</p>
          <label id="bench-tempo-control" class="load-control" hidden><span>卧推播放节奏</span><select id="bench-tempo" aria-label="卧推播放节奏"><option value="teaching">慢速教学 · 对称周期</option><option value="study50">实验 50% 1RM · 起举速度参照</option><option value="study75">实验 75% 1RM · 起举速度参照</option></select></label>
          <p id="bench-velocity-note" class="load-note" data-output="bench-velocity-note" data-status="research_reference" data-source="bench_velocity_benchmark" hidden></p>
          <label id="load-control" class="load-control"><span>杠铃总重量 kg</span><input id="load-input" type="number" inputmode="decimal" min="0" max="300" step="2.5" value="${loads[exercise]}" /></label>
          <label id="squat-bar-control" class="load-control"><span>深蹲杠铃前后位置假设</span><select id="squat-bar-offset" aria-label="深蹲杠铃相对默认位置前后偏移"><option value="-6">向后 6 cm</option><option value="0">默认位置</option><option value="6">向前 6 cm</option></select></label>
          <p id="squat-bar-note" class="load-note" data-output="squat-bar-note" data-status="scenario" data-source="user_bar_offset_assumption">相对肩中心的水平偏移；不代表高杠位或低杠位技术测量。</p>
          <label id="squat-depth-control" class="load-control depth-control"><span>深蹲幅度示意</span><select id="squat-depth" aria-label="深蹲模型最深膝屈角"><option value="75">较浅 · 约 75°</option><option value="">原型默认 · 约 96°</option><option value="117">较深 · 约 117°</option></select></label>
          <p id="squat-depth-note" class="load-note" data-output="squat-depth-note" data-status="illustrative" data-source="preset_trajectory"></p>
          <p id="load-effect-note" class="load-note" data-output="load-effect-note" data-status="scenario" data-source="barbell_static_scenario">当前重量影响动作示意中的器械外观与负重力学情景；尚未进入肌肉发力计算。</p>
          <p id="capacity-hint" class="capacity-hint" data-output="capacity-hint" data-status="estimate" data-source="epley_with_reserve_reps"></p>
        </section>

              </div>
    </section>

    <div class="lower-grid">
      <div class="side-column">
        <section class="card readout-card">
          <div class="section-heading"><div><h2>读数与实验对照</h2><p>当前视图的读数与公开实验对照；数值不随个人发力标定。</p></div></div>
          <div id="view-explanation" class="explanation"></div>
          <details id="press-evidence" class="lab-evidence" data-output="press-evidence" data-status="research_reference" data-source="press_emg_and_trajectory" hidden>
            <summary>实验对照 · 站姿轨迹与坐姿肌电</summary>
            <div class="lab-evidence-body">
              <h3>站姿杠铃轨迹 · 14 人研究</h3>
              <p id="press-trajectory-comparison" data-output="press-trajectory-comparison" data-status="research_reference" data-source="press_group_trajectory"></p>
              <p>动画让杠铃在上推早期略向前，再向后靠近肩部；转折时点由教学模型设定。论文仅公布组层范围，没有可逐帧核查的个人轨迹或手部外力。示意数值由输入身高、臂展和预设轨迹生成；范围接近也不能验证你的动作或肌肉发力。<a href="${standingPressStudy.sourceUrl}" target="_blank" rel="noreferrer">An 等，2025 ↗</a></p>
              <h3>坐姿杠铃肩推肌电 · 8 人研究</h3>
              <p>公开实验让 ${pressEmgStudy.participants} 人靠着约 80° 靠背，以各自约 80% 1RM 做前方杠铃肩推。下表是六块肌肉上推／下放整阶段的肌电平均值，单位为各肌肉自身最大等长肌电参考值的百分比；每人每阶段只保留一个均值。</p>
              <div class="press-study-table-wrap"><table class="press-study-table"><thead><tr><th>肌肉</th><th>上推均值</th><th>下放均值</th><th>上推较高</th></tr></thead><tbody>${pressEmgRows.map(item => {
                const row = pressEmgStudy.muscles[item.key];
                return `<tr><th scope="row">${item.label}</th><td>${row.concentricMeanPctReference.toFixed(0)}%</td><td>${row.eccentricMeanPctReference.toFixed(0)}%</td><td>${row.participantsConcentricHigher}/8 人</td></tr>`;
              }).join('')}</tbody></table></div>
              <p>这是一项<strong>坐姿</strong>研究，当前动画是站姿实力举，技术、支撑与重量比例不能自动等同。表格没有逐帧肌电、杠铃轨迹或手部外力；肌电也不是肌肉拉力。因而这些数值不随你的参数变化，也不用于三维肌肉发力着色。</p>
              <small>来源：<a href="${pressEmgStudy.sourceUrl}" target="_blank" rel="noreferrer">Coratella 等，2022 ↗</a> · <a href="${pressEmgStudy.dataUrl}" target="_blank" rel="noreferrer">Zenodo 原始表格 ↗</a> · <a href="${pressEmgStudy.licenseUrl}" target="_blank" rel="noreferrer">CC BY 4.0 ↗</a>。</small>
            </div>
          </details>
          <div id="muscle-summary" class="muscle-summary"></div>
          <details id="lab-evidence" class="lab-evidence" data-output="lab-evidence" data-status="research_reference" data-source="dynamic_squat_studies">
            <summary>实验对照 · 12 人动态深蹲</summary>
            <div class="lab-evidence-body">
              <p>同一批受试者做自重深蹲和额外 ${squatEvidence.addedLoadLb} lb 深蹲。论文未说明重量放置位置。以下在同一动作阶段和相近髋、膝、踝姿态下对照；不是你的个人预测，也不是当前输入的杠铃重量。</p>
              <div class="lab-evidence-grid">
                <div><strong>下蹲</strong><span>地面反力中位差 +${Math.round(squatEvidence.descent.verticalGrfDifferenceMedianN)} N</span><span>右髋伸方向净力矩 ${squatEvidence.descent.hipExtensionDirectionCount}/${squatEvidence.descent.participants} 人增加</span><span>右膝净力矩 ${squatEvidence.descent.rightKneeIncreaseCount}/${squatEvidence.descent.participants} 人增加</span></div>
                <div><strong>起身</strong><span>地面反力中位差 +${Math.round(squatEvidence.ascent.verticalGrfDifferenceMedianN)} N</span><span>右髋伸方向净力矩 ${squatEvidence.ascent.hipExtensionDirectionCount}/${squatEvidence.ascent.participants} 人增加</span><span>右膝净力矩 ${squatEvidence.ascent.rightKneeIncreaseCount}/${squatEvidence.ascent.participants} 人增加</span></div>
              </div>
              <p>起身阶段的表面肌电包络：右臀大肌通过信号筛选的 ${squatEvidence.ascentEmg.rightGluteMax.participants} 人中，${squatEvidence.ascentEmg.rightGluteMax.increaseCount} 人升高；右股外侧肌为 ${squatEvidence.ascentEmg.rightVastusLateralis.increaseCount}/${squatEvidence.ascentEmg.rightVastusLateralis.participants}。肌电表示电活动，不等于肌肉力量。</p>
              <p>肌电随动作阶段变化的跨人检验：对 ${squatEvidence.phaseEmgValidation.subjects} 人的 ${squatEvidence.phaseEmgValidation.unloadedReps} 次自重和 ${squatEvidence.phaseEmgValidation.loadedReps} 次额外 25 lb 深蹲，每次留出一整人，其余人建立标准化肌电曲线。自重右股直肌曲线比恒定基线更接近留出者：${squatEvidence.phaseEmgValidation.unloadedRightRectusFemoris.subjectsTemplateBeatsStatic}/${squatEvidence.phaseEmgValidation.subjects} 人；右股二头肌仅 ${squatEvidence.phaseEmgValidation.unloadedRightBicepsFemoris.subjectsTemplateBeatsStatic}/${squatEvidence.phaseEmgValidation.subjects} 人。额外 25 lb 右股外侧肌为 ${squatEvidence.phaseEmgValidation.loadedRightVastusLateralis.subjectsTemplateBeatsStatic}/${squatEvidence.phaseEmgValidation.subjects} 人。比较时用留出者自身实测肌电作幅值归一化，手机无法从身体参数获得这个幅值；此结果只能检验相对波形，不能给个人肌肉发力或红色高亮。</p>
              <p>跨实验室复核：把上面的自重股直肌相位模板固定，再对<a href="${squatEvidence.externalPhaseEmgSourceUrl}" target="_blank" rel="noreferrer">Tang 等（2026）SAME-Limb 的 30 人深蹲肌电数据 ↗</a>逐人测试，${squatEvidence.externalPhaseEmgValidation.templateBeatsStatic}/${squatEvidence.externalPhaseEmgValidation.participants} 人优于恒定基线；每人误差改善中位 ${squatEvidence.externalPhaseEmgValidation.medianPairedImprovement.toFixed(3)}，人数优势的单侧符号检验 p=${squatEvidence.externalPhaseEmgValidation.oneSidedSignTestP.toFixed(3)}。数据许可为 <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0 ↗</a>。新实验的深蹲条件没有箱内标准化负重，也不是杠铃深蹲；此处仅是左右腿、不同实验流程之间的波形探索性对照，优势尚不稳健，不能验证个人肌肉力。</p>
              <div class="emg-study-curves" aria-label="公开实验自重深蹲肌电相位波形">
                ${studyEmgChart('右股直肌 · 10/12 人优于恒定基线', 'RRF')}
                ${studyEmgChart('右股外侧肌 · 8/12 人优于恒定基线', 'RVL')}
                ${studyEmgChart('右股二头肌 · 2/12 人优于恒定基线', 'RBF')}
              </div>
              <p class="emg-study-note">实线是这 12 人自重深蹲的相对肌电中位波形，阴影是人群四分位范围；水平虚线为每人自身时间中位值 1，竖线跟随上方示意时间轴。不同人的绝对肌电幅值已消除，图形不表示你的肌电、肌肉拉力或训练重量影响。</p>
              <p>净关节力矩相位参考：仅用训练者的人群曲线预测留出者的完整自重深蹲，右髋／右膝比固定值更接近 ${squatEvidence.phaseJointMomentValidation.rightHip.phaseBeatsFlatSubjects}/12、${squatEvidence.phaseJointMomentValidation.rightKnee.phaseBeatsFlatSubjects}/12 人；逐人误差中位仍为 ${squatEvidence.phaseJointMomentValidation.rightHip.subjectMedianPhaseMaeNmPerKg.toFixed(2)}／${squatEvidence.phaseJointMomentValidation.rightKnee.subjectMedianPhaseMaeNmPerKg.toFixed(2)} N·m/kg。动作边界由实验膝角标定，手机并未测量你的动作。</p>
              <p>少量输入的留人检验：把真实实验的峰值膝屈和时长选到手机的三档设置，再加体重预测净关节力矩。12 人 39 次自重深蹲中，右髋／右膝逐人误差中位为 ${squatEvidence.manualInputJointMomentValidation['0lbs'].rightHip.coarse_manual.subjectMedianMaeNmPerKg.toFixed(3)}／${squatEvidence.manualInputJointMomentValidation['0lbs'].rightKnee.coarse_manual.subjectMedianMaeNmPerKg.toFixed(3)} N·m/kg；不填这些参数的人群相位曲线为 ${squatEvidence.manualInputJointMomentValidation['0lbs'].rightHip.phaseMedianSubjectMae.toFixed(3)}／${squatEvidence.manualInputJointMomentValidation['0lbs'].rightKnee.phaseMedianSubjectMae.toFixed(3)}。额外 25 lb 条件的对应误差为 ${squatEvidence.manualInputJointMomentValidation['25lbs'].rightHip.coarse_manual.subjectMedianMaeNmPerKg.toFixed(3)}／${squatEvidence.manualInputJointMomentValidation['25lbs'].rightKnee.coarse_manual.subjectMedianMaeNmPerKg.toFixed(3)}，人群曲线为 ${squatEvidence.manualInputJointMomentValidation['25lbs'].rightHip.phaseMedianSubjectMae.toFixed(3)}／${squatEvidence.manualInputJointMomentValidation['25lbs'].rightKnee.phaseMedianSubjectMae.toFixed(3)}。实验动作边界和选档真值对手机都属于有利条件；此方案没有稳定改善跨人误差，不能推断个人关节或单块肌肉发力。</p>
              <div class="joint-study-curves" aria-label="公开实验自重深蹲净关节力矩相位波形">
                ${studyJointMomentChart('右髋 · 源模型坐标', 'rightHip')}
                ${studyJointMomentChart('右膝 · 源模型坐标', 'rightKnee')}
              </div>
              <p class="joint-study-note">曲线为十二人实验逆动力学净力矩的逐相位中位值，纵向按每千克体重计；负号取决于源模型坐标定义。训练人群 10%–90% 带在留出者单次动作中仅覆盖髋 ${Math.round(squatEvidence.phaseJointMomentValidation.rightHip.repetitionWeightedP10P90Coverage * 100)}%、膝 ${Math.round(squatEvidence.phaseJointMomentValidation.rightKnee.repetitionWeightedP10P90Coverage * 100)}% 的点，因此不画作个人误差带。尝试仅用体重修正，髋误差中位只从 ${squatEvidence.phaseJointMomentValidation.rightHip.subjectMedianPhaseMaeNmPerKg.toFixed(2)} 变为 ${squatEvidence.phaseJointMomentValidation.rightHip.subjectMedianMassAdjustedMaeNmPerKg.toFixed(2)} N·m/kg，膝则从 ${squatEvidence.phaseJointMomentValidation.rightKnee.subjectMedianPhaseMaeNmPerKg.toFixed(2)} 变为 ${squatEvidence.phaseJointMomentValidation.rightKnee.subjectMedianMassAdjustedMaeNmPerKg.toFixed(2)}；当前不把体重修正当作个人力矩。这也不是当前杠铃重量下你的关节净力矩，更不能分解为单块肌肉力量。</p>
              <p>预测验收：留出整名受试者测试后，仅用体重、负重、膝角和动作阶段预测右髋／右膝净力矩，R² 为 ${squatEvidence.heldOutPrediction.hipR2.toFixed(2)}／${squatEvidence.heldOutPrediction.kneeR2.toFixed(2)}；起身时膝力矩的负重变化方向只判断对 ${squatEvidence.heldOutPrediction.ascentKneeLoadDirectionCorrect}/${squatEvidence.heldOutPrediction.ascentKneeLoadParticipants} 人。此误差不支持个人发力高亮。</p>
              <p>手机预设动作检查：${squatEvidence.templateGrf.subjects} 人 ${squatEvidence.templateGrf.reps} 次自重深蹲，用实验动作起止点对齐后，${squatEvidence.templateGrf.defaultDurationS.toFixed(1)} 秒示意轨迹的整体竖直力误差约为体重的 ${squatEvidence.templateGrf.fixedTemplateMaeRatio.toFixed(3)}（原型默认约 ${Math.round(squatEvidence.templateGrf.viewerMaxKneeFlexionDeg)}° 膝屈）与 ${squatEvidence.templateGrf.deepTemplateMaeRatio.toFixed(3)}（较深 117°）；静态体重基线为 ${squatEvidence.templateGrf.staticMaeRatio.toFixed(3)}。实验逐人峰值膝屈中位约 ${Math.round(squatEvidence.templateGrf.observedMedianPeakKneeFlexionDeg)}°。角度更接近没有改善力板误差；实验动作起止点由研究者标注，手机所选节奏不是测量值。三档幅度都不能据此显示个人负重或肌肉发力。</p>
              <p>独立实验室复查：另用 <a href="${squatEvidence.independentSquatSourceUrl}" target="_blank" rel="noreferrer">GroundLink ↗</a> 的 ${squatEvidence.independentSquatGrf.subjects} 人 ${squatEvidence.independentSquatGrf.reps} 次自重深蹲，在实验骨盆标记划出的每次动作边界内，固定示意轨迹的整体竖直力误差逐人中位为体重的 ${squatEvidence.independentSquatGrf.fixedTemplateMaeRatio.toFixed(3)}，恒定体重基线为 ${squatEvidence.independentSquatGrf.staticMaeRatio.toFixed(3)}，${squatEvidence.independentSquatGrf.fixedBeatsStaticSubjects}/${squatEvidence.independentSquatGrf.subjects} 人改善。换用实验时长缩放的结果对边界门槛敏感；手机没有这些标记与时长，这仍不能验证个人动作、负重或单块肌肉发力。</p>
              <p>额外 25 lb 深蹲复查：同一公开研究的 ${squatEvidence.loadedSquatGrf.subjects} 人 ${squatEvidence.loadedSquatGrf.reps} 次完整重复动作，按“体重＋额外重量”归一后，手机固定示意轨迹的整体竖直力误差逐人中位为总重量的 ${squatEvidence.loadedSquatGrf.fixedTemplateMaeRatio.toFixed(3)}，恒定总重量基线为 ${squatEvidence.loadedSquatGrf.staticMaeRatio.toFixed(3)}，${squatEvidence.loadedSquatGrf.fixedBeatsStaticSubjects}/${squatEvidence.loadedSquatGrf.subjects} 人改善。若身体按示意运动、额外重量只提供恒定重力，误差为 ${squatEvidence.loadedSquatGrf.bodyMotionPlusStaticLoadMaeRatio.toFixed(3)}；给重量也加入示意加速度仅 ${squatEvidence.loadedSquatGrf.barMotionBeatsStaticLoadSubjects}/${squatEvidence.loadedSquatGrf.subjects} 人进一步改善。论文没有说明 25 lb 放在哪里，实验动作边界也不是手机输入；此结果只检查整体支撑力，不能验证杠铃位置、个人关节或肌肉发力。</p>
              <p>已知负重外力复核：另一套<a href="${squatEvidence.knownLoadSupportSourceUrl}" target="_blank" rel="noreferrer">INAIL 双手举箱实验 ↗</a>中，有完整体重和箱重的 ${squatEvidence.knownLoadSupportStudy.participants} 人 ${squatEvidence.knownLoadSupportStudy.trials} 次有效试次。用体重加箱重的静态公式，整体竖直力误差跨人中位为总重的 ${squatEvidence.knownLoadSupportStudy.staticMaeRatio.toFixed(4)}；加入实验标记点测出的箱体加速度后为 ${squatEvidence.knownLoadSupportStudy.measuredAccelerationMaeRatio.toFixed(4)}，${squatEvidence.knownLoadSupportStudy.participantsImproved}/${squatEvidence.knownLoadSupportStudy.participants} 人改善。另两档预设平滑得到 ${squatEvidence.knownLoadSupportStudy.smoothingMaeRange.map(value => value.toFixed(4)).join('／')}，也都是 10/10 人改善。该动作不是杠铃深蹲；手机的预设动画没有测到你的真实加速度，因此这些误差不是个人预测精度，也不能推出单块肌肉力。</p>
              <p>同批举箱试次的人体运动探针：再用实验人体标记点构造粗略质心运动，整体竖直力误差从仅计箱体时的 ${squatEvidence.measuredBodyMotionProbe.boxOnlyMaeRatio.toFixed(4)} 降到 ${squatEvidence.measuredBodyMotionProbe.bodyAndBoxMaeRatio.toFixed(4)} 倍总重，${squatEvidence.measuredBodyMotionProbe.improvedParticipants}/${squatEvidence.measuredBodyMotionProbe.participants} 人改善；仅用骨盆运动则为 ${squatEvidence.measuredBodyMotionProbe.pelvisOnlyMaeRatio.toFixed(4)}，${squatEvidence.measuredBodyMotionProbe.pelvisOnlyImprovedParticipants}/${squatEvidence.measuredBodyMotionProbe.participants} 人改善。体段比例和中心是通用模型近似，手臂与头部被并入躯干；手机没有这些实测运动，不能据此显示个人动力学或肌肉发力。</p>
              <p>节奏选择检查：每轮仅用其余 11 人选 2.0／2.8／4.0 秒预设，再测试留出者，跨人误差中位数为体重的 ${squatEvidence.tempoSelection.heldOutMedianSelectedMaeRatio.toFixed(3)}，高于固定默认 2.8 秒的 ${squatEvidence.tempoSelection.heldOutMedianDefault28sMaeRatio.toFixed(3)}；仅 ${squatEvidence.tempoSelection.selectedBeatsDefaultSubjects}/${squatEvidence.tempoSelection.subjects} 人改善。手机保留默认节奏；选择器只改变示意情景。</p>
              <p>少量参数检查：即使用实验测得的每次峰值膝屈角和真实动作时长选最接近的幅度／节奏预设，整体竖直力误差中位数仍为体重的 ${squatEvidence.twoParameterInputs.bothMeasuredPresetsMaeRatio.toFixed(3)}；仅 ${squatEvidence.twoParameterInputs.bothMeasuredPresetsBeatsDefault}/${squatEvidence.twoParameterInputs.subjects} 人比固定默认改善。实际用户手填值不会比实验测量更精确；这不能验证个人发力。</p>
              <p>支撑点检查：同批双力板自重深蹲中，合成压力中心沿实验室 Z 轴的逐人位移中位约 ${squatEvidence.pressureCenterAudit.medianPlateZExcursionCm.toFixed(1)} cm。另将 ${squatEvidence.pressureCenterAudit.registeredParticipants} 人的 ${squatEvidence.pressureCenterAudit.registeredClips} 段原始标记点重算姿态，与力板对齐；${squatEvidence.pressureCenterAudit.registeredFootTracks} 条单脚轨迹沿各自脚踝到前足方向的位移范围为 ${squatEvidence.pressureCenterAudit.minimumFootForwardExcursionCm.toFixed(1)}–${squatEvidence.pressureCenterAudit.maximumFootForwardExcursionCm.toFixed(1)} cm。用这些实验力板数据计算的踝部外力矩，与同源逆动力学净踝力矩按相反符号逐帧比较，每条轨迹平均绝对差 ${squatEvidence.pressureCenterAudit.maximumPlateToSourceAnkleMaeNm.toFixed(1)} N·m 以下；两者共用实验输入，这只是坐标与主要外力项的复核。若把支撑点固定在踝前 6 cm，即使保留逐帧实测地面反力，八条轨迹的平均绝对差也变为 ${squatEvidence.pressureCenterAudit.minimumFixedCopMeasuredForceMaeNm.toFixed(1)}–${squatEvidence.pressureCenterAudit.maximumFixedCopMeasuredForceMaeNm.toFixed(1)} N·m；再改用静态总重均分、忽略水平力，则为 ${squatEvidence.pressureCenterAudit.minimumFixedCopStaticWeightMaeNm.toFixed(1)}–${squatEvidence.pressureCenterAudit.maximumFixedCopStaticWeightMaeNm.toFixed(1)} N·m。6 cm 取值参考了这四段数据的压力中心中位位置，仍使用实验姿态；这不是独立预测精度。手机没有你的足底压力测量，不能据此给出个人关节净力矩或单块肌肉力。</p>
              <p>支撑点相位模板再检验：${squatEvidence.pressureCenterPhaseTransfer.sourceUnloadedSubjects} 人 ${squatEvidence.pressureCenterPhaseTransfer.sourceUnloadedReps} 次自重深蹲整人留出时，逐人误差中位为固定点 ${squatEvidence.pressureCenterPhaseTransfer.sourceUnloadedFlatMaeCm.toFixed(2)} cm、相位线 ${squatEvidence.pressureCenterPhaseTransfer.sourceUnloadedPhaseMaeCm.toFixed(2)} cm；额外 25 lb 条件分别为 ${squatEvidence.pressureCenterPhaseTransfer.sourceLoadedFlatMaeCm.toFixed(2)}／${squatEvidence.pressureCenterPhaseTransfer.sourceLoadedPhaseMaeCm.toFixed(2)} cm。把自重相位线不作调整地用于独立 <a href="${squatEvidence.independentSquatSourceUrl}" target="_blank" rel="noreferrer">GroundLink ↗</a> 的 ${squatEvidence.pressureCenterPhaseTransfer.externalSubjects} 人 ${squatEvidence.pressureCenterPhaseTransfer.externalReps} 次深蹲，相位线与固定点的跨人误差中位为 ${squatEvidence.pressureCenterPhaseTransfer.externalPhaseMaeCm.toFixed(2)}／${squatEvidence.pressureCenterPhaseTransfer.externalFlatMaeCm.toFixed(2)} cm，${squatEvidence.pressureCenterPhaseTransfer.externalPhaseBetterSubjects}/${squatEvidence.pressureCenterPhaseTransfer.externalSubjects} 人改善。仅替换支撑点、保留实验每脚竖直力时，踝部外力矩相应误差中位为 ${squatEvidence.pressureCenterPhaseTransfer.externalPhaseCopOnlyMomentMaeNm.toFixed(2)}／${squatEvidence.pressureCenterPhaseTransfer.externalFlatCopOnlyMomentMaeNm.toFixed(2)} N·m。两实验的脚部标记和动作分段方法不同；手机没有实测阶段或每脚反力，这些数值不构成个人净关节力矩或肌肉力量验证。</p>
              <p>肌肉力核查：公开的 ${squatEvidence.subjectMuscleParameters.models} 个人体缩放模型中，${squatEvidence.subjectMuscleParameters.unchangedMaxForceMuscles} 条肌肉的最大等长力在受试者间完全相同，未测出个人肌肉强度。对 ${squatEvidence.muscleForceSensitivity.subjects} 人改变求解参数，即使筛去关节力矩残差较大的解，起身臀大肌组的预测负重力最大／最小倍数逐人中位仍为 ${squatEvidence.muscleForceSensitivity.gluteMaxLoadedForceSpreadMedian.toFixed(1)}，股二头肌组为 ${squatEvidence.muscleForceSensitivity.bicepsFemorisLoadedForceSpreadMedian.toFixed(1)}。求解器用了实验净力矩作为输入；这些力值不能用于个人标红。</p>
              <p>关节力矩来源核查：两人自重／额外 25 lb 共 ${squatEvidence.independentIdReplay.conditions} 段原始标记与力板数据独立重算，在不加入力板自由力矩的设置下，右髋、膝、踝共 ${squatEvidence.independentIdReplay.rightHipKneeAnkleComparisons} 项与公开 CSV×体重的平均绝对差最大 ${squatEvidence.independentIdReplay.maximumMeanAbsoluteErrorNm.toFixed(1)} N·m。源作者设置文件未公开；此结果仅支持实验净关节力矩的量纲和外力约定，不验证你的动作或单块肌肉力。</p>
              <p>双腿模型验收：用 ${squatEvidence.bilateralForceGate.subject} 的实测姿态和力板数据求解，${squatEvidence.bilateralForceGate.testedFrames} 帧中有 ${squatEvidence.bilateralForceGate.optimizerFailedFrames} 帧肌肉优化失败。以公开 CSV×体重为力矩目标，两人在最深蹲附近的左右髋旋转共 ${squatEvidence.bilateralForceGate.sourceCsvHipRotationGroupsExceeding} 组、每组 ${squatEvidence.bilateralForceGate.framesPerCapacityGroup} 帧，均超过现有 ${squatEvidence.bilateralForceGate.hipRotationMuscleCount} 肌肉模型主动等长肌肉容量的乐观单关节上界；四组中位需求／容量比最低为 ${squatEvidence.bilateralForceGate.lowestMedianSourceCsvDemandToCapacity.toFixed(1)}。独立复算表明这个上界本身不可解读：在需求方向它只有 ${squatEvidence.bilateralForceGate.hipRotationCapacityNm.toFixed(1)} N·m，反方向却有 ${squatEvidence.bilateralForceGate.hipRotationOppositeDirectionCapacityNm.toFixed(0)} N·m，相差 ${squatEvidence.bilateralForceGate.hipRotationBoundDirectionAsymmetryRatio.toFixed(0)} 倍，因为 ${squatEvidence.bilateralForceGate.hipRotationMuscleCount} 条肌肉中有 ${squatEvidence.bilateralForceGate.hipRotationMusclesWithNegligibleArm} 条在髋旋转上几乎没有力臂，力臂大的髋肌都指向另一侧；承载这个需求的坐标又在最深屈曲下两侧同时抬升并与髋屈曲保持同一比例。所以这条警报应读作「髋旋转坐标在深屈曲下不可解读」，不是「模型缺少肌肉容量」。补上肌肉力-长度关系后，右膝的上界由 ${squatEvidence.bilateralForceGate.kneeMaximumBoundNm.toFixed(1)} 降到 ${squatEvidence.bilateralForceGate.kneeLengthDependentBoundNm.toFixed(0)} N·m：AB01 右膝需求是它的 ${squatEvidence.bilateralForceGate.kneeDemandToLengthBound.toFixed(2)} 倍且 21 帧全部越界，而 AB02 右膝只有 ${squatEvidence.bilateralForceGate.otherSubjectKneeDemandToLengthBound.toFixed(2)} 倍；其中约 ${squatEvidence.bilateralForceGate.hamstringShareOfKneeBoundNm} N·m 来自腿后肌群在超过约 125° 屈膝时才出现的正力臂，不应计入伸膝容量。最稳健的缺口反而是腰椎伸展：两人各 21 帧都超过长度相关上界（最高 ${squatEvidence.bilateralForceGate.lumbarDemandToLengthBound.toFixed(2)} 倍），而模型只有两条竖脊肌负责它，且该模型自己的许可说明写着它的肌肉集是为演示而削减、不适用于研究。换到研究用途的高屈曲模型（80 条下肢肌肉）复核后，那 ${squatEvidence.bilateralForceGate.hamstringShareOfKneeBoundNm} N·m 的腿后肌群正力臂消失（${squatEvidence.bilateralForceGate.crossModelKneeFlexorArtifactNm}），伸膝容量提高 ${squatEvidence.bilateralForceGate.crossModelKneeExtensorRatio} 倍。但候选模型的髌骨几何只到 ${squatEvidence.bilateralForceGate.kneeValidRangeSplineLimitDeg}°（髌股关节三条样条的节点终点，关节坐标上限另有 140°），按帧重算后，${squatEvidence.bilateralForceGate.kneeValidRangeSplineLimitDeg}° 以内两个模型、两个受试者的越界帧数为 ${squatEvidence.bilateralForceGate.kneeValidRangeInsideFramesOverOne}（还原模型最高 ${squatEvidence.bilateralForceGate.kneeValidRangeInsideWorstSourceRatio.toFixed(2)}、候选模型最高 ${squatEvidence.bilateralForceGate.kneeValidRangeInsideWorstCandidateRatio.toFixed(2)}）；AB01 右膝在 ${squatEvidence.bilateralForceGate.kneeValidRangeSplineLimitDeg}° 以外仍为 ${squatEvidence.bilateralForceGate.crossModelKneeDemandToLengthBound.toFixed(2)} 倍（这以外的 ${squatEvidence.bilateralForceGate.kneeValidRangeOutsideFrames} 帧里有 ${squatEvidence.bilateralForceGate.kneeValidRangeOutsideCandidateFramesOverOne} 帧越界，最深帧被上限钳在 ${squatEvidence.bilateralForceGate.crossModelPoseClampedDeg.toFixed(0)}°），而那里候选模型的髌骨几何已在自身数据之外、还原模型膝部又没有髌骨，所以这个缺口只能读作「未决」；AB02 两组都不越界（${squatEvidence.bilateralForceGate.crossModelOtherSubjectKneeDemandToLengthBound.toFixed(2)} 倍）。但用带真正躯干肌群的全身模型（${squatEvidence.bilateralForceGate.lumbarFullBodyMuscleCount} 条肌肉，L5/S1 与源模型腰椎关节高度对齐）复核后，那条缺口消失了：只算真正的脊柱伸肌，容量是还原模型的 ${squatEvidence.bilateralForceGate.lumbarFullBodyErectorRatio} 倍（${squatEvidence.bilateralForceGate.lumbarFullBodyErectorCapacityNm} N·m），需求只占 ${squatEvidence.bilateralForceGate.lumbarFullBodyDemandToCapacity.toFixed(2)}／${squatEvidence.bilateralForceGate.lumbarFullBodyOtherSubjectDemandToCapacity.toFixed(2)}——所以那是还原模型缺躯干肌群，不是人的腰椎力量上限。当前不生成个人肌肉力红色高亮。</p>
              <p>高屈曲模型复查：以原个体模型净力矩投影为目标，80 条肌肉同时承担双髋、双膝和双踝的需求，AB01／AB02 两秒片段各自有 ${squatEvidence.highFlexForceGate.AB01.nominalStrengthFeasibleFrames}/${squatEvidence.highFlexForceGate.AB01.withinKneeRangeFrames}、${squatEvidence.highFlexForceGate.AB02.nominalStrengthFeasibleFrames}/${squatEvidence.highFlexForceGate.AB02.withinKneeRangeFrames} 帧可在名义等长肌力内配平；深屈膝阶段最多需要把当前模型的名义上限放大 ${squatEvidence.highFlexForceGate.AB01.peakRequiredNominalStrengthMultiplier.toFixed(1)}／${squatEvidence.highFlexForceGate.AB02.peakRequiredNominalStrengthMultiplier.toFixed(1)} 倍。强行用 ${squatEvidence.highFlexEmgGate.strengthMultiplier.toFixed(1)} 倍参数求张力后，相比仅看膝屈角，模型与同试次肌电的趋势更接近的对应通道仅为 ${squatEvidence.highFlexEmgGate.subjects.AB01.modelBeatsKneeDepthChannels}/${squatEvidence.highFlexEmgGate.subjects.AB01.comparableChannels}、${squatEvidence.highFlexEmgGate.subjects.AB02.modelBeatsKneeDepthChannels}/${squatEvidence.highFlexEmgGate.subjects.AB02.comparableChannels}。两人数据和任意强度倍率不能校准你的肌肉力量；仍不提供红色发力高亮。</p>
              <p>候选模型自身动力学复核：AB02 深屈膝 ${squatEvidence.highFlexCandidateGate.frames} 帧的右髋旋转力矩需求比原模型投影中位多 ${Math.abs(squatEvidence.highFlexCandidateGate.rightHipRotationCandidateMinusMappedSourceMedianNm).toFixed(1)} N·m。按候选模型自身需求，十轴名义容量的最小统一肌力倍率中位为 ${squatEvidence.highFlexCandidateGate.ownIdNominalStrengthMultiplierMedian.toFixed(2)}，加入固定被动力快照后为 ${squatEvidence.highFlexCandidateGate.ownIdPassiveAdjustedMultiplierMedian.toFixed(2)}；这些不是人的实际力量倍率。完整静态优化以任意 4.2 倍肌力运行仍有 ${squatEvidence.highFlexCandidateGate.staticOptimization4p2FailedFrames}/${squatEvidence.highFlexCandidateGate.frames} 帧未收敛。6 倍时虽无失败警告，双侧股二头肌长头仍有 ${squatEvidence.highFlexCandidateGate.staticOptimization6xSaturatedBicepsFemorisLongHeadFrames}/${squatEvidence.highFlexCandidateGate.frames} 帧达到激活上限，骨盆也需要辅助力。这些数据只定位模型缺口，不能生成你的肌肉发力颜色。</p>
              <small>来源：<a href="${squatEvidence.sourceUrl}" target="_blank" rel="noreferrer">Scherpereel 等，Scientific Data 2023 ↗</a> · <a href="${squatEvidence.licenseUrl}" target="_blank" rel="noreferrer">CC BY 4.0 ↗</a>。实验力矩由 OpenSim 逆动力学计算；当前 App 的个体发力模型尚未通过此对照。</small>
            </div>
          </details>
        </section>
      <section class="card profile-card">
        <div class="section-heading"><span class="step-number">03</span><div><h2>身体参数</h2><p>围度先用于调整外形，不能直接测出单块肌肉大小。</p></div></div>
        <form id="profile-form">
          <div class="field-grid">${fieldHtml}</div>
          <div class="form-footer"><button class="button primary" type="submit">更新模型</button><span id="profile-message" role="status">仅保存在本设备</span></div>
        </form>
        ${measurementDiagramHtml()}
        <div id="profile-calibration" class="profile-calibration" data-output="profile-calibration" data-status="illustrative" data-source="height_scaled_preset_skeleton"></div>
      </section>
      <section class="card training-card">
        <div class="section-heading"><span class="step-number">04</span><div><h2>已有训练记录</h2><p>接近力竭的低次数记录用于动作能力粗估；目前不能据此反推单块肌肉量或发力。</p></div></div>
        <form id="training-form">
          <label class="field"><span>动作</span><select name="exercise">${Object.entries(exercises).map(([id, info]) => `<option value="${id}">${info.label}</option>`).join('')}</select></label>
          <label class="field"><span>器械</span><select name="equipment" aria-label="器械类型">${trainingEquipments.map(item => `<option value="${item.id}"${item.id === 'barbell' ? ' selected' : ''}>${item.label}</option>`).join('')}</select></label>
          <div class="field-grid small">
            <label class="field"><span>重量 kg</span><input name="loadKg" type="number" inputmode="decimal" min="0" max="600" step="0.5" required /></label>
            <label class="field"><span>次数</span><input name="repetitions" type="number" inputmode="numeric" min="1" max="50" step="1" required /></label>
          </div>
          <label class="field"><span>变式</span><select name="variation" id="training-variation" aria-label="动作变式"></select></label>
          <label class="field"><span>实际幅度</span><select name="range" id="training-range" aria-label="实际动作幅度"></select></label>
          <label class="field"><span>做完还可做几次</span><select name="rir"><option value="">不确定</option><option value="0">已力竭</option><option value="1">约 1 次</option><option value="2">约 2 次</option><option value="3">3 次或更多</option></select></label>
          <div class="form-footer"><button class="button primary" type="submit">保存记录</button><span>变式与幅度为自报，仅作记录</span></div>
        </form>
        <div class="training-controls">
          <label class="field"><span>筛选记录</span><select id="training-filter" aria-label="按动作筛选训练记录"><option value="all">全部动作</option>${Object.entries(exercises).map(([id, info]) => `<option value="${id}">${info.label}</option>`).join('')}</select></label>
          <label class="field"><span>搜索记录</span><input id="training-search" type="search" aria-label="按变式、器械、幅度或日期搜索训练记录" placeholder="变式、器械、幅度、日期"></label>
          <label class="field"><span>排序</span><select id="training-sort" aria-label="训练记录排序方式"><option value="recent">最近优先</option><option value="load">重量优先</option><option value="estimate">估算 1RM 优先</option></select></label>
          <button id="training-show-all" type="button" class="button ghost" aria-pressed="false" disabled>显示全部记录</button>
          <small id="training-count" class="training-count"></small>
        </div>
        <div id="training-list" class="training-list" data-output="training-list" data-status="estimate" data-source="epley_with_reserve_reps"></div>
        <details class="lab-evidence">
          <summary>卧推训练记录 · 估算误差对照</summary>
          <div class="lab-evidence-body">
            <p>独立的<a href="${benchCapacityEvidence.sourceArticle}" target="_blank" rel="noreferrer">卧推实验 ↗</a>让 10 名训练者在当天测过 1RM 后，用不同节奏和杠铃配重位置完成力竭组。仅看 80% 1RM、符合本应用 1–10 次范围的 ${benchCapacityEvidence.byNominalLoadPercent['80'].sets} 组：同一估算公式相对实测 1RM 的中位偏差为 ${benchCapacityEvidence.byNominalLoadPercent['80'].setMedianSignedPercent.toFixed(1)}%，其中 ${benchCapacityEvidence.byNominalLoadPercent['80'].setPercentWithinTenPercent.toFixed(1)}% 的组误差在 ±10% 内。</p>
            <p>同一人在规定慢速与快速节奏下的估算值，中位相差 ${benchCapacityEvidence.atEightyPercent.withinSubjectFastMinusSlowEstimatePercent.median.toFixed(1)} 个百分点。每人固定 80% 1RM 的六组全用来汇总时，取最高估算值的逐人绝对误差中位为 ${benchCapacityEvidence.recordAggregationAtEightyPercent.bestSetSubjectMedianAbsoluteErrorPercent.toFixed(1)}%，取六组中位值为 ${benchCapacityEvidence.recordAggregationAtEightyPercent.medianSetSubjectMedianAbsoluteErrorPercent.toFixed(1)}%。这仅解释当前采用“最高记录”的研究依据：同一实验日的六组与日常跨天记录不同，最高值也可能受异常记录影响。</p>
            <p>这批数据没有逐组绝对公斤数，也没有验证“还能做 1–2 次”的填写方式；上述误差不构成你的个人误差范围，更不能推算单块肌肉量或发力。</p>
          </div>
        </details>
      </section>
    </div>

      </div>

    <section class="card backup-card">
      <div class="section-heading"><span class="step-number">05</span><div><h2>本地数据备份</h2><p>身体参数和训练记录只保存在这台设备。换手机或清除应用数据前，可以导出 JSON 备份。</p></div></div>
      <p class="backup-message">本应用没有账号、统计或广告：代码里只有一处网络请求，读的是安装包里自带的深蹲参考数据；整包清单也只有联网权限（Capacitor 的 WebView 用它加载打包资源），且系统云备份已关闭。页面里出现的外部网址都是参考资料链接，要你自己点开才会访问。数据只在你按“导出备份”时写出。</p>
      <div class="backup-actions">
        <button id="backup-export" type="button" class="button ghost">导出备份</button>
        <button id="backup-import" type="button" class="button ghost">导入备份</button>
        <input id="backup-file" type="file" accept=".json,application/json" hidden />
      </div>
      <p id="backup-message" class="backup-message" role="status">备份文件包含你填写的身体数据和训练记录，请自行保管。</p>
    </section>

    <footer class="footer"><strong>模型说明</strong><p>动作示意由 Blender 网格模板与简化运动学构成，尚未完成解剖校验。解剖参考来自 BodyParts3D 与 Z-Anatomy，依据 CC BY-SA 4.0 提供。默认参考层仅用于静态识别；研究叠加层让右腿六块骨网格及臀大肌、股直肌、股二头肌短头、半膜肌、股中间肌、胫骨前肌、比目鱼肌、腓肠肌内侧头八块网格随 OpenSim 深蹲运动。大腿四块网格可按大腿围、小腿三块可按小腿围调整横向厚度，但不能分辨各肌肉体积。骨骼仅按站立包围盒中心配准，肌肉仅用启发式形变传递路径运动；未验证真实附着点、关节面或肌肉发力。卧推、实力举参考路径改编自 Seth 等人的胸廓—肩胛模型及 Belli 等人的修改版（CC BY 4.0）；仅显示单侧研究模型在人工拟合或扫掠姿态中的路径和力臂，未验证真实杠铃动作。卧推与实力举还可选看右臂三骨、肱二头肌长头和三角肌三束候选网格；卧推和实力举的胸大肌三束均显示候选解剖网格逐帧研究层：骨网格用端部切片中心拟合肩、肘、手点，肱二头肌网格按肱骨刚体和模型路径作小幅形变，放松臂围仅调整该网格的横向厚度示意；胸大肌候选网格采用四代理点起点配准和路径端点形变，三角肌候选网格采用肱骨代理配准和近端路径修正，均未独立验证解剖位置；路径颜色只表示模型长度变化，不是解剖标志点、关节面、肌纤维应变或肌肉力量验证。负重力学视图计算杠铃重力外力矩；卧推另给出假设侧向手力对单侧外力矩的敏感性，不显示未经验证的单肌肉发力数值。</p><a href="https://github.com/Z-Anatomy/Models-of-human-anatomy" target="_blank" rel="noreferrer">Z-Anatomy 与来源署名 ↗</a> · <a href="https://github.com/ComputationalBiomechanicsLab/rmr-solver" target="_blank" rel="noreferrer">肩胛模型来源 ↗</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">肩胛模型许可 ↗</a> · <a href="https://doi.org/10.3389/fnbot.2019.00090" target="_blank" rel="noreferrer">原始研究 ↗</a> · <a href="https://github.com/opensim-org/opensim-core" target="_blank" rel="noreferrer">计算路线参考：OpenSim ↗</a><span id="build-identity" class="build-identity"></span></footer>
  </main>
`;

const get = <T extends HTMLElement>(selector: string): T => {
  const found = document.querySelector<T>(selector);
  if (!found) throw new Error(`找不到元素：${selector}`);
  return found;
};
const anatomy = new AnatomyPrototype(get('#viewer'), () => updateView());
const timeline = get<HTMLInputElement>('#timeline');
const loadInput = get<HTMLInputElement>('#load-input');
const cycleDurationInput = get<HTMLSelectElement>('#cycle-duration');
cycleDurationInput.value = String(cycleDurationS);
const benchTempoInput = get<HTMLSelectElement>('#bench-tempo');
benchTempoInput.value = benchTempoMode;
const squatBarOffsetInput = get<HTMLSelectElement>('#squat-bar-offset');
squatBarOffsetInput.value = String(squatBarOffsetCm);
const squatDepthInput = get<HTMLSelectElement>('#squat-depth');
squatDepthInput.value = squatDepthDeg === undefined ? '' : String(squatDepthDeg);
const playButton = get<HTMLButtonElement>('#play-button');
const profileForm = get<HTMLFormElement>('#profile-form');
const trainingForm = get<HTMLFormElement>('#training-form');

// Variant and range options are per exercise, so the two selects follow the form's action field.
function syncTrainingOptionFields(): void {
  const exerciseSelect = trainingForm.querySelector<HTMLSelectElement>('[name="exercise"]');
  const current = (exerciseSelect?.value ?? 'squat') as ExerciseId;
  const options = (values: readonly string[]) => '<option value="">未记录</option>' +
    values.map(item => `<option value="${item}">${item}</option>`).join('');
  get<HTMLSelectElement>('#training-variation').innerHTML =
    options(trainingVariations[current] ?? trainingVariations.squat);
  get<HTMLSelectElement>('#training-range').innerHTML =
    options(trainingRanges[current] ?? trainingRanges.squat);
}
syncTrainingOptionFields();
trainingForm.querySelector('[name="exercise"]')?.addEventListener('change', syncTrainingOptionFields);

// Filtering, searching, sorting and expanding the record list: display only, and deliberately not persisted.
const trainingFilterSelect = get<HTMLSelectElement>('#training-filter');
const trainingShowAllButton = get<HTMLButtonElement>('#training-show-all');
const trainingSearchInput = get<HTMLInputElement>('#training-search');
const trainingSortSelect = get<HTMLSelectElement>('#training-sort');
trainingFilterSelect.addEventListener('change', () => {
  trainingFilter = trainingFilterSelect.value as ExerciseId | 'all';
  renderTraining();
});
trainingSearchInput.addEventListener('input', () => {
  trainingQuery = trainingSearchInput.value.trim();
  renderTraining();
});
trainingSortSelect.addEventListener('change', () => {
  trainingSort = trainingSortSelect.value as typeof trainingSort;
  renderTraining();
});
trainingShowAllButton.addEventListener('click', () => {
  trainingShowAll = !trainingShowAll;
  renderTraining();
});
const backupFile = get<HTMLInputElement>('#backup-file');
get('#muscle-summary').addEventListener('click', event => {
  const expand = (event.target as HTMLElement).closest<HTMLButtonElement>('[data-expand-muscles]');
  if (expand) {
    showAllTsmMuscles = !showAllTsmMuscles;
    updateView();
    return;
  }
  const target = (event.target as HTMLElement).closest<HTMLButtonElement>('[data-muscle]');
  if (!target?.dataset.muscle) return;
  selectedOpenSimMuscle = target.dataset.muscle;
  updateView();
});
get('#muscle-summary').addEventListener('change', event => {
  const target = event.target as HTMLSelectElement;
  if (target.id !== 'illustrative-muscle-picker' || !anatomy.muscleNames.includes(target.value)) return;
  selectedIllustrativeMuscle = target.value;
  updateView();
});

async function loadOpenSimLookup(id: ReferenceExercise): Promise<void> {
  if (opensimLookups[id] || opensimLoading.has(id) || opensimErrors.has(id)) return;
  opensimLoading.add(id);
  try {
    const response = await fetch(id === 'squat' ? '/data/squat_opensim_reference.json'
      : id === 'bench' ? '/data/bench_tsm_reference.json' : '/data/press_tsm_reference.json');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const parsed = await response.json() as OpenSimLookup;
    if (parsed.schemaVersion !== (id === 'squat' ? 3 : 2) ||
        parsed.status !== (id === 'squat' ? 'reference_model_kinematics_only'
          : id === 'bench' ? 'bench_research_kinematics_only' : 'shoulder_research_kinematics_only') ||
        parsed.frames.length !== 101 || !Number.isFinite(parsed.maximumPolylineErrorM) ||
        parsed.maximumPolylineErrorM > 0.005 ||
        parsed.frames.some(frame => !frame.viewerJointsM ||
          Object.values(frame.muscles).some(muscle => !Array.isArray(muscle.viewerPathM)))) {
      throw new Error('参考数据格式不符');
    }
    opensimLookups[id] = parsed;
  } catch (error) {
    opensimErrors.add(id);
    console.error('OpenSim 参考数据加载失败', error);
  } finally {
    opensimLoading.delete(id);
    updateView();
  }
}

function updateView(): void {
  get<HTMLDetailsElement>('#lab-evidence').hidden = exercise !== 'squat' || referenceMode;
  get<HTMLDetailsElement>('#press-evidence').hidden = exercise !== 'press' || referenceMode;
  if (exercise === 'press' && !referenceMode) {
    if (pressTrajectoryProfile !== profile) {
      const samples = Array.from({ length: 101 }, (_, index) => createPose(profile, 'press', index / 200));
      const modelVerticalCm = 100 * (samples[100].wristR.y - samples[0].wristR.y);
      const sagittalCm = samples.map(pose => 100 * (pose.wristR.z - pose.shoulderR.z));
      const modelApCm = Math.max(...sagittalCm) - Math.min(...sagittalCm);
      pressTrajectoryDescription = `你当前输入生成的示意杠铃上推：竖直位移 ${modelVerticalCm.toFixed(1)} cm，前后位移 ${modelApCm.toFixed(1)} cm。公开实验中 ${standingPressStudy.participants} 名训练男性（平均身高 ${standingPressStudy.meanHeightCm.toFixed(1)} cm），以约 ${standingPressStudy.loadPercentOneRm}% 1RM 完成站姿杠铃肩推；其组均值 ± 标准差分别为 ${standingPressStudy.barbellAscentVerticalRangeCm.mean.toFixed(1)} ± ${standingPressStudy.barbellAscentVerticalRangeCm.sd.toFixed(1)} cm 和 ${standingPressStudy.barbellAscentAnteriorPosteriorRangeCm.mean.toFixed(1)} ± ${standingPressStudy.barbellAscentAnteriorPosteriorRangeCm.sd.toFixed(1)} cm。`;
      pressTrajectoryProfile = profile;
    }
    get('#press-trajectory-comparison').textContent = pressTrajectoryDescription;
  }
  const studyBenchTempo = exercise === 'bench' && benchTempoMode !== 'teaching';
  get('#cycle-duration-control').hidden = referenceMode || studyBenchTempo;
  get('#cycle-duration-note').hidden = referenceMode || studyBenchTempo;
  get('#bench-tempo-control').hidden = referenceMode || exercise !== 'bench';
  const benchVelocityNote = get('#bench-velocity-note');
  benchVelocityNote.hidden = exercise !== 'bench' || referenceMode;
  if (exercise === 'bench' && !referenceMode) {
    const timing = benchPlaybackTiming(benchTempoMode, profile.heightCm, cycleDurationS);
    const timingDescription = benchTempoMode === 'teaching'
      ? `当前人工轨迹按 ${cycleDurationS.toFixed(1)} 秒对称播放，起举平均速度约 ${timing.meanAscentMPerS.toFixed(2)} m/s。`
      : `当前人工轨迹按实验逐次起举速度中位数播放：下放固定 ${timing.descentS.toFixed(1)} 秒（人为假设），起举 ${timing.ascentS.toFixed(2)} 秒，整组约 ${timing.totalS.toFixed(2)} 秒。起举平均速度约 ${timing.meanAscentMPerS.toFixed(2)} m/s。`;
    benchVelocityNote.innerHTML = `速度量级审查：${timingDescription}<a href="${benchVelocityBenchmark.sourceData}" target="_blank" rel="noreferrer">公开实验逐次数据 ↗</a>的线性位移传感器中位数在自报 1RM 的 50%／75% 时分别为 ${benchVelocityBenchmark.measured.fiftyPercentOneRmLpt.medianMPerS.toFixed(2)}／${benchVelocityBenchmark.measured.seventyFivePercentOneRmLpt.medianMPerS.toFixed(2)} m/s。负重百分比与个人动作未配准，节奏只供观察长度变化，不能推断肌肉发力。`;
  }
  const segments = profileSegmentDimensions(profile);
  get('#profile-calibration').innerHTML = `<strong>示意骨架标定</strong><span>股骨 ${(segments.femurM * 100).toFixed(1)} cm · 胫骨 ${(segments.tibiaM * 100).toFixed(1)} cm · 躯干 ${(segments.torsoM * 100).toFixed(1)} cm</span><span>上臂 ${(segments.upperArmM * 100).toFixed(1)} cm · 前臂 ${(segments.forearmM * 100).toFixed(1)} cm</span><small>按身高保持站立总高度；内侧腿长用于腿段比例，臂展扣除示意肩宽后用于手臂比例。两者都不是实测骨长。臂围、胸围、腰围、大腿围、小腿围改变示意外轮廓及对应部位的示意肌腹粗细，不能确定单块肌肉体积。OpenSim 骨骼与路径按身高缩放；研究层四块大腿网格按大腿围、三块小腿网格按小腿围、上臂肱二头肌长头网格按放松臂围调整横向外形。胸围改变卧推与实力举胸大肌研究网格的局部宽度，不校准胸大肌力量。</small>`;
  const referenceId = exercise;
  const studySquatDemand = !referenceMode && view === 'demand' && exercise === 'squat' && squatDemandMode === 'study';
  const studyMoments = studySquatDemand ? squatStudyJointMoments(phase) : [];
  get('#squat-demand-mode-control').hidden = referenceMode || view !== 'demand' || exercise !== 'squat';
  get<HTMLSelectElement>('#squat-demand-mode').value = squatDemandMode;
  get('#load-control').hidden = referenceMode || studySquatDemand;
  get('#load-effect-note').hidden = referenceMode || studySquatDemand;
  get('#capacity-hint').hidden = referenceMode || studySquatDemand;
  const viewerReadout = get('#viewer-research-readout');
  viewerReadout.hidden = !studySquatDemand;
  if (studySquatDemand) {
    viewerReadout.innerHTML = `<strong>紫环 · 12 人自重研究参考</strong><span>${studyMoments.map(item =>
      `右${item.joint} ${item.momentNmPerKg >= 0 ? '+' : ''}${item.momentNmPerKg.toFixed(3)}`
    ).join('　')} N·m/kg</span><small>净关节力矩中位 · 非个人肌肉发力</small>`;
  }
  const lookup = opensimLookups[referenceId];
  const opensimFrame = (view === 'opensim' || (view === 'demand' && exercise === 'bench')) && lookup
    ? lookup.frames[Math.round(phase * 100)] : undefined;
  const momentOverlay: JointMomentOverlay = referenceMode || view !== 'demand' ? []
    : exercise === 'bench' ? opensimFrame ? (() => {
      const median = benchBarbellMomentScenarios(opensimFrame, profile.heightCm,
        loads.bench, [benchMedianLateralPercent / 100])[0];
      return [{ joint: '肩', source: 'barbell' as const, magnitudeNm: median.shoulderMomentNm },
        { joint: '肘', source: 'barbell' as const, magnitudeNm: median.elbowMomentNm }];
    })() : []
      : studySquatDemand
        ? studyMoments.map(item => ({
          joint: item.joint, source: 'study' as const, magnitudeNmPerKg: Math.abs(item.momentNmPerKg),
        }))
        : barbellGravityMoments(profile, exercise, phase, loads[exercise],
          squatBarOffsetCm, squatDepthDeg).map(item => ({
          joint: item.joint, source: 'barbell' as const, magnitudeNm: item.momentNm,
        }));
  const displayedLoadKg = studySquatDemand ? 0 : loads[exercise];
  const displayedBarOffsetCm = studySquatDemand ? 0 : squatBarOffsetCm;
  const displayedSquatDepthDeg = studySquatDemand ? undefined : squatDepthDeg;
  const values = anatomy.update(profile, exercise, phase, view, showBones, showMuscles,
    displayedLoadKg, opensimFrame, selectedOpenSimMuscle, lookup?.frames[0], displayedBarOffsetCm,
    selectedIllustrativeMuscle, displayedSquatDepthDeg, registeredColorMode, momentOverlay, showOutline,
    poseOverrides);
  get('#squat-bar-control').hidden = exercise !== 'squat' || referenceMode || view === 'opensim' || studySquatDemand;
  get('#squat-bar-note').hidden = exercise !== 'squat' || referenceMode || view === 'opensim' || studySquatDemand;
  get('#squat-depth-control').hidden = exercise !== 'squat' || referenceMode || view === 'opensim' || studySquatDemand;
  get('#squat-depth-note').hidden = exercise !== 'squat' || referenceMode || view === 'opensim' || studySquatDemand;
  if (exercise === 'squat' && !referenceMode && view !== 'opensim' && !studySquatDemand) {
    const currentKnee = squatKneeFlexionDeg(createPose(profile, 'squat', phase, displayedBarOffsetCm, displayedSquatDepthDeg));
    const deepestKnee = squatKneeFlexionDeg(createPose(profile, 'squat', 0.5, displayedBarOffsetCm, displayedSquatDepthDeg));
    get('#squat-depth-note').textContent = `模型当前膝屈约 ${Math.round(currentKnee)}°，最深约 ${Math.round(deepestKnee)}°。这是预设骨架角度，不是对你动作的测量或发力验证。`;
  }
  const registeredToggle = get<HTMLInputElement>('#registered-bones-toggle');
  registeredToggle.disabled = referenceMode || view !== 'opensim' || exercise !== 'squat';
  get('#tsm-upper-bones-control').hidden = referenceMode || view !== 'opensim' || exercise === 'squat';
  get<HTMLInputElement>('#tsm-upper-bones-toggle').disabled = referenceMode || view !== 'opensim' || exercise === 'squat';
  get('#registered-color-control').hidden = referenceMode || view !== 'opensim' || exercise !== 'squat'
    || !registeredBonesMode || !anatomy.registeredBonesLoaded;
  get('#asset-tag').textContent = referenceMode
    ? anatomy.referenceLoaded ? 'Z-Anatomy · 静态参考' : anatomy.referenceError ? '解剖模型加载失败' : '解剖模型加载中'
    : (view === 'opensim' || (view === 'demand' && exercise === 'bench')) && referenceId
      ? lookup ? exercise === 'squat'
        ? registeredBonesMode && anatomy.registeredBonesLoaded ? 'Z-Anatomy 六块骨骼＋八块肌肉 · 研究叠加' : 'OpenSim · 单侧计算模型'
        : tsmUpperBonesMode && view === 'opensim' && anatomy.tsmUpperBonesLoaded
          ? '胸肩模型＋右臂三骨／肱二头肌／胸大肌／三角肌研究网格'
          : '胸廓—肩胛模型 · 单侧研究'
        : opensimErrors.has(referenceId) ? 'OpenSim 数据加载失败' : 'OpenSim 数据加载中'
    : anatomy.assetLoaded ? 'Blender 5.1 模型 · 示意' : anatomy.assetError ? '模型加载失败 · 使用备用几何' : 'Blender 模型加载中';
  timeline.value = String(Math.round(phase * 100));
  get('#phase-label').textContent = `${Math.round(phase * 100)}%`;
  document.querySelectorAll<SVGLineElement>('[data-emg-phase-marker], [data-joint-phase-marker]').forEach(marker => {
    const x = String(8 + phase * 284);
    marker.setAttribute('x1', x);
    marker.setAttribute('x2', x);
  });
  get('#exercise-cue').textContent = exercises[exercise].cue;
  const capacities = training.filter(entry => entry.exercise === exercise)
    .map(estimatedOneRepMax).filter((value): value is number => value !== undefined);
  get('#capacity-hint').textContent = capacities.length
    ? `当前重量约为已录入记录中最高估算 1RM 的 ${Math.round(loads[exercise] / Math.max(...capacities) * 100)}%。这是动作级粗估，不能据此推断单块肌肉力量。`
    : '录入接近力竭的训练记录后，可显示当前重量相对动作级估算能力的比例。';
  get('#model-status').textContent = poseEditMode ? '自由摆姿 · OpenSim 路径近似'
    : referenceMode ? '静态解剖参考 · 身高与局部围度外形示意'
    : view === 'length' ? '路径长度示意' : view === 'opensim'
      ? exercise === 'squat'
        ? registeredBonesMode && anatomy.registeredBonesLoaded
          ? '右腿六块骨骼＋八块肌肉研究形变 · 大腿／小腿围外形' : 'OpenSim 参考 · 右腿 · 身高比例缩放'
        : tsmUpperBonesMode && anatomy.tsmUpperBonesLoaded
          ? '右臂三骨＋肱二头肌／胸大肌／三角肌研究网格'
          : '肩胛—肩臂参考 · 右侧 · 身高比例缩放'
      : exercise === 'bench' ? '卧推单侧杠铃外力矩情景 · 橙环标关节'
        : studySquatDemand ? '公开自重深蹲净关节力矩参考 · 紫环标关节'
          : '杠铃重力力臂 · 橙环标关节';
  timeline.disabled = referenceMode || poseEditMode;
  playButton.disabled = referenceMode || poseEditMode;
  get('#viewer-instruction').textContent = poseEditMode
    ? '拖动彩色圆点摆姿势 · 空白处旋转 · 滚轮缩放' : '拖动旋转 · 滚轮缩放';
  get<HTMLButtonElement>('#pose-edit-toggle').setAttribute('aria-pressed', String(poseEditMode));
  get<HTMLButtonElement>('#pose-edit-toggle').textContent = poseEditMode ? '结束自由摆姿' : '自由摆姿';
  get<HTMLButtonElement>('#pose-edit-toggle').disabled = referenceMode;
  get('#pose-reset').hidden = !poseEditMode;
  get('#pose-edit-note').hidden = !poseEditMode;
  document.querySelectorAll<HTMLButtonElement>('[data-exercise]').forEach(button => {
    const isCurrent = button.dataset.exercise === exercise;
    button.classList.toggle('selected', isCurrent);
    // The tab look is a class; screen readers need the state itself.
    button.setAttribute('aria-pressed', String(isCurrent));
  });
  document.querySelectorAll<HTMLButtonElement>('[data-view]').forEach(button => {
    const isCurrent = button.dataset.view === view;
    button.classList.toggle('selected', isCurrent);
    button.setAttribute('aria-pressed', String(isCurrent));
    button.disabled = referenceMode;
  });
  if (referenceMode) {
    get('#view-explanation').innerHTML = `<span class="status-dot ready"></span><strong>静态解剖参考 · 外形示意</strong><p>按身高 ${profile.heightCm} cm 将整套骨骼与肌肉等比例缩放；来源网格缺少完整头部，画面高度不等于你的身高测量。左右上臂、胸大肌三束、腹外斜肌与腹直肌、大腿、小腿的局部中段宽度分别为参考的 ${registeredArmThicknessScale(profile).toFixed(2)}／${registeredChestThicknessScale(profile).toFixed(2)}／${registeredWaistThicknessScale(profile).toFixed(2)}／${registeredThighThicknessScale(profile).toFixed(2)}／${registeredCalfThicknessScale(profile).toFixed(2)} 倍。围度未填时用身高、体重、体脂生成示意默认值；已填围度只改变对应网格的视觉厚度，两端保留原位。胸围和腰围不能分出胸肌或腹肌体积，也未校准附着点。参考层不随动作变化、不计算收缩或发力。素材：BodyParts3D / Z-Anatomy，CC BY-SA 4.0。</p>`;
    const selected = anatomy.selectedReferenceName &&
      (anatomy.selectedReferenceIsBone ? showBones : showMuscles);
    get('#muscle-summary').innerHTML = selected
      ? '<div class="moment-detail"><strong id="reference-selected-name"></strong><small>黄色只表示选中结构；围度外形不是该肌肉体积或激活的测量。</small></div>'
      : '<div class="empty-state">点选模型中的骨骼或肌肉查看名称；拖动可旋转。</div>';
    if (selected) get('#reference-selected-name').textContent = referenceDisplayName(anatomy.selectedReferenceName);
    return;
  }
  if (poseEditMode) {
    const state = JSON.parse(get('#viewer').dataset.dynamicMuscles ?? '{}') as
      { count?: number; longer?: number; shorter?: number };
    get('#view-explanation').innerHTML = '<span class="status-dot ready"></span><strong>自由摆姿 · 肌肉路径几何估计</strong><p>拖动手腕或脚踝圆点，肘和膝由两段骨骼长度约束求出。蓝色表示路径变长，紫色表示变短；对比的是进入编辑时的当前预设姿势。下肢 OpenSim 路径点随所属骨段刚性移动，但未重新求解肌肉包裹面。上肢和躯干仍用简化示意路径。颜色不表示肌肉激活、收缩力或真实肌纤维应变。</p>';
    const illustrativeChanged = values.filter(item => Math.abs(item.ratio - 1) > 0.025);
    get('#muscle-summary').innerHTML = `<div class="summary-title">自由摆姿 · 几何路径</div><div class="muscle-row"><span>OpenSim 下肢路径</span><strong>${state.count ?? 0} 条</strong></div><div class="muscle-row"><span>下肢路径变长超过 2.5%</span><strong class="longer">${state.longer ?? 0} 条</strong></div><div class="muscle-row"><span>下肢路径变短超过 2.5%</span><strong class="shorter">${state.shorter ?? 0} 条</strong></div><div class="muscle-row"><span>上肢／躯干示意路径有变化</span><strong>${illustrativeChanged.length} / ${values.length} 条</strong></div><div class="moment-detail"><small>路径点随骨段刚性移动；包裹面、接触与发力尚未计算。点击结束后可继续播放预设动作。</small></div>`;
    return;
  }
  if (view === 'demand') {
    if (studySquatDemand) {
      get('#view-explanation').innerHTML = `<span class="status-dot ready"></span><strong>公开实验 · 自重深蹲净关节力矩</strong><p><span class="legend study-moment"></span>紫色关节环放在无杠铃的默认示意姿态上，大小取 12 人自重深蹲逐相位中位净力矩的绝对值。实验动作相位由膝角标注，手机时间轴只是示意对齐；数值保留源模型符号和 N·m/kg 单位，不乘你的体重，也不随杠铃重量、围度或训练记录改变。右踝留人检验没有优于固定基线，因此只显示右髋和右膝。这是研究样本参考，不是你的关节力矩或单块肌肉发力。</p>`;
      get('#muscle-summary').innerHTML = `<div class="summary-title">12 人自重深蹲 · 右侧净关节力矩中位</div>${studyMoments.map(item =>
        `<div class="muscle-row"><span>右${item.joint}<small>源模型符号；紫环按绝对值显示</small></span><strong>${item.momentNmPerKg >= 0 ? '+' : ''}${item.momentNmPerKg.toFixed(3)} N·m/kg</strong></div>`
      ).join('')}<div class="moment-detail"><small>整人留出检验：右髋／右膝曲线分别在 ${squatEvidence.phaseJointMomentValidation.rightHip.phaseBeatsFlatSubjects}/12、${squatEvidence.phaseJointMomentValidation.rightKnee.phaseBeatsFlatSubjects}/12 人上比固定值更接近，但逐人误差中位仍有 ${squatEvidence.phaseJointMomentValidation.rightHip.subjectMedianPhaseMaeNmPerKg.toFixed(3)}／${squatEvidence.phaseJointMomentValidation.rightKnee.subjectMedianPhaseMaeNmPerKg.toFixed(3)} N·m/kg。查看下方“实验对照”的原始曲线和限制。当前选的 ${loads.squat} kg 杠铃没有进入这组数值；切回橙环可查看另一种杠铃重力情景。</small></div>`;
      return;
    }
    if (exercise === 'bench') {
      get('#view-explanation').innerHTML = `<span class="status-dot pending"></span><strong>卧推 · 手部侧向力敏感性研究</strong><p><span class="legend moment"></span>橙色关节环按研究样本中位侧向手力比例 +${benchMedianLateralPercent.toFixed(1)}% 的假设显示；环越大，表中该关节的单侧杠铃外力矩越大。以单侧参考路径的手、肩、肘位置，计算假定杠铃力对关节的三维外力矩大小 |r × F|。总重量 ${loads.bench} kg 均分到双手；表中手力比例取自研究样本，再代入当前模型作情景计算，没有测量你的握杠力。${lookup ? '' : '正在加载参考轨迹。'}这不是关节净力矩或单块肌肉力量。</p>`;
      if (opensimErrors.has('bench')) {
        get('#muscle-summary').innerHTML = '<div class="empty-state">卧推参考轨迹加载失败，请刷新页面重试。</div>';
        return;
      }
      if (!opensimFrame) {
        get('#muscle-summary').innerHTML = '<div class="empty-state">正在加载卧推参考轨迹…</div>';
        return;
      }
      const observed = benchSampleLateralPercents;
      const observedMedian = benchMedianLateralPercent;
      const sampleRatios = [observed[0], observedMedian, observed[observed.length - 1]];
      const scenarios = benchBarbellMomentScenarios(opensimFrame, profile.heightCm, loads.bench,
        sampleRatios.map(percent => percent / 100));
      const labels = ['样本最低 · 向内', '样本中位 · 向外', '样本最高 · 向外'];
      get('#muscle-summary').innerHTML = `<div class="summary-title">研究手力比例代入 · 单侧杠铃外力矩</div>${scenarios.map((item, index) =>
        `<div class="muscle-row"><span>${labels[index]} ${Math.abs(sampleRatios[index]).toFixed(1)}%<small>肩 ${item.shoulderMomentNm.toFixed(1)} N·m</small></span><strong class="moment-value">${item.elbowMomentNm.toFixed(1)} N·m<small>肘</small></strong></div>`
      ).join('')}<div class="moment-detail"><small>论文补充表 S3：10 名训练者用 16 kg 杠铃，每人平均侧向力占“假定每手竖直力”的比例从 ${observed[0].toFixed(1)}% 到 +${observed[observed.length - 1].toFixed(1)}%，十人的中位数为 +${observedMedian.toFixed(1)}%。竖直手力在论文中按每手 8 kg 假定，没有实测。这里把这些比例代入你选的 ${loads.bench} kg 和人工轨迹，只展示未知手力的敏感性；比例不能跨负重预测，更不是你的施力或发力范围。未加入杠铃加速度、手臂重力和凳面反力。<a href="${benchLateralStudy.source}" target="_blank" rel="noreferrer">论文与补充材料 ↗</a></small></div>`;
      return;
    }
    const moments = barbellGravityMoments(profile, exercise, phase, loads[exercise], squatBarOffsetCm, squatDepthDeg);
    get('#view-explanation').innerHTML = `<span class="status-dot pending"></span><strong>先看杠铃重力，再研究肌肉发力</strong><p><span class="legend moment"></span>橙色关节环标出下表的髋／膝／踝或肩／肘；环越大，当前单侧杠铃重力外力矩分量越大。总重量 ${loads[exercise]} kg 按左右各一半、匀速静态姿态处理。${exercise === 'squat' ? `杠铃相对默认位置${squatBarOffsetCm < 0 ? `向后 ${-squatBarOffsetCm}` : squatBarOffsetCm > 0 ? `向前 ${squatBarOffsetCm}` : '偏移 0'} cm；杠铃和抓握手臂随之移动，髋膝踝与躯干姿态保持不变。` : ''}下方关节表只计算杠铃重力的力臂和外力矩 M = F × d；未计入身体自重、加速度、支撑力或肌肉分担，不能据此判断单块肌肉发力。灰色不表示肌肉不工作。</p>`;
    const balance = exercise === 'squat' ? squatBalanceEstimate(profile, phase, loads.squat, squatBarOffsetCm, squatDepthDeg) : undefined;
    const vertical = balance ? squatVerticalSupportScenario(profile, phase, loads.squat,
      cycleDurationS, squatBarOffsetCm, squatDepthDeg) : undefined;
    const balancePosition = balance ? `${balance.combinedComRelativeAnkleCm < 0 ? '踝后' : '踝前'} ${Math.abs(balance.combinedComRelativeAnkleCm).toFixed(1)} cm` : '';
    get('#muscle-summary').innerHTML = `<div class="summary-title">单侧关节 · 杠铃重力外力矩分量</div>${moments.map(moment =>
      `<div class="muscle-row"><span>${moment.joint}<small>重力力臂 ${moment.leverArmCm.toFixed(1)} cm</small></span><strong>${moment.momentNm.toFixed(1)} N·m</strong></div>`
    ).join('')}<div class="moment-detail"><small>${exercise === 'squat' ? '深蹲取矢状面力臂；' : '取关节到手腕的水平距离；'}杠铃作用点和动作轨迹仍是示意。此处不是关节净力矩，也不是肌肉力量。</small></div>${balance ? `<div class="summary-title">全身＋杠铃 · 静态平衡情景</div><div class="muscle-row"><span>合成重力线<small>相对右踝的水平位置</small></span><strong>${balancePosition}</strong></div><div class="moment-detail"><small>体重 ${profile.weightKg} kg 和杠铃 ${loads.squat} kg 的总重力约 ${balance.totalGravityN.toFixed(0)} N。若此姿态静止且无水平外力，所需地面压力中心须位于合成重力线下方。身体分段质量使用<a href="https://www.nature.com/articles/s41597-023-02840-6" target="_blank" rel="noreferrer">公开 OpenSim 模板 ↗</a>，分段重心按示意骨架近似放置；体脂和围度尚未校准质量分布。没有实测足底压力与加速度，因此这不是你的真实压力中心、关节净力矩或肌肉力量。</small></div>` : ''}${vertical ? `<div class="summary-title">整体竖直支撑力 · 示意加速度情景</div><div class="muscle-row"><span>${cycleDurationS.toFixed(1)} 秒动作周期<small>相当于静态总重力的 ${vertical.ratioToStaticWeight.toFixed(2)} 倍</small></span><strong>${vertical.verticalSupportN.toFixed(0)} N</strong></div><div class="moment-detail"><small>按预设质心轨迹求竖直加速度 ${vertical.accelerationMs2.toFixed(2)} m/s²，再计算质量 ×（重力加速度＋竖直加速度）。当前没有你的真实动作时间、轨迹与足底测量；2.8 秒自重模板在 12 人力板样本中的误差约为体重的 ${squatEvidence.templateGrf.fixedTemplateMaeRatio.toFixed(3)}，25 lb 模板误差约为总重量的 ${squatEvidence.loadedSquatGrf.fixedTemplateMaeRatio.toFixed(3)}。实验重复动作由研究者分段对齐，负重位置不明；其他重量、动作时长及个人动作未验证。这不是你的实测地面反力、关节净力矩或肌肉力量。</small></div>` : ''}`;
    return;
  }
  const registeredColorDescription = registeredColorMode === 'path-length'
    ? '<span class="legend blue"></span>蓝色表示模型肌肉肌腱路径比站姿长超过 2.5%；<span class="legend purple"></span>紫色表示短超过 2.5%；灰色表示变化不超过 2.5%。颜色不是肌纤维应变、激活或力量。'
    : '紫、青、粉、橄榄、绿、橙、浅棕、砖红仅用于区分八块结构。';
  if (view === 'opensim') {
    const upperBoneDescription = tsmUpperBonesMode && exercise !== 'squat'
      ? anatomy.tsmUpperBonesError ? '右臂解剖骨骼加载失败。'
        : anatomy.tsmUpperBonesLoaded
          ? `橙色肱骨、桡骨、尺骨按对应刚体逐帧运动；端部几何代理点最大残差约 1.9 cm。肱二头肌长头网格主体随肱骨运动，两端小幅参考模型路径。三角肌前、中、后三束候选网格随肱骨运动，并对靠近锁骨／肩胛骨的一端作保守路径修正；101 帧粗筛中最远路径至网格表面约 6.9 cm。胸大肌锁骨、胸肋、腹部三束显示解剖候选网格；四个代理点完成起点配准，网格随锁骨／胸廓刚体运动，并按模型路径两端作线性修正。${exercise === 'bench' ? '卧推用 80% 端点修正；101 帧筛查中路径到网格表面最远约 3.5／3.3／4.1 cm。' : '实力举用完整端点修正；101 帧筛查中路径到网格表面最远约 3.0／2.6／3.5 cm。'}${profile.upperArmCm === undefined ? '臂围未填时用身高、体重和体脂生成示意默认值；' : '输入的放松臂围'}让肱二头肌网格相对上臂骨轴的横向厚度示意变为 ${registeredArmThicknessScale(profile).toFixed(2)} 倍；${profile.chestCm === undefined ? '胸围未填，' : '输入的胸围让'}胸部三束研究网格的视觉宽度为 ${registeredChestThicknessScale(profile).toFixed(2)} 倍（限制 0.80–1.20），不能测出胸肌体积。蓝色表示整条路径较起点长超过 2.5%，紫色表示短超过 2.5%，灰粉色表示变化较小。肱二头肌卧推／上举五帧路径到网格表面最远仍约 4.2／3.3 cm；胸肌配准包含中束路径起点，三角肌也只通过粗网格形变门槛；两者均无独立解剖验证。颜色与形变都不是肌纤维应变、肌电或发力验证。`
          : '正在加载右臂解剖骨骼…'
      : '';
    get('#view-explanation').innerHTML = exercise === 'squat'
      ? `<span class="status-dot ready"></span><strong>OpenSim 深蹲参考路径</strong><p>三维骨段和肌肉路径来自同一单侧计算模型；按输入身高相对 175 cm 统一缩放几何。此缩放不识别个人腿长比例或肌肉量。金色只标识选中肌肉，不代表发力；体重、杠铃和训练记录未进入这组数值。${registeredBonesMode ? anatomy.registeredBonesError ? '解剖网格加载失败。' : anatomy.registeredBonesLoaded ? `橙色右腿六块骨骼随刚体运动；髌骨在共同平移之外叠加了下面说的实测恒定偏移，跟骨仍只用共同平移，髌骨五个源路径点与骨面相距约 2.6–3.7 cm；${registeredColorDescription}臀大肌网格随骨盆、大腿四块网格随股骨、小腿胫骨前肌与比目鱼肌网格随胫骨运动，端点部分参考路径位移。${profile.thighCm === undefined ? '大腿围未填时，用身高、体重和体脂生成示意默认值；' : '输入的大腿围'}让四块大腿网格相对股骨轴的横向厚度示意变为 ${registeredThighThicknessScale(profile).toFixed(2)} 倍；${profile.calfCm === undefined ? '小腿围未填时用示意默认值；' : '输入的小腿围'}让胫骨前肌、比目鱼肌与腓肠肌内侧头网格相对胫骨轴的横向厚度示意变为 ${registeredCalfThicknessScale(profile).toFixed(2)} 倍（均限制 0.80–1.20）。围度不能分出单块肌肉体积。列表百分比仍取自 OpenSim 路径，并非网格应变。前三块站立网格切面中心与模型路径最远约差 4.7／5.5／6.7 cm；胫骨前肌路径至网格表面最大约 1.6 cm；比目鱼肌路径的肌腱末端超出候选网格约 8.9 cm；臀大肌约 3.6 cm，臀大肌暂不按腰围缩放。股中间肌网格纵向比它的模型路径长约 13 cm，切面质心筛查给出 13.2 cm，但该质心落在包裹状剖面的外侧，不能当作肌轴；改用路径到网格表面的筛查后，其中位约 2.0 cm、最大约 6.0 cm，与已绑定的半膜肌／股直肌同量级。腓肠肌内侧头表面距离最大约 15.7 cm，看似最差，但按网格高度拆分后：网格范围内的 14 个采样点中位仅约 0.6 cm（八块中最好），越界的 7 个点有约 97% 的差值来自路径越过网格底端继续向下走（即跟腱），不是横向错位；它的模型路径长度约为网格高度的 1.5 倍，因此纵向分数把更长的弧长压缩映射，只是形变启发式。逐帧完整性审计对全部 101 帧逐帧检查：没有任何网格边超出站姿的 0.5–1.5 倍，也没有面翻转或退化面；但形变会在深蹲中段新增相互穿插（最深约 7.6 mm），骨网格自身也从第 3 帧起就相交（股骨与胫骨 97／101 帧），站立姿态本身已有 20 对网格相交，因此“不穿模”这条验收仍未通过。把膝关节间隙按 2–10 mm 逐级开大重测，10 mm 仍留下 81／97 帧股骨－胫骨重叠，所以靠关节间隙修不了，需要逐骨配准（后来证明逐骨常数配准在膝关节也不够，见下）。髌骨改用由 101 帧穿插搜索得到的 28.8 mm 恒定配准偏移（不再只用共同平移）：髌股相交从 87 帧降到 5 帧、髌骨与胫骨从 73 帧降到 0 帧；代价是股直肌网格与髌骨在 67 帧里相接，而髌骨本就位于股四头肌腱内，这一接触未单独验证。股骨－胫骨这一对没有这种便宜可占：把胫骨（连腓骨）的配准按四种常数方案各搜一遍——只平移、只换旋转支点、两者叠加、再加站姿倾角——最好的“只平移”把骨网格相交帧从 173 降到 86 帧（腓骨×股骨整对消失、股骨－胫骨 97／101 → 81／101 帧、深度减约三分之一），却把 8 个胫骨源点到骨面的距离全部推远（胫骨前肌 P3 从 0.38 cm 到 1.79 cm、比目鱼肌 P1 从 0.18 cm 到 1.28 cm），因此没有采纳；只换旋转支点对股骨－胫骨完全无效（仍 97 帧），加倾角虽到 83 帧却新增 20 帧胫骨－跟骨相交，只动腓骨单独搜也只能把 71 帧降到 52 帧。原因是每帧骨骼运动是复合的螺旋运动：其轴离站立膝面中心约 365 mm、且沿轴平移为零，一个常数支点跟不上屈曲角。所以膝关节这条只能靠关节软骨／接触建模，或明确接受刚性骨网格在深屈曲下互相接触。这只是几何筛查，形变不代表发力。` : '正在加载解剖网格…' : ''}</p>`
      : exercise === 'bench'
        ? `<span class="status-dot ready"></span><strong>胸廓—肩胛模型卧推路径研究</strong><p>单侧模型的 33 束肌肉随仰卧肩、肘角度变化；手部轨迹由人工端点拟合，沿卧推凳方向已参考<a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC9658160/" target="_blank" rel="noreferrer">12 人卧推组均轨迹 ↗</a>修正。路径长度和力臂来自 OpenSim，尚未验证个人动作，也未加入双手杠铃、凳面反力或肌肉发力计算。金色只表示选中，长度变化不等于激活。${upperBoneDescription}</p>`
        : `<span class="status-dot ready"></span><strong>胸廓—肩胛模型上举路径研究</strong><p>来自单侧研究模型的 33 束肌肉，含胸大肌、三角肌、前锯肌、斜方肌与肱三头肌长头；按身高统一缩放几何。肩胛和肘关节随人工角度扫掠运动，尚未拟合真实实力举，也没有杠铃、个人肌肉参数或发力求解。金色仅表示选中，长度变化不等于激活。${upperBoneDescription}</p>`;
    if (referenceId && opensimErrors.has(referenceId)) {
      get('#muscle-summary').innerHTML = '<div class="empty-state">参考数据加载失败，请刷新页面重试。</div>';
      return;
    }
    if (!lookup) {
      get('#muscle-summary').innerHTML = '<div class="empty-state">正在加载 OpenSim 参考数据…</div>';
      return;
    }
    const frame = lookup.frames[Math.round(phase * 100)];
    const ratio = (item: OpenSimFrame['muscles'][string]) => item.ratioToStanding ?? item.ratioToStartingPose ?? 1;
    const items = Object.entries(frame.muscles).sort((a, b) => Math.abs(ratio(b[1]) - 1) - Math.abs(ratio(a[1]) - 1));
    const selected = frame.muscles[selectedOpenSimMuscle] ?? items[0][1];
    const labels = exercise === 'squat' ? opensimLabels : tsmLabels;
    const selectedName = frame.muscles[selectedOpenSimMuscle] ? selectedOpenSimMuscle : items[0][0];
    const selectedLabel = labels[selectedName] ?? selectedName;
    const displayedItems = exercise !== 'squat' && !showAllTsmMuscles
      ? items.filter(([name], index) => index < 12 || name === selectedName) : items;
    const geometryScale = profile.heightCm / 175;
    const arm = (coordinate: string) => {
      const value = selected.momentArmsM[coordinate] * geometryScale * 100;
      return `${Math.abs(value) < 0.05 ? '0.0' : value.toFixed(1)} cm`;
    };
    const momentDetails = exercise === 'squat'
      ? `力臂：髋 ${arm('hip_flexion_r')}　膝 ${arm('knee_angle_r')}　踝 ${arm('ankle_angle_r')}`
      : exercise === 'bench'
        ? `力臂：肩平面角 ${arm('plane_elv')}　肩抬举 ${arm('shoulder_elv')}　肘屈伸 ${arm('elbow_flexion')}`
        : `力臂：肩抬举 ${arm('shoulder_elv')}　肩胛上旋 ${arm('scapula_upward_rot')}　肘屈伸 ${arm('elbow_flexion')}`;
    get('#muscle-summary').innerHTML = `<div class="summary-title">相对${exercise === 'squat' ? '站立' : '起始姿态'}的模型路径长度 · 点选肌肉查看力臂</div>${displayedItems.map(([name, item]) => {
      const change = (ratio(item) - 1) * 100;
      const label = labels[name] ?? name;
      return `<button type="button" class="muscle-row muscle-select${name === selectedOpenSimMuscle ? ' active' : ''}" data-muscle="${name}"><span>${label}</span><strong class="${change >= 0 ? 'longer' : 'shorter'}">${change >= 0 ? '+' : ''}${change.toFixed(1)}%</strong></button>`;
    }).join('')}${exercise !== 'squat' ? `<button type="button" class="expand-muscles" data-expand-muscles>${showAllTsmMuscles ? '收起列表' : `查看全部 ${items.length} 束肌肉`}</button>` : ''}<div class="moment-detail"><strong>${selectedLabel} · 模型路径</strong><span>当前长度 ${(selected.lengthM * geometryScale * 100).toFixed(1)} cm</span><span>${momentDetails}</span><small>按身高统一缩放 ×${geometryScale.toFixed(2)}；正负号按模型关节角方向定义，力臂不能单独推出肌肉力量。</small></div>`;
    return;
  }
  get('#view-explanation').innerHTML = '<span class="status-dot ready"></span><strong>几何路径示意</strong><p><span class="legend blue"></span>路径变长 <span class="legend purple"></span>路径变短。此颜色不表示实际肌肉激活或力量。半透明外表层与示意肌腹只按输入围度换算轮廓粗细，可单独关闭以看清骨骼和肌肉路径；它们不代表单块肌肉体积。</p>';
  const changed = values
    .filter(item => Math.abs(item.ratio - 1) > 0.025)
    .sort((a, b) => Math.abs(b.ratio - 1) - Math.abs(a.ratio - 1))
    .slice(0, 4);
  const selected = values.find(item => item.label === selectedIllustrativeMuscle) ?? values[0];
  if (!selected) return;
  const rawDifference = (selected.ratio - 1) * 100;
  const difference = Math.abs(rawDifference) < 0.05 ? 0 : rawDifference;
  const direction = difference > 2.5 ? '变长' : difference < -2.5 ? '变短' : '近似不变';
  get('#muscle-summary').innerHTML = `<label class="illustrative-picker"><span>逐条查看 · ${values.length} 条示意路径</span><select id="illustrative-muscle-picker" aria-label="选择肌肉示意路径">${values.map(item => `<option value="${item.label}"${item.label === selected.label ? ' selected' : ''}>${item.label}</option>`).join('')}</select></label><div class="moment-detail"><strong>${selected.label} · ${direction}</strong><span>当前示意路径 ${(selected.lengthM * 100).toFixed(1)} cm · 动作起点 ${(selected.baselineM * 100).toFixed(1)} cm</span><span>相对起点 ${difference >= 0 ? '+' : ''}${difference.toFixed(1)}%</span><small>所选路径在三维模型中加粗以便识别。躯干和肩胛骨自由度有限，路径不变也不表示不发力；长度与颜色不是肌纤维应变、肌电或肌肉力量。</small></div>${changed.length
    ? `<div class="summary-title changed-title">当前变化较大的示意路径</div>${changed.map(item => `<div class="muscle-row"><span>${item.label}</span><strong class="${item.ratio > 1 ? 'longer' : 'shorter'}">${item.ratio > 1 ? '变长' : '变短'}</strong></div>`).join('')}`
    : '<div class="empty-state">拖动时间轴，查看相对动作起点的路径变化。</div>'}`;
}

// Search over what the row itself shows: the exercise, the equipment label, the self-reported variant and
// range, the date and the numbers. It never looks at the estimate or the pool rule, so searching cannot
// change what the record means.
function matchesTrainingQuery(entry: TrainingEntry): boolean {
  if (trainingQuery === '') return true;
  const haystack = [exercises[entry.exercise].label, trainingEquipmentLabel(entry), entry.variation,
    entry.range, entry.date, String(entry.loadKg), String(entry.repetitions)]
    .filter(Boolean).join(' ').toLowerCase();
  return haystack.includes(trainingQuery.toLowerCase());
}

// Sorting is display order only. `recent` reproduces the previous behaviour exactly — the stored order
// reversed, so the newest record is first and the collapsed list is the newest five. The other two orders
// put the heaviest load (or the highest estimate) first and send records without an estimate last, with
// recency breaking ties.
function orderTrainingMatches(matches: Array<{ entry: TrainingEntry; index: number }>) {
  if (trainingSort === 'load') {
    return [...matches].sort((left, right) =>
      right.entry.loadKg - left.entry.loadKg || right.index - left.index);
  }
  if (trainingSort === 'estimate') {
    return [...matches].sort((left, right) =>
      (estimatedOneRepMax(right.entry) ?? -1) - (estimatedOneRepMax(left.entry) ?? -1) ||
      right.index - left.index);
  }
  return [...matches].reverse();
}

function renderTraining(): void {
  const element = get('#training-list');
  const count = get('#training-count');
  const showAllButton = get<HTMLButtonElement>('#training-show-all');
  const byExercise = training.map((entry, index) => ({ entry, index }))
    .filter(item => trainingFilter === 'all' || item.entry.exercise === trainingFilter);
  const matching = byExercise.filter(item => matchesTrainingQuery(item.entry));
  const ordered = orderTrainingMatches(matching);
  const shown = trainingShowAll ? ordered : ordered.slice(0, 5);
  // The controls say what is hidden instead of letting the five-row limit look like the whole history.
  showAllButton.disabled = matching.length <= 5;
  const sortedTitle = trainingSort === 'load' ? '重量优先'
    : trainingSort === 'estimate' ? '估算 1RM 优先' : '';
  showAllButton.textContent = trainingShowAll
    ? (sortedTitle === '' ? '只显示最近 5 条' : '只显示前 5 条')
    : `显示全部 ${matching.length} 条`;
  showAllButton.setAttribute('aria-pressed', String(trainingShowAll));
  count.textContent = trainingFilter === 'all'
    ? `共 ${training.length} 条记录，当前显示 ${shown.length} 条`
    : `该动作共 ${byExercise.length} 条，当前显示 ${shown.length} 条`;
  if (!training.length) {
    element.innerHTML = '<p class="empty-state">尚无训练记录。</p>';
    return;
  }
  if (!matching.length) {
    element.innerHTML = `<p class="empty-state">${trainingQuery === ''
      ? '这个动作还没有记录。' : '没有匹配这条搜索的记录。'}</p>`;
    return;
  }
  const listTitle = sortedTitle === '' ? (trainingShowAll ? '全部记录' : '最近记录') : sortedTitle;
  element.innerHTML = `<div class="summary-title">${listTitle}</div>${shown.map(item => {
    const entry = item.entry;
    const estimate = estimatedOneRepMax(entry);
    const rirLabel = entry.repsInReserve === undefined ? '接近力竭程度未知'
      : entry.repsInReserve >= 3 ? '至少还可做 3 次'
        : `还可做约 ${entry.repsInReserve} 次`;
    const recordIndex = item.index;
    const detail = [trainingEquipmentLabel(entry), entry.variation, entry.range].filter(Boolean).join(' · ');
    const recordedTime = entry.recordedAt === undefined ? ''
      : new Date(entry.recordedAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    const estimateLabel = estimate === undefined
      ? (entersBarbellCapacityPool(entry) ? '' : ' · 非杠铃器械不进入 1RM 粗估')
      : ` · 估算动作 1RM ≈ ${estimate.toFixed(1)} kg`;
    return `<div class="training-row"><span>${exercises[entry.exercise].label} · ${entry.loadKg} kg × ${entry.repetitions} 次<small>${detail} · ${rirLabel} · ${entry.date}${recordedTime === '' ? '' : ` ${recordedTime}`}${estimateLabel}</small></span><div class="training-actions">${entry.loadKg <= 300 ? `<button type="button" class="use-record-button" data-use-entry="${recordIndex}" aria-label="载入${exercises[entry.exercise].label} ${entry.loadKg} 千克到模型">查看动作</button>` : '<small>超过示意重量上限</small>'}<button type="button" class="delete-button" data-remove="${recordIndex}" aria-label="删除这条记录">×</button></div></div>`;
  }).join('')}`;
  element.querySelectorAll<HTMLButtonElement>('[data-use-entry]').forEach(button => {
    button.addEventListener('click', () => {
      const entry = training[Number(button.dataset.useEntry)];
      if (!entry || entry.loadKg > 300) return;
      loads[entry.exercise] = entry.loadKg;
      localStorage.setItem('muscle-atlas-loads-v1', JSON.stringify(loads));
      if (referenceMode) {
        referenceMode = false;
        get<HTMLButtonElement>('#reference-toggle').textContent = '查看静态解剖参考';
        anatomy.setReferenceMode(false, updateView);
      }
      selectExercise(entry.exercise);
      get('.workspace').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
  element.querySelectorAll<HTMLButtonElement>('[data-remove]').forEach(button => {
    button.addEventListener('click', () => {
      training.splice(Number(button.dataset.remove), 1);
      saveTraining(training);
      renderTraining();
      updateView();
    });
  });
}

function stopPoseEdit(): void {
  if (!poseEditMode) return;
  poseEditMode = false;
  poseOverrides = {};
  anatomy.setPoseEditEnabled(false);
}

get<HTMLButtonElement>('#pose-edit-toggle').addEventListener('click', () => {
  if (poseEditMode) {
    stopPoseEdit();
  } else {
    poseEditMode = true;
    poseOverrides = {};
    playing = false;
    playButton.textContent = '▶ 播放';
    view = 'length';
    anatomy.setPoseEditEnabled(true, (handle, point) => {
      poseOverrides[handle] = point;
      updateView();
    });
  }
  updateView();
});
get<HTMLButtonElement>('#pose-reset').addEventListener('click', () => {
  poseOverrides = {};
  updateView();
});

function selectExercise(next: ExerciseId): void {
  stopPoseEdit();
  exercise = next;
  localStorage.setItem('muscle-atlas-exercise-v1', next);
  loadInput.value = String(loads[exercise]);
  if (view === 'opensim' || (view === 'demand' && exercise === 'bench')) void loadOpenSimLookup(exercise);
  selectedOpenSimMuscle = exercise === 'squat' ? 'vas_int_r' : 'PectoralisMajorThorax_M';
  selectedIllustrativeMuscle = exercise === 'squat' ? '左竖脊肌' : '左胸大肌';
  showAllTsmMuscles = false;
  phase = 0;
  playing = false;
  playButton.textContent = '▶ 播放';
  updateView();
}

document.querySelectorAll<HTMLButtonElement>('[data-exercise]').forEach(button => {
  button.addEventListener('click', () => selectExercise(button.dataset.exercise as ExerciseId));
});
document.querySelectorAll<HTMLButtonElement>('[data-view]').forEach(button => {
  button.addEventListener('click', () => {
    stopPoseEdit();
    view = button.dataset.view as ViewMode;
    if (view === 'opensim' || (view === 'demand' && exercise === 'bench')) void loadOpenSimLookup(exercise);
    updateView();
  });
});
get<HTMLSelectElement>('#squat-demand-mode').addEventListener('change', event => {
  const value = (event.target as HTMLSelectElement).value;
  if (value !== 'barbell' && value !== 'study') return;
  squatDemandMode = value;
  updateView();
});
timeline.addEventListener('input', () => {
  phase = Number(timeline.value) / 100;
  playing = false;
  playButton.textContent = '▶ 播放';
  updateView();
});
function applyLoadInput(finalize: boolean): void {
  if (!finalize && loadInput.value.trim() === '') return;
  const value = Number(loadInput.value);
  if (!Number.isFinite(value) || value < 0 || value > 300) {
    if (finalize) loadInput.value = String(loads[exercise]);
    return;
  }
  loads[exercise] = value;
  localStorage.setItem('muscle-atlas-loads-v1', JSON.stringify(loads));
  updateView();
}
loadInput.addEventListener('input', () => applyLoadInput(false));
loadInput.addEventListener('change', () => applyLoadInput(true));
cycleDurationInput.addEventListener('change', () => {
  const value = Number(cycleDurationInput.value);
  if (![2, demoMotionProtocol.cycleDurationS, 4].includes(value)) return;
  cycleDurationS = value;
  if (value === demoMotionProtocol.cycleDurationS) localStorage.removeItem('muscle-atlas-cycle-duration-s-v1');
  else localStorage.setItem('muscle-atlas-cycle-duration-s-v1', String(value));
  updateView();
});
benchTempoInput.addEventListener('change', () => {
  const value = benchTempoInput.value;
  if (value !== 'teaching' && value !== 'study50' && value !== 'study75') return;
  benchTempoMode = value;
  if (value === 'teaching') localStorage.removeItem('muscle-atlas-bench-tempo-v1');
  else localStorage.setItem('muscle-atlas-bench-tempo-v1', value);
  phase = 0;
  playing = false;
  playButton.textContent = '▶ 播放';
  updateView();
});
squatBarOffsetInput.addEventListener('change', () => {
  const value = Number(squatBarOffsetInput.value);
  if (![-6, 0, 6].includes(value)) return;
  squatBarOffsetCm = value;
  localStorage.setItem('muscle-atlas-squat-bar-offset-cm-v1', String(value));
  updateView();
});
squatDepthInput.addEventListener('change', () => {
  const value = squatDepthInput.value;
  if (!['', '75', '117'].includes(value)) return;
  squatDepthDeg = value === '' ? undefined : Number(value);
  if (value === '') localStorage.removeItem('muscle-atlas-squat-depth-deg-v1');
  else localStorage.setItem('muscle-atlas-squat-depth-deg-v1', value);
  updateView();
});
playButton.addEventListener('click', () => {
  playing = !playing;
  playButton.textContent = playing ? 'Ⅱ 暂停' : '▶ 播放';
  lastFrame = performance.now();
});
get<HTMLInputElement>('#bones-toggle').addEventListener('change', event => {
  showBones = (event.target as HTMLInputElement).checked;
  updateView();
});
get<HTMLInputElement>('#muscles-toggle').addEventListener('change', event => {
  showMuscles = (event.target as HTMLInputElement).checked;
  updateView();
});
get<HTMLInputElement>('#outline-toggle').addEventListener('change', event => {
  showOutline = (event.target as HTMLInputElement).checked;
  updateView();
});
get<HTMLInputElement>('#registered-bones-toggle').addEventListener('change', event => {
  registeredBonesMode = (event.target as HTMLInputElement).checked;
  anatomy.setRegisteredBonesEnabled(registeredBonesMode, updateView);
  updateView();
});
get<HTMLInputElement>('#tsm-upper-bones-toggle').addEventListener('change', event => {
  tsmUpperBonesMode = (event.target as HTMLInputElement).checked;
  anatomy.setTsmUpperBonesEnabled(tsmUpperBonesMode, updateView);
  updateView();
});
get<HTMLSelectElement>('#registered-color-mode').addEventListener('change', event => {
  const value = (event.target as HTMLSelectElement).value;
  if (value !== 'identity' && value !== 'path-length') return;
  registeredColorMode = value;
  updateView();
});
get<HTMLButtonElement>('#reference-toggle').addEventListener('click', () => {
  stopPoseEdit();
  referenceMode = !referenceMode;
  playing = false;
  playButton.textContent = '▶ 播放';
  const button = get<HTMLButtonElement>('#reference-toggle');
  button.textContent = referenceMode ? '返回动作示意' : '查看静态解剖参考';
  anatomy.setReferenceMode(referenceMode, updateView);
  updateView();
});
profileForm.addEventListener('submit', event => {
  event.preventDefault();
  try {
    profile = parseProfile(profileForm);
    saveProfile(profile);
    get('#profile-message').textContent = '已更新并保存在本设备';
    updateView();
  } catch (error) {
    get('#profile-message').textContent = error instanceof Error ? error.message : '输入有误';
  }
});
trainingForm.addEventListener('submit', event => {
  event.preventDefault();
  const data = new FormData(trainingForm);
  const rir = String(data.get('rir') ?? '');
  const variation = String(data.get('variation') ?? '');
  const range = String(data.get('range') ?? '');
  const now = new Date();
  training.push({
    exercise: String(data.get('exercise')) as ExerciseId,
    loadKg: Number(data.get('loadKg')),
    repetitions: Number(data.get('repetitions')),
    repsInReserve: rir === '' ? undefined : Number(rir),
    date: now.toLocaleDateString('zh-CN'),
    variation: variation === '' ? undefined : variation,
    range: range === '' ? undefined : range,
    equipment: (String(data.get('equipment') ?? 'barbell') || 'barbell') as TrainingEquipment,
    recordedAt: now.toISOString(),
  });
  saveTraining(training);
  trainingForm.reset();
  syncTrainingOptionFields();
  // The new record must be visible even if the list was filtered elsewhere or a search is active.
  trainingFilter = 'all';
  trainingFilterSelect.value = 'all';
  trainingQuery = '';
  trainingSearchInput.value = '';
  renderTraining();
  updateView();
});

get<HTMLButtonElement>('#backup-export').addEventListener('click', async () => {
  const message = get('#backup-message');
  try {
    const now = new Date();
    const localDay = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    const name = `肌动图谱备份-${localDay}.json`;
    const data = JSON.stringify(makeLocalBackup(profile, training), null, 2);
    if (Capacitor.isNativePlatform()) {
      const { uri } = await Filesystem.writeFile({
        path: name, data, directory: Directory.Cache, encoding: Encoding.UTF8,
      });
      await Share.share({ title: '肌动图谱本地备份', files: [uri], dialogTitle: '保存或分享备份文件' });
      message.textContent = '已交给系统分享；请确认备份文件已保存。';
      return;
    }
    const file = new File([data],
      name, { type: 'application/json' });
    if (navigator.canShare?.({ files: [file] })) {
      try {
        await navigator.share({ files: [file], title: '肌动图谱本地备份' });
        message.textContent = '已交给系统分享或保存；请确认文件已保存。';
        return;
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
          message.textContent = '已取消导出。';
          return;
        }
      }
    }
    const url = URL.createObjectURL(file);
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    message.textContent = '已请求下载备份；请确认文件已保存。';
  } catch (error) {
    message.textContent = error instanceof Error ? `导出失败：${error.message}` : '导出失败';
  }
});

get<HTMLButtonElement>('#backup-import').addEventListener('click', () => backupFile.click());
backupFile.addEventListener('change', async () => {
  const message = get('#backup-message');
  const file = backupFile.files?.[0];
  backupFile.value = '';
  if (!file) return;
  try {
    if (file.size > 1_000_000) throw new Error('文件超过 1 MB');
    const imported = parseLocalBackup(JSON.parse(await file.text()) as unknown);
    if (!window.confirm(`将用备份中的身体参数和 ${imported.training.length} 条训练记录覆盖本设备现有数据。确认导入？`)) {
      message.textContent = '已取消导入，现有数据未改变。';
      return;
    }
    const previousProfile = profile;
    try {
      saveProfile(imported.profile);
      saveTraining(imported.training);
    } catch (error) {
      saveProfile(previousProfile);
      throw error;
    }
    profile = imported.profile;
    training = imported.training;
    for (const field of bodyFields) {
      const input = profileForm.elements.namedItem(field.key);
      if (input instanceof HTMLInputElement) input.value = String(profile[field.key] ?? '');
    }
    // Imported data replaces everything, so the list goes back to showing all actions, unsorted.
    trainingFilter = 'all';
    trainingFilterSelect.value = 'all';
    trainingShowAll = false;
    trainingQuery = '';
    trainingSearchInput.value = '';
    trainingSort = 'recent';
    trainingSortSelect.value = 'recent';
    renderTraining();
    updateView();
    message.textContent = `已从本地备份恢复身体参数和 ${training.length} 条训练记录。`;
    get('#profile-message').textContent = '已从备份恢复并保存在本设备';
  } catch (error) {
    message.textContent = error instanceof Error ? `导入失败：${error.message}` : '导入失败：文件格式不正确';
  }
});

function frame(now: number): void {
  if (playing) {
    phase = exercise === 'bench'
      ? advanceBenchPhase(phase, (now - lastFrame) / 1000,
        benchPlaybackTiming(benchTempoMode, profile.heightCm, cycleDurationS))
      : (phase + (now - lastFrame) / (cycleDurationS * 1000)) % 1;
    updateView();
  }
  lastFrame = now;
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
renderTraining();
updateView();
// Which build this page is, so a report from a phone can name the exact version it ran.
get('#build-identity').textContent = `构建标识 ${buildCache}`;

if (import.meta.env.PROD && !Capacitor.isNativePlatform()) {
  const offlineStatus = get('#offline-status');
  if ('serviceWorker' in navigator) {
    const expectedCache = buildCache;
    // The badge reports two independent things: whether the offline bundle is verified complete, and
    // whether the device currently has a network at all. Saying “资源缓存已完成” while offline would
    // hide the second one, and saying “离线” while the bundle is incomplete would overstate the app.
    let bundleState = '离线包准备中';
    const renderOfflineStatus = (): void => {
      const online = navigator.onLine;
      offlineStatus.textContent = online ? bundleState : `离线 · ${bundleState}`;
    };
    const checkOfflineCache = (registration: ServiceWorkerRegistration): void => {
      const worker = navigator.serviceWorker.controller ?? registration.active;
      if (!worker) return;
      const channel = new MessageChannel();
      channel.port1.onmessage = event => {
        const status = event.data as { cache?: string; complete?: boolean; missing?: string[] } | undefined;
        if (status?.cache !== expectedCache) return;
        if (status.complete) {
          bundleState = '资源缓存已完成';
          renderOfflineStatus();
          return;
        }
        const missing = Array.isArray(status.missing) ? status.missing.length : undefined;
        bundleState = missing === undefined ? '离线包未就绪' : `离线包未就绪 · 缺 ${missing} 项`;
        renderOfflineStatus();
      };
      worker.postMessage({ type: 'cache-status' }, [channel.port2]);
    };
    window.addEventListener('online', renderOfflineStatus);
    window.addEventListener('offline', renderOfflineStatus);
    renderOfflineStatus();
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      void navigator.serviceWorker.ready.then(checkOfflineCache);
    });
    window.addEventListener('load', () => {
      void navigator.serviceWorker.register('/sw.js').then(() => navigator.serviceWorker.ready)
        .then(checkOfflineCache).catch(error => {
          // Say why, on the element itself: a silent catch hid a real offline-bundle failure from every
          // check and probe in this repository.
          bundleState = '离线包未就绪';
          offlineStatus.title = `离线包注册失败：${error instanceof Error ? error.message : String(error)}`;
          renderOfflineStatus();
        });
    });
  } else {
    offlineStatus.textContent = '浏览器不支持离线包';
  }
}
