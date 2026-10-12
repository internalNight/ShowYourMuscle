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
      meshes: s.dataset.sourceMeshes, missing: s.dataset.missingSourceMeshes,
      excluded: s.dataset.excludedSourceMeshes,
      length: +s.dataset.selectedLengthM, canvas: !!s.querySelector('canvas') }; })()`);
  assert.equal(initial.muscles, '520');
  assert.equal(initial.bodies, '80');
  assert.equal(initial.meshes, '83');
  assert.equal(initial.missing, '37');
  assert.equal(initial.excluded, '12');
  assert(initial.canvas);
  const lengths = { neutral: initial.length };
  for (const mode of ['squat', 'bench', 'press']) {
    lengths[mode] = await evalPage(`(() => {
      document.querySelector('[data-mode="${mode}"]').click();
      const range = document.querySelector('#unified-timeline');
      range.value = '50'; range.dispatchEvent(new Event('input', { bubbles: true }));
      return +document.querySelector('#unified-stage').dataset.selectedLengthM;
    })()`);
    assert.equal(await evalPage(`document.querySelector('#unified-stage').dataset.mode`), mode);
    const jointText = await evalPage(`document.querySelector('#unified-joints').textContent`);
    assert(jointText.includes('人为设定的角度') && jointText.includes('°'),
      `${mode} has no source coordinate readout: ${jointText}`);
    await sleep(200);
    const poseShot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
    writeFileSync(join(process.cwd(), '.cache', `unified-${mode}-check.png`),
      Buffer.from(poseShot.result.data, 'base64'));
  }
  assert(Object.values(lengths).every(Number.isFinite), `invalid selected muscle length: ${JSON.stringify(lengths)}`);
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
