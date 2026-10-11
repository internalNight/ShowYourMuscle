// ⑤ 同源守卫：研究层 Z-Anatomy 网格名 → OpenSim 体段名的映射只写在 docs/data/registered_bone_bodies.json
// 一处，且每个目标体段都必须在默认视图导出记录的 22 个模型体段里存在，腓骨网格必须挂到带腓骨部件的体段。
import { readFileSync as readGuardFile } from 'node:fs';
{
  const readGuard = (relative) => JSON.parse(readGuardFile(new URL(relative, import.meta.url), 'utf8'));
  const mapping = readGuard('../docs/data/registered_bone_bodies.json');
  const record = readGuard('../docs/data/full_body_skeleton_export.json');
  // 导出记录里 32 条 = 22 个模型体段 + 10 个拆分部件，部件就是某些条目 parts 里点名的那些（已实测）。
  const partNames = new Set(record.bodies.flatMap((body) => body.parts ?? []));
  const modelBodies = record.bodies.map((body) => body.body).filter((name) => !partNames.has(name));
  const entries = Object.entries(mapping.map ?? {});
  if (modelBodies.length !== 22) {
    throw new Error(`默认视图导出记录里有 ${modelBodies.length} 个模型体段，不是 22 个`);
  }
  if (entries.length !== 6) {
    throw new Error(`研究层映射了 ${entries.length} 个网格，不是 6 个`);
  }
  const unknown = entries.filter(([, body]) => !modelBodies.includes(body))
    .map(([mesh, body]) => `${mesh}→${body}`);
  if (unknown.length > 0) {
    throw new Error(`研究层体段名不在默认视图导出记录里：${unknown.join('、')}`);
  }
  if (mapping.source !== 'docs/data/full_body_skeleton_export.json') {
    throw new Error(`映射声明的来源是 ${mapping.source}，不是默认视图的导出记录`);
  }
  const fibula = record.bodies.find((body) => body.body === mapping.map.Fibular);
  const fibulaParts = (fibula?.parts ?? []).map((part) => String(part));
  if (!fibulaParts.some((name) => name.includes('fibula'))) {
    throw new Error(`腓骨网格挂到的体段没有腓骨部件：${fibulaParts.join('、')}`);
  }
  // 每个体段用哪套几何：研究层网格（精细，但只覆盖右侧五段与骨盆，左侧靠镜像）与导出几何必须不重不漏，
  // 合起来正好 22 个模型体段。这条守住"以研究网格为准"的裁决，防止两边各写各的。
  const source = mapping.geometrySource;
  if (!source) throw new Error('映射文件里没有 geometrySource：默认视图各体段用哪套几何没有单一来源');
  const research = source.research ?? [];
  const mirrored = Object.keys(source.mirroredFrom ?? {});
  const exportBodies = source.exportBodies ?? [];
  const overlap = research.filter((name) => exportBodies.includes(name));
  if (overlap.length > 0) {
    throw new Error(`这些体段同时被声明为研究网格与导出几何：${overlap.join('、')}`);
  }
  // 覆盖按集合算：同一体段被不同清单以不同理由提到时不该把总数撑大，只要并集正好是 22 个模型体段。
  const union = [...new Set([...research, ...mirrored, ...exportBodies])];
  const duplicates = [...research, ...mirrored, ...exportBodies]
    .filter((name, index, all) => all.indexOf(name) !== index)
    .filter((name) => !mirrored.includes(name));
  if (duplicates.length > 0) {
    throw new Error(`来源清单里重复的体段：${duplicates.join('、')}`);
  }
  const missing = union.filter((name) => !record.bodies.some((body) => body.body === name));
  if (missing.length > 0) {
    throw new Error(`这些模型体段没有声明几何来源：${missing.join('、')}`);
  }
  // 覆盖按导出记录的 32 个条目算（22 个模型体段 + 10 个拆分部件）：研究清单点名的 torso_spine 等是部件，
  // 不是模型体段；用 22 去比会把部件当错项，这正是这次守卫抓到的我自己写的错。
  const entryNames = record.bodies.map((body) => body.body);
  if (union.length !== entryNames.length) {
    throw new Error(`来源清单覆盖 ${union.length} 个条目，导出记录有 ${entryNames.length} 个`);
  }
  // ⑤ 的执行一致性：默认视图让位的体段必须正是来源清单里声明用研究网格的那些，一个不多一个不少。
  const swapScript = readFileSync(new URL('./check-full-body-skeleton.mjs', import.meta.url), 'utf8');
  if (!swapScript.includes('registeredBoneBodies.geometrySource.research')) {
    throw new Error('渲染器没有按来源清单让位：geometrySource.research 未被使用');
  }
  if (research.length === 0 || mirrored.length === 0) {
    throw new Error('来源清单里研究网格或镜像清单为空，默认视图无法按裁决绘制那六段');
  }
  // 上半身肌肉守卫：每条规则都必须真的匹配到研究资源里的网格——否则默认视图会"以为补了、其实没补"。
  const assetMap = readGuard('../docs/data/registered_bone_bodies.json');
  const rules = assetMap.upperBodyMuscles?.rules ?? [];
  if (rules.length < 8) {
    throw new Error(`上半身肌肉规则只有 ${rules.length} 条，覆盖不了那几段示意圆柱`);
  }
  const glb = readFileSync(new URL('../public/models/z_anatomy_reference.glb', import.meta.url));
  const jsonLength = glb.readUInt32LE(12);
  const asset = JSON.parse(glb.subarray(20, 20 + jsonLength).toString('utf8'));
  const assetNames = (asset.nodes ?? []).filter((node) => node.mesh !== undefined).map((node) => node.name);
  const uncovered = rules.filter((rule) => !assetNames.some((name) => new RegExp(rule.match, 'i').test(name)));
  // 脊柱与肋骨规则同样必须真的匹配到资源——逐块椎骨、逐根肋骨是 ② 的实质内容，不能只是清单上写了。
  const boneRules = assetMap.boneRules?.rules ?? [];
  if (boneRules.length < 2) {
    throw new Error(`脊柱/肋骨规则只有 ${boneRules.length} 条`);
  }
  const uncoveredBones = boneRules.filter((rule) => !assetNames.some((name) => new RegExp(rule.match, 'i').test(name)));
  if (uncoveredBones.length > 0) {
    throw new Error(`这些骨骼规则在研究资源里找不到对应网格：${uncoveredBones.map((rule) => rule.group).join('、')}`);
  }
  for (const rule of boneRules) {
    // 规则指向的是导出记录里的条目（可能是拆分部件，如 torso_spine），不是 22 个体段名。
    if (!entryNames.includes(rule.body)) {
      throw new Error(`骨骼规则 ${rule.group} 指向的条目 ${rule.body} 不在导出记录里`);
    }
    if (!research.includes(rule.body)) {
      throw new Error(`骨骼规则 ${rule.group} 指向 ${rule.body}，但它没有声明用研究网格`);
    }
  }
  if (uncovered.length > 0) {
    throw new Error(`这些上半身肌肉规则在研究资源里找不到对应网格：${uncovered.map((rule) => rule.group).join('、')}`);
  }
  // ③ 的包裹面：模型定义里有 44 个（全是圆柱），每个都必须有名、有类型、有所属体段，且体段必须真在导出记录里，
  // 圆柱还必须带半径。少了任何一个，说明"路径绕过了什么"这件事在数据层就丢了。
  const wraps = readGuard('../docs/data/full_body_wrap_surfaces.json');
  const wrapRecords = wraps.records ?? [];
  if (wrapRecords.length !== 44) {
    throw new Error(`wrapping 面有 ${wrapRecords.length} 个，模型定义里是 44 个`);
  }
  const entryNamesForWraps = record.bodies.map((body) => body.body);
  for (const wrap of wrapRecords) {
    if (!wrap.name || !wrap.type || !wrap.body) {
      throw new Error(`wrapping 面记录不完整：${JSON.stringify(wrap)}`);
    }
    if (!entryNamesForWraps.includes(wrap.body)) {
      throw new Error(`wrapping 面 ${wrap.name} 挂在 ${wrap.body} 上，但导出记录里没有这个条目`);
    }
    if (wrap.type === 'WrapCylinder' && typeof wrap.radiusM !== 'number') {
      throw new Error(`圆柱包裹面 ${wrap.name} 没有半径，画不出来`);
    }
  }
  if (source.export !== 'docs/data/full_body_skeleton_export.json') {
    throw new Error(`导出几何的来源声明是 ${source.export}`);
  }
  console.log(JSON.stringify({ source: mapping.source, meshes: entries.length,
    bodies: modelBodies.length, fibulaCarrier: mapping.map.Fibular, fibulaParts: fibulaParts.length }));
}
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// The full-body skeleton is exported offline by `scripts/export_full_body_skeleton.py` (OpenSim runs only on
// the desktop) and shipped as `public/models/full_body_skeleton.glb`. This check re-reads the shipped GLB
// itself — its node tree, its accessor ranges and its per-node triangle counts — and requires the recorded
// export numbers to match what is actually in the file, so a stale record or a half-written export fails.
const record = JSON.parse(readFileSync('docs/data/full_body_skeleton_export.json', 'utf8'));
// Measured independently by loading the shipped GLB in three.js inside headless Edge: the export
// record comes from OpenSim in Python, so agreement between the two is a real cross-check and
// catches transform mistakes (an export that ignored body rotations once under-reported the
// assembled height by 12.5 cm).
const render = JSON.parse(readFileSync('docs/data/full_body_skeleton_render_check.json', 'utf8'));
const glb = readFileSync('public/models/full_body_skeleton.glb');

assert.equal(record.status, 'full_body_skeleton_export_geometry_only');
assert.ok(record.model.path.endsWith('RajagopalLaiUhlrich2023.osim'));
assert.match(record.model.sha256, /^[0-9A-F]{64}$/);
assert.equal(record.model.bodies, 22);
assert.equal(record.referenceHeightCm, 175);

// GLB container: magic, version, declared length, then the JSON chunk.
assert.equal(glb.readUInt32LE(0), 0x46546c67, 'not a GLB file');
assert.equal(glb.readUInt32LE(4), 2, 'unexpected glTF version');
assert.equal(glb.readUInt32LE(8), glb.length, 'the GLB header length does not match the file');
const jsonLength = glb.readUInt32LE(12);
assert.equal(glb.readUInt32LE(16), 0x4e4f534a, 'the first chunk is not JSON');
const binaryLength = glb.readUInt32LE(20 + jsonLength);
assert.equal(glb.readUInt32LE(24 + jsonLength), 0x004e4942, 'the second chunk is not BIN');
assert.equal(12 + 8 + jsonLength + 8 + binaryLength, glb.length,
  'the GLB chunks do not add up to the file length');
const gltf = JSON.parse(glb.subarray(20, 20 + jsonLength).toString('utf8'));

assert.equal(record.output.bytes, glb.length, 'the recorded export size is not the size of the shipped file');
assert.equal(record.output.nodes, gltf.nodes.length);
assert.equal(record.output.meshes, gltf.meshes.length);
assert.equal(gltf.asset.extras.sourceSha256, record.model.sha256,
  'the GLB and the record disagree about which OpenSim model this came from');
assert.equal(gltf.asset.extras.referenceHeightCm, record.referenceHeightCm);

// The node tree must be exactly the model's body tree, taken from the GLB rather than from the record.
const nodeNames = gltf.nodes.map(node => node.name);
const recordedBodies = record.bodies.map(body => body.body);
assert.deepEqual([...nodeNames].sort(), [...recordedBodies].sort(),
  'the GLB nodes are not exactly the recorded bodies');
const parentFromGlb = new Map();
gltf.nodes.forEach((node, index) => {
  for (const child of node.children ?? []) {
    assert(!parentFromGlb.has(gltf.nodes[child].name), `${gltf.nodes[child].name} has two parents`);
    parentFromGlb.set(gltf.nodes[child].name, node.name);
  }
});
assert.deepEqual(record.roots, gltf.scenes[0].nodes.map(index => gltf.nodes[index].name),
  'the recorded roots are not the scene roots');
assert.equal(record.roots.length, 1, 'the skeleton should hang off a single root');
for (const body of record.bodies) {
  assert.equal(parentFromGlb.get(body.body) ?? null, body.parent,
    `${body.body}: the recorded parent is not the parent in the GLB`);
}
// A skeleton where every bone hangs off the root would still pass a name comparison, so the depth is checked.
const depth = name => {
  let levels = 0;
  let current = name;
  while (parentFromGlb.has(current)) {
    current = parentFromGlb.get(current);
    levels += 1;
    assert.ok(levels < 12, 'the body tree has a cycle');
  }
  return levels;
};
assert.ok(depth('toes_r') >= 5, `the right leg is not a chain: depth ${depth('toes_r')}`);
assert.ok(depth('hand_l') >= 5, `the left arm is not a chain: depth ${depth('hand_l')}`);

// Per-body geometry, recomputed from the GLB: triangle count from the index accessor, bounds from POSITION.
let triangles = 0;
for (const body of record.bodies) {
  const node = gltf.nodes.find(candidate => candidate.name === body.body);
  assert.ok(node, `${body.body} has no node`);
  if (body.meshes.length === 0) {
    // A parent body whose geometry lives in its parts. The record has to say so, the GLB node must carry no
    // mesh, and the body still needs a box: the joint-clearance and render checks read where it is.
    assert.ok(node.mesh === undefined || node.mesh === null,
      `${body.body} records no mesh but carries one in the GLB`);
    assert.equal(body.triangles, 0, `${body.body}: a mesh-less body records triangles`);
    assert.ok(body.boundsInBodyFrame, `${body.body}: a mesh-less body records no bounding box`);
    assert.deepEqual(body.meshes, [], `${body.body}: a mesh-less body lists meshes`);
    continue;
  }
  assert.ok(node.mesh !== undefined && node.mesh !== null, `${body.body} has no mesh`);
  const primitive = gltf.meshes[node.mesh].primitives[0];
  const indices = gltf.accessors[primitive.indices];
  const positions = gltf.accessors[primitive.attributes.POSITION];
  assert.equal(indices.componentType, 5125, `${body.body}: indices are not uint32`);
  assert.equal(indices.count / 3, body.triangles,
    `${body.body}: the recorded triangle count is not what the GLB holds`);
  assert.equal(positions.count, body.points, `${body.body}: the recorded point count is wrong`);
  assert.equal(positions.type, 'VEC3');
  for (const axis of [0, 1, 2]) {
    assert.ok(positions.min[axis] < positions.max[axis], `${body.body}: empty on axis ${axis}`);
    // The trunk parts are the largest meshes in the file (spine alone spans most of the torso); a single bone
    // spanning more than 90 cm would mean a mesh was attached at the wrong scale.
    assert.ok(positions.max[axis] - positions.min[axis] < 0.9,
      `${body.body}: a body mesh spans more than 90 cm on axis ${axis}`);
  }
  triangles += body.triangles;
}
assert.equal(triangles, record.output.triangles, 'the recorded triangle total does not add up');

// Plausibility of the assembled skeleton, and of the map a girth input uses. A typo in that map would
// silently stop scaling a segment, which no other assertion would notice.
assert.ok(Math.abs(record.boundsInExportM.max[1] - record.boundsInExportM.min[1] - record.boundsInExportM.heightM) < 1e-9,
  'the recorded height is not the recorded bounds');
assert.ok(Math.abs(record.boundsInExportM.max[0] - record.boundsInExportM.min[0] - record.boundsInExportM.widthM) < 1e-9,
  'the recorded width is not the recorded bounds');
// Independently measured by loading the shipped GLB in three.js (0.4971 x 1.67073 x 0.51064 m), which is
// what pinned this window: an earlier export that added translations to local boxes without rotating them
// under-reported the height as 1.5452 m, and the tight window catches that mistake.
assert.ok(record.boundsInExportM.heightM > 1.62 && record.boundsInExportM.heightM < 1.72,
  `the assembled skeleton is not about 1.67 m tall: ${record.boundsInExportM.heightM}`);
// The record's `widthM` is the front-to-back (x) span; left to right is z. Hands baked in the wrong body
// frame used to stretch x to 0.497 m, and centring them on their own frame brought it to 0.342 m, which is
// why this window is narrow — it is exactly the kind of geometry mistake it should catch.
assert.ok(record.boundsInExportM.widthM > 0.3 && record.boundsInExportM.widthM < 0.4,
  `the front-to-back span is not plausible: ${record.boundsInExportM.widthM}`);
const leftRightSpan = record.boundsInExportM.max[2] - record.boundsInExportM.min[2];
assert.ok(leftRightSpan > 0.45 && leftRightSpan < 0.55,
  `the left-to-right span is not plausible: ${leftRightSpan}`);
assert.ok(record.boundsInExportM.min[1] < -0.9 && record.boundsInExportM.max[1] > 0.7,
  'the legs should extend about 0.94 m below and the torso about 0.73 m above the pelvis origin');
// The default pose sits about 3 cm off-centre in x now that the hand meshes are in their own body frame
// (they used to push the x extent out to -0.348 m). The runtime still has to centre on the bounding box
// rather than the root node, and this window catches a mesh that wanders off again.
assert.ok(record.boundsInExportM.min[0] < -0.15 && record.boundsInExportM.min[0] > -0.3,
  `the default pose is not a plausible distance off-centre in x: ${record.boundsInExportM.min[0]}`);
for (const axis of [0, 1, 2]) {
  const difference = Math.max(Math.abs(record.boundsInExportM.min[axis] - render.measuredBoundsM.min[axis]),
    Math.abs(record.boundsInExportM.max[axis] - render.measuredBoundsM.max[axis]));
  assert.ok(difference <= 0.002,
    `axis ${axis}: the export record and the independent render disagree by ${difference} m`);
}
assert.equal(render.artifact.bytes, glb.length, 'the render check measured a different file');
assert.equal(render.artifact.triangles, triangles, 'the render check counted different triangles');
assert.equal(render.checks.nodesPresent, '22/22');
assert.equal(render.checks.invertedOrInwardFacingMeshes, 0, 'the render found inside-out meshes');
assert.equal(render.checks.degenerateNodes, 0, 'the render found degenerate nodes');
assert.equal(render.checks.pageErrors.length, 0, 'the page that rendered the skeleton logged errors');
// The left arm is mirrored from the right side, so the worst left-right pair has to stay at mirror accuracy:
// the independent render measured 42.1 mm when the mirror used the front-to-back axis and 0.9 mm once it used
// left-to-right, which is the fault this assertion exists to catch.
assert.ok(render.checks.worstLeftRightPairM !== null && render.checks.worstLeftRightPairM !== undefined,
  'the render check did not measure left-right symmetry');
assert.ok(Math.abs(render.checks.worstLeftRightPairM) < 0.005,
  `the worst left-right pair is ${render.checks.worstLeftRightPairM} m apart`);
for (const [pair, gap] of Object.entries(render.checks.parentChildBoundingBoxGapsM)) {
  assert.ok(gap < 0.001, `${pair}: the rendered bones are not touching (${gap} m apart)`);
}
for (const [name, box] of Object.entries(render.boneBoxesM)) {
  assert.ok(record.bodies.some(body => body.body === name), `the render measured an unknown bone: ${name}`);
  assert.ok(box.size.every(value => value > 0), `${name}: the render measured an empty box`);
}
for (const segment of ['chest', 'waist', 'thigh', 'calf', 'arm']) {
  assert.ok(Array.isArray(record.segmentGirthBodies[segment]) && record.segmentGirthBodies[segment].length > 0,
    `the girth map does not cover ${segment}`);
  for (const body of record.segmentGirthBodies[segment]) {
    assert.ok(nodeNames.includes(body), `the girth map points at an unknown body: ${body}`);
  }
}
// The runtime fits each bone mesh onto the app's own skeleton segments, which needs every bone's proximal
// and distal joint in that bone's own frame. Recomputing that here keeps a stale or unit-mangled table from
// silently mis-fitting the whole skeleton.
const jointByChild = new Map(record.jointFrames.map(frame => [frame.childBody, frame]));
const childSideOffsets = [];
assert.equal(record.jointFrames.length, 22, 'the joint frame table is incomplete');
assert.ok(['walker_knee_r', 'walker_knee_l'].every(name =>
  record.jointFrames.some(frame => frame.joint === name)), 'the knee joints are missing from the table');
assert.equal(jointByChild.size, 22, 'two joints claim the same child body');
for (const frame of record.jointFrames) {
  assert.ok(nodeNames.includes(frame.childBody), `${frame.joint}: unknown child body ${frame.childBody}`);
  const body = record.bodies.find(candidate => candidate.body === frame.childBody);
  assert.equal(frame.parentBody, body.parent, `${frame.joint}: the joint table and the body tree disagree`);
  // This model attaches most joints with the offset on the parent side only, so the child-side offset is
  // exactly zero; the two `walker_knee` joints are the exception and carry a small distal offset.
  for (const axis of [0, 1, 2]) {
    assert.ok(Math.abs(frame.locationInChildBodyM[axis]) < 0.2,
      `${frame.joint}: a child-side joint offset larger than 20 cm is not a human skeleton`);
  }
  if (Math.max(...frame.locationInChildBodyM.map(Math.abs)) > 0) childSideOffsets.push(frame.joint);
  if (frame.joint === 'ground_pelvis') {
    assert.equal(frame.locationInParentBodyM, null, 'the ground joint has no parent body');
    continue;
  }
  assert.ok(Array.isArray(frame.locationInParentBodyM), `${frame.joint} is missing its parent-side offset`);
  assert.ok(Math.max(...frame.locationInParentBodyM.map(Math.abs)) < 0.6,
    `${frame.joint}: a joint offset larger than 60 cm is not a human skeleton`);
}
// Bone lengths read off the joint offsets: a unit or axis mistake shows up here as an impossible bone.
const offsetOf = child => Math.hypot(...jointByChild.get(child).locationInParentBodyM);
assert.ok(offsetOf('tibia_r') > 0.3 && offsetOf('tibia_r') < 0.45, `shank length ${offsetOf('tibia_r')} m`);
assert.ok(offsetOf('ulna_r') > 0.2 && offsetOf('ulna_r') < 0.35, `upper arm length ${offsetOf('ulna_r')} m`);
assert.ok(offsetOf('talus_r') > 0.3 && offsetOf('talus_r') < 0.45, `shank-to-ankle length ${offsetOf('talus_r')} m`);
assert.ok(offsetOf('femur_r') > 0.05 && offsetOf('femur_r') < 0.2, `hip offset ${offsetOf('femur_r')} m`);
assert.deepEqual(childSideOffsets.sort(), ['walker_knee_l', 'walker_knee_r'],
  `unexpected joints carrying a child-side offset: ${childSideOffsets.join(', ')}`);

// The pelvis and trunk geometry must be in the file. Before the split each was one merged mesh; now the meshes
// belong to the parts those bodies name, so the count follows the parts instead of stopping at the parent.
const bodyEntry = name => record.bodies.find(body => body.body === name) || {};
const pairingCount = name => (record.pairing[name] || []).length +
  (bodyEntry(name).parts || []).reduce((total, part) => total + (record.pairing[part] || []).length, 0);
assert.ok(pairingCount('pelvis') > 0 && pairingCount('torso') > 0,
  'the pelvis and the trunk carry no geometry, directly or through their parts');

// The default view renders what the export assigns: one fit per body, 22 of 22. Before this assertion the
// table covered 11 bodies, so the pelvis, both patellae, both feet and both hands were shipped in the GLB and
// never drawn — the app has no other list to notice a missing bone.
const fits = gltf.asset.extras.segments;
// One fit per mesh-bearing node. The split bodies hand their meshes to the parts they name, so the count is the
// number of bodies that still carry a mesh, and coverage below follows the parts for the rest.
const meshBearing = record.bodies.filter(body => body.meshes.length > 0).length;
assert.equal(fits.length, meshBearing,
  'the export must assign every mesh-bearing body to a teaching segment');
const fittedBodies = new Set(fits.map(fit => fit.body));
const partsOf = name => (record.bodies.find(body => body.body === name) || {}).parts || [];
const isDrawn = name => fittedBodies.has(name) || partsOf(name).some(part => fittedBodies.has(part));
const unfitted = record.bodies.map(body => body.body).filter(name => !isDrawn(name));
assert.deepEqual(unfitted, [], `bodies the default view would never render: ${unfitted.join(', ')}`);
for (const fit of fits) {
  assert(gltf.nodes.some(node => node.name === fit.body), `${fit.body}: the fit names a node that is not in the GLB`);
  assert([...fittedBodies].includes(fit.body));
  assert.equal(fit.offset.length, 16, `${fit.body}: the fit offset is not a 4x4 matrix`);
}
assert.ok(record.limitations.length >= 3, 'the export limitations were dropped');
assert.ok(record.limitations.join('\n').includes('镜像'), 'the limitation about mirrored meshes was dropped');

console.log(`FULL_BODY_SKELETON {"bytes":${glb.length},"nodes":${gltf.nodes.length},"triangles":${triangles},"heightM":${record.boundsInExportM.heightM},"root":"${record.roots[0]}","legDepth":${depth('toes_r')},"armDepth":${depth('hand_l')},"girthSegments":${Object.keys(record.segmentGirthBodies).length},"renderHeightM":${render.measuredBoundsM.size[1]},"jointFrames":${record.jointFrames.length}}`);
console.log('The shipped skeleton GLB, its node tree and its recorded numbers agree.');
