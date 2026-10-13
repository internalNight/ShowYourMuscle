import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { spawn, spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const browser = [process.env.ATLAS_BROWSER,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'].find(value => value && existsSync(value));
assert(browser, 'Chromium browser required for unified model UI check');
const origin = process.env.ATLAS_ORIGIN || 'http://127.0.0.1:5173';
const port = 15000 + Math.floor(Math.random() * 10000);
const profile = mkdtempSync(join(tmpdir(), 'unified-ui-'));
const child = spawn(browser, ['--headless=new', '--no-sandbox', '--disable-gpu',
  '--enable-unsafe-swiftshader', '--hide-scrollbars', '--window-size=1440,920',
  `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  `${origin}/`], { stdio: 'ignore' });
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let socket;
try {
  let target;
  for (let attempt = 0; attempt < 100; attempt++) {
    try {
      const tabs = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      target = tabs.find(item => item.type === 'page' && item.url.startsWith(origin));
      if (target) break;
    } catch {}
    await sleep(500);
  }
  assert(target, `browser never opened the unified page on debug port ${port}; Edge exit=${child.exitCode}`);
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let nextId = 1;
  const pending = new Map();
  const errors = [];
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      pending.get(message.id)(message);
      pending.delete(message.id);
    }
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text);
  };
  const send = (method, params = {}) => new Promise(resolve => {
    const id = nextId++;
    pending.set(id, resolve);
    socket.send(JSON.stringify({ id, method, params }));
  });
  const evalPage = async expression => {
    const reply = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (reply.result?.exceptionDetails) throw new Error(reply.result.exceptionDetails.text);
    return reply.result?.result?.value;
  };
  await send('Runtime.enable');
  let state;
  for (let attempt = 0; attempt < 100; attempt++) {
    state = await evalPage(`document.querySelector('#unified-stage')?.dataset.ready`);
    if (state === 'true' || state === 'error') break;
    await sleep(500);
  }
  assert.equal(state, 'true', await evalPage(`document.querySelector('#unified-status')?.textContent`));
  const initial = await evalPage(`(() => { const s = document.querySelector('#unified-stage');
    return { model: s.dataset.model, muscles: s.dataset.muscles, bodies: s.dataset.bodies,
      meshes: s.dataset.sourceMeshes, surfaces: s.dataset.surfaceMeshes,
      anatomyBones: s.dataset.anatomyBones,
      missing: s.dataset.missingSourceMeshes,
      excluded: s.dataset.excludedSourceMeshes,
      length: +s.dataset.selectedLengthM, canvas: !!s.querySelector('canvas') }; })()`);
  assert.equal(initial.muscles, '520');
  assert.equal(initial.bodies, '80');
  assert.equal(initial.meshes, '83');
  assert.equal(initial.surfaces, '68');
  assert.equal(initial.anatomyBones, '91');
  assert.equal(await evalPage(`document.querySelector('#unified-bones').checked`), true);
  assert.equal(initial.missing, '37');
  assert.equal(initial.excluded, '12');
  assert(initial.canvas);
  const lengths = { neutral: initial.length };
  for (const mode of ['squat', 'bench', 'press']) {
    await evalPage(`document.querySelector('[data-mode="${mode}"]').click()`);
    if (mode === 'bench' || mode === 'press') {
      await sleep(200);
      const startShot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
      writeFileSync(join(process.cwd(), '.cache', `unified-${mode}-start-check.png`),
        Buffer.from(startShot.result.data, 'base64'));
    }
    lengths[mode] = await evalPage(`(() => {
      const range = document.querySelector('#unified-timeline');
      range.value = '50'; range.dispatchEvent(new Event('input', { bubbles: true }));
      return +document.querySelector('#unified-stage').dataset.selectedLengthM;
    })()`);
    assert.equal(await evalPage(`document.querySelector('#unified-stage').dataset.mode`), mode);
    const major = await evalPage(`(() => { const p = document.querySelector('#unified-major');
      return { longer: p.dataset.longer, shorter: p.dataset.shorter,
        reference: p.dataset.reference, text: p.textContent }; })()`);
    assert.equal(major.reference, '动作起点');
    assert(major.text.includes('不推断激活或力量'), `${mode} omits geometric scope`);
    if (mode === 'squat') assert(major.longer.includes('臀大肌') && major.longer.includes('股'),
      `squat major changes are not lower limb: ${JSON.stringify(major)}`);
    if (mode === 'bench') {
      assert(major.shorter.includes('肱三头肌') && major.text.includes('胸大肌路径变化很小'),
        `bench geometry or chest caveat missing: ${JSON.stringify(major)}`);
      const before = await evalPage(`document.querySelector('#unified-stage').dataset.selectedLengthM`);
      await evalPage(`document.querySelector('#unified-major .major-row.shorter').click()`);
      const after = await evalPage(`document.querySelector('#unified-stage').dataset.selectedLengthM`);
      assert.notEqual(after, before, 'clicking a major muscle did not select its OpenSim path');
    }
    if (mode === 'press') assert(major.shorter.includes('肱三头肌'),
      `press major changes omit triceps: ${JSON.stringify(major)}`);
    if (mode === 'squat') {
      const returnState = await evalPage(`(() => { const range = document.querySelector('#unified-timeline');
        range.value = '75'; range.dispatchEvent(new Event('input', { bubbles: true }));
        const p = document.querySelector('#unified-major');
        return { shorter: p.dataset.shorter, reference: p.dataset.reference,
          readout: document.querySelector('#unified-readout').textContent }; })()`);
      assert.equal(returnState.reference, '折返点');
      assert(returnState.shorter.includes('臀大肌') && returnState.readout.includes('折返点'),
        `return stage did not reverse geometric comparison: ${JSON.stringify(returnState)}`);
      await evalPage(`(() => { const range = document.querySelector('#unified-timeline');
        range.value = '50'; range.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    }
    const propState = await evalPage(`(() => {
      const canvas = document.querySelector('#unified-stage canvas');
      return { canvasHeight: canvas.getBoundingClientRect().height,
        buttonsVisible: document.querySelector('.unified-tabs').getBoundingClientRect().bottom <= innerHeight };
    })()`);
    assert(propState.canvasHeight > 350 && propState.buttonsVisible,
      `${mode} viewport clips the model controls: ${JSON.stringify(propState)}`);
    const jointText = await evalPage(`document.querySelector('#unified-joints').textContent`);
    assert(jointText.includes('人为设定的角度') && jointText.includes('°'),
      `${mode} has no source coordinate readout: ${jointText}`);
    await sleep(200);
    const poseShot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
    writeFileSync(join(process.cwd(), '.cache', `unified-${mode}-check.png`),
      Buffer.from(poseShot.result.data, 'base64'));
  }
  assert(Object.values(lengths).every(Number.isFinite), `invalid selected muscle length: ${JSON.stringify(lengths)}`);
  if (process.env.ATLAS_LIVE === '1') {
    await evalPage(`(() => {
      document.querySelector('[data-mode="custom"]').click();
      for (const [name, value] of [['hip_flexion', 90], ['knee_angle', 100]]) {
        const slider = document.querySelector('[data-joint="' + name + '"]');
        slider.value = String(value);
        slider.dispatchEvent(new Event('input', { bubbles: true }));
      }
    })()`);
    let liveStatus;
    for (let attempt = 0; attempt < 40; attempt++) {
      liveStatus = await evalPage(`document.querySelector('#unified-live-status').textContent`);
      if (liveStatus.includes('已由 OpenSim') || liveStatus.includes('不可用')) break;
      await sleep(250);
    }
    assert(liveStatus.includes('已由 OpenSim'), `live pose failed: ${liveStatus}`);
    const joints = await evalPage(`document.querySelector('#unified-joints').textContent`);
    assert(joints.includes('90.0°') && joints.includes('100.0°'), `live pose not applied: ${joints}`);
    const liveShot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
    writeFileSync(join(process.cwd(), '.cache', 'unified-custom-check.png'),
      Buffer.from(liveShot.result.data, 'base64'));
    const beforeArm = await evalPage(`document.querySelector('#unified-joints').textContent`);
    const handScreen = await evalPage(`document.querySelector('#unified-stage').dataset.handRightScreen`);
    assert(handScreen, 'custom hand drag handle has no screen position');
    const [handX, handY] = handScreen.split(',').map(Number);
    await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: handX, y: handY,
      button: 'left', buttons: 1, clickCount: 1 });
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: handX + 10, y: handY - 30,
      button: 'left', buttons: 1 });
    await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: handX + 10, y: handY - 30,
      button: 'left', buttons: 0, clickCount: 1 });
    let ikStatus;
    for (let attempt = 0; attempt < 100; attempt++) {
      ikStatus = await evalPage(`document.querySelector('#unified-live-status').textContent`);
      if (ikStatus.includes('手部目标已') || ikStatus.includes('手部目标超出') || ikStatus.includes('失败')) break;
      await sleep(250);
    }
    assert(ikStatus.includes('手部目标已') || ikStatus.includes('手部目标超出'),
      `hand drag IK failed: ${ikStatus}`);
    const afterArm = await evalPage(`document.querySelector('#unified-joints').textContent`);
    assert.notEqual(afterArm, beforeArm, `hand drag did not change arm coordinates: ${ikStatus}; hand=${handScreen}`);
    const footScreen = await evalPage(`document.querySelector('#unified-stage').dataset.footRightScreen`);
    assert(footScreen, 'custom foot drag handle has no screen position');
    const [footX, footY] = footScreen.split(',').map(Number);
    await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: footX, y: footY,
      button: 'left', buttons: 1, clickCount: 1 });
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: footX + 10, y: footY - 15,
      button: 'left', buttons: 1 });
    await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: footX + 10, y: footY - 15,
      button: 'left', buttons: 0, clickCount: 1 });
    let footStatus;
    for (let attempt = 0; attempt < 100; attempt++) {
      footStatus = await evalPage(`document.querySelector('#unified-live-status').textContent`);
      if (footStatus.includes('脚部目标已') || footStatus.includes('脚部目标超出') || footStatus.includes('失败')) break;
      await sleep(250);
    }
    assert(footStatus.includes('脚部目标已') || footStatus.includes('脚部目标超出'),
      `foot drag IK failed: ${footStatus}`);
  }
  await evalPage(`document.querySelector('[data-mode="neutral"]').click()`);
  await sleep(800);
  const screenshot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  const imagePath = join(process.cwd(), '.cache', 'unified-ui-check.png');
  writeFileSync(imagePath, Buffer.from(screenshot.result.data, 'base64'));
  assert.deepEqual(errors, [], `page exceptions: ${errors.join(' | ')}`);
  console.log(JSON.stringify({ ready: true, initial, lengths, screenshot: imagePath }, null, 2));
} finally {
  socket?.close();
  if (process.platform === 'win32') {
    spawnSync('powershell', ['-NoProfile', '-Command',
      '$targetPath = $env:UNIFIED_UI_PROFILE; ' +
      'Get-CimInstance Win32_Process -Filter "name = \'msedge.exe\'" | ' +
      'Where-Object { $_.CommandLine -like "*$targetPath*" } | ' +
      'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }'],
    { stdio: 'ignore', env: { ...process.env, UNIFIED_UI_PROFILE: profile } });
  } else {
    child.kill();
  }
  await sleep(300);
  try { rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 }); } catch {}
}
