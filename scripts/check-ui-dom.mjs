// Verifies the built page in a real browser instead of only checking sources and data.
//
// The repository previously verified the interface by hand: switch to the OpenSim view, enable the
// research layer, read the status card. Those runs found real problems (a toggle that stayed
// disabled, stale sentinel text) and were written up as one-off验收 because there was no script.
// This check makes the same pass repeatable: it serves dist/, drives the page over the Chrome
// DevTools Protocol with Node's built-in WebSocket, and fails on a missing control, a view that does
// not switch, a research layer that reports a load failure, or any uncaught page error.
//
// A browser is required. Set ATLAS_BROWSER to an executable path when auto-detection fails.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { tmpdir } from 'node:os';
import { extname, join, normalize } from 'node:path';

const ROOT = process.cwd();
const DIST = join(ROOT, 'dist');
const CANDIDATES = [
  process.env.ATLAS_BROWSER,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  '/usr/bin/microsoft-edge', '/usr/bin/google-chrome', '/usr/bin/chromium',
].filter(Boolean);

const browser = CANDIDATES.find(path => existsSync(path));
if (!browser) {
  console.log('SKIPPED: no Chromium-based browser found. Set ATLAS_BROWSER to an executable path ' +
    'to run this check; the other check scripts do not need a browser.');
  process.exit(0);
}
assert(existsSync(join(DIST, 'index.html')),
  'dist/index.html is missing. Run `npm run build` before this check.');

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.json': 'application/json',
  '.glb': 'model/gltf-binary', '.png': 'image/png', '.webmanifest': 'application/manifest+json',
  '.txt': 'text/plain; charset=utf-8' };
const server = createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
  const file = join(DIST, normalize(pathname === '/' ? 'index.html' : pathname).replace(/^(\.\.[/\\])+/, ''));
  try {
    if (!statSync(file).isFile()) throw new Error('not a file');
    response.writeHead(200, { 'Content-Type': MIME[extname(file)] || 'application/octet-stream' });
    response.end(readFileSync(file));
  } catch {
    response.writeHead(404).end('not found');
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;

const debugPort = 9500 + (process.pid % 400);
const profile = mkdtempSync(join(tmpdir(), 'atlas-ui-'));
const child = spawn(browser, ['--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run',
  '--enable-unsafe-swiftshader', `--remote-debugging-port=${debugPort}`,
  `--user-data-dir=${profile}`, `${origin}/`], { stdio: 'ignore' });
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

let socket;
try {
  const target = await (async () => {
    for (let attempt = 0; attempt < 40; attempt++) {
      try {
        const list = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
        const page = list.find(item => item.type === 'page' && item.url.startsWith(origin));
        if (page) return page.webSocketDebuggerUrl;
      } catch {}
      await sleep(500);
    }
    throw new Error('the browser never exposed the page over the DevTools Protocol');
  })();

  socket = new WebSocket(target);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let nextId = 1;
  const pending = new Map();
  const pageErrors = [];
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      pending.get(message.id)(message);
      pending.delete(message.id);
    }
    if (message.method === 'Runtime.exceptionThrown') {
      pageErrors.push(message.params.exceptionDetails.exception?.description ||
        message.params.exceptionDetails.text);
    }
    if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') {
      pageErrors.push(message.params.args.map(argument => argument.value ?? argument.description).join(' '));
    }
  };
  const send = (method, params = {}) => {
    const id = nextId++;
    socket.send(JSON.stringify({ id, method, params }));
    return new Promise(resolve => pending.set(id, resolve));
  };
  const evaluate = async (expression) => {
    const reply = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (reply.result?.exceptionDetails) {
      throw new Error(`page evaluation failed: ${reply.result.exceptionDetails.text} ${expression}`);
    }
    return reply.result?.result?.value;
  };
  const waitFor = async (expression, description, attempts = 60) => {
    for (let attempt = 0; attempt < attempts; attempt++) {
      if (await evaluate(expression)) return;
      await sleep(500);
    }
    throw new Error(`timed out waiting for ${description}`);
  };

  await send('Runtime.enable');
  const verified = [];
  const check = async (name, fn) => {
    try {
      await fn();
    } catch (error) {
      throw new Error(`interface check failed — ${name}: ${error.message}`);
    }
    verified.push(name);
  };
  // Real key presses, not synthetic events: the page must react to what a keyboard actually sends.
  const pressKey = async (name, code, keyCode) => {
    for (const type of ['keyDown', 'keyUp']) {
      await send('Input.dispatchKeyEvent', { type, key: name, code, windowsVirtualKeyCode: keyCode,
        nativeVirtualKeyCode: keyCode });
    }
    await sleep(200);
  };

  await check('the application boots and creates a canvas', async () => {
    await waitFor(`!!document.querySelector('canvas')`, 'the canvas to exist');
    const size = await evaluate(`(() => { const c = document.querySelector('canvas');
      return { width: c.width, height: c.height }; })()`);
    assert(size.width > 0 && size.height > 0, `canvas has no size: ${JSON.stringify(size)}`);
  });

  await check('the measurement diagram renders every declared site', async () => {
    const rendered = await evaluate(`[...document.querySelectorAll('.measure-site')]
      .map(node => node.dataset.site).sort()`);
    const legend = await evaluate(`[...document.querySelectorAll('.measure-legend li[data-site]')]
      .map(node => node.dataset.site).sort()`);
    assert(rendered.length >= 10, `the measurement diagram rendered only ${rendered.length} sites`);
    assert.equal(new Set(rendered).size, rendered.length, `duplicate measurement sites: ${rendered}`);
    // The figure and the legend are rendered from the same list by different code paths, so a
    // mismatch means one of them dropped or renamed a site.
    assert.deepEqual(rendered, legend, 'the diagram and the legend disagree about the sites');
    // Scoped to the card: “测量位置” also appears in the figure's aria-label and the panel copy, so a
    // page-wide search would pass even if this card stopped explaining itself.
    const card = await evaluate(`(() => {
      const node = document.querySelector('details.measure-sites');
      return node ? (node.textContent ?? '').replace(/\\s+/g, ' ').trim() : null;
    })()`);
    assert(card && card.length > 20, 'the measurement card is missing or empty');
    assert(card.includes('测量位置') && card.includes('图示只说明量尺位置'),
      `the measurement card no longer explains what the diagram shows: ${(card ?? '').slice(0, 80)}`);
  });

  await check('every recorded measurement site has a form field', async () => {
    const missing = await evaluate(`[...document.querySelectorAll('.measure-site')]
      .map(node => node.dataset.site)
      .filter(name => !document.querySelector('[name="' + name + '"]'))`);
    assert.deepEqual(missing, [], `diagram sites without a form field: ${missing.join(', ')}`);
  });

  await check('the training record exposes variation, range and equipment', async () => {
    // Searching the whole page is not enough here: “器械” alone appears five times in the bundle, and
    // “变式” three times, so the labels have to be found inside the form and bound to real controls.
    const form = await evaluate(`(() => {
      const node = document.querySelector('#training-form');
      return node ? (node.textContent ?? '').replace(/\\s+/g, ' ').trim() : null;
    })()`);
    assert(form, 'the training form is missing');
    for (const label of ['变式', '实际幅度', '器械']) {
      assert(form.includes(label), `the training form is missing ${label}`);
    }
    for (const [name, label] of [['variation', '变式'], ['range', '实际幅度'], ['equipment', '器械']]) {
      // The visible caption is the label's own <span>. Reading the whole wrapper would also accept the
      // word “器械” appearing in the select's options (“固定器械”), which is not a caption at all.
      const caption = await evaluate(`(() => {
        const field = document.querySelector('#training-form [name=${JSON.stringify(name)}]');
        if (!field) return null;
        const wrapper = field.closest('label');
        if (!wrapper) return '';
        const span = wrapper.querySelector('span');
        return span ? (span.textContent ?? '').replace(/\\s+/g, ' ').trim() : '';
      })()`);
      assert(caption !== null, `the training form has no ${label} control named ${name}`);
      assert(caption === label,
        `the ${name} control is labelled “${caption}” instead of “${label}”`);
    }
  });

  await check('every exercise selector switches the action', async () => {
    const exercises = await evaluate(`[...document.querySelectorAll('[data-exercise]')]
      .map(node => node.dataset.exercise)`);
    assert(exercises.length >= 3, `expected at least three preset actions, found ${exercises.length}`);
    for (const exercise of exercises) {
      await evaluate(`document.querySelector('[data-exercise="${exercise}"]').click()`);
      const selected = await evaluate(`[...document.querySelectorAll('[data-exercise]')]
        .filter(node => node.classList.contains('selected')).map(node => node.dataset.exercise)`);
      assert.deepEqual(selected, [exercise], `selecting ${exercise} left ${selected.join(', ')} selected`);
    }
  });

  await check('each view selector switches the interface', async () => {
    const views = await evaluate(`[...document.querySelectorAll('[data-view]')].map(node => node.dataset.view)`);
    assert(views.length >= 3, `expected at least three views, found ${views.length}`);
    for (const view of views) {
      await evaluate(`document.querySelector('[data-view="${view}"]').click()`);
      const selected = await evaluate(`[...document.querySelectorAll('[data-view]')]
        .filter(node => node.classList.contains('selected')).map(node => node.dataset.view)`);
      assert.deepEqual(selected, [view], `selecting ${view} left ${selected.join(', ')} selected`);
    }
  });

  await check('the outline toggle can be switched independently', async () => {
    const toggle = `document.querySelector('#outline-toggle')`;
    await waitFor(`!!${toggle}`, 'the outline toggle to exist');
    const before = await evaluate(`${toggle}.checked`);
    await evaluate(`${toggle}.click()`);
    const after = await evaluate(`${toggle}.checked`);
    assert.notEqual(before, after, 'the outline toggle did not change state when clicked');
    await evaluate(`${toggle}.click()`);
  });

  await check('the research layer loads all registered meshes in the squat view', async () => {
    await evaluate(`document.querySelector('[data-exercise="squat"]').click()`);
    await evaluate(`document.querySelector('[data-view="opensim"]').click()`);
    const research = `document.querySelector('#registered-bones-toggle')`;
    await waitFor(`!!${research} && !${research}.disabled`,
      'the research toggle to become enabled in a squat view');
    await evaluate(`if (!${research}.checked) ${research}.click()`);
    await waitFor(`document.querySelector('#asset-tag').textContent.includes('研究叠加') && document.querySelector('#asset-tag').textContent.includes('八块肌肉')`,
      'the research layer to report a completed load', 90);
    // Everything below is scoped to the element that is supposed to say it. The research copy lives
    // in the view explanation, and searching the whole page would also accept a copy of it sitting
    // anywhere else (for example inside a collapsed card or the static page chrome).
    const explanation = await evaluate(`(() => {
      const node = document.querySelector('#view-explanation');
      return node ? (node.textContent ?? '').replace(/\\s+/g, ' ').trim() : '';
    })()`);
    const status = await evaluate(`document.querySelector('#model-status').textContent`);
    // src/model.ts fails the whole layer when any single registered mesh is missing, so a completed
    // load already implies every registered mesh matched.
    assert(!status.includes('加载失败') && !explanation.includes('解剖网格加载失败'),
      'the research layer reported a load failure');
    assert(explanation.includes('腓肠肌内侧头') && explanation.includes('砖红'),
      'the research layer copy does not describe the eighth mesh');
    assert(explanation.includes('7.6 mm') && explanation.includes('97／101 帧') &&
      explanation.includes('不穿模'),
      'the research layer description does not report the measured mesh integrity result');
  });

  await check('the lab evidence card renders the regenerated capacity figures', async () => {
    // The card lives inside a closed <details>, whose content is not rendered, so it is opened first.
    const opened = await evaluate(`(() => {
      const card = document.querySelector('#lab-evidence');
      if (!card) return false;
      card.open = true;
      return true;
    })()`);
    assert(opened, 'the squat lab evidence card is missing in the squat view');
    const text = await evaluate(`document.querySelector('#lab-evidence').innerText`);
    // These numbers come from docs/data/bilateral_deep_squat_capacity_pose_check.json through
    // scripts/export-squat-evidence.mjs, so finding them proves the whole chain reached the page.
    assert(text.includes('不可解读'),
      'the card does not carry the corrected reading of the hip-rotation capacity alert');
    assert(text.includes('202') && text.includes('16 倍'),
      'the card does not report the direction asymmetry of the capacity bound');
    assert(text.includes('右膝'),
      'the card does not point at the axis whose excess survived the re-derivation');
    assert(text.includes('153') && text.includes('1.47') && text.includes('0.57'),
      'the card does not report the length-dependent knee bound and both subjects against it');
    assert(text.includes('腰椎伸展') && text.includes('1.45'),
      'the card does not report the most robust shortfall, lumbar extension');
    assert(text.includes('不适用于研究'),
      'the card does not carry the model-provenance caveat behind the shortfall');
    assert(text.includes('1.40') && text.includes('0.36') && text.includes('未决'),
      'the card does not report the research-purpose knee re-check and its unresolved reading');
    assert(text.includes('120°') && text.includes('越界帧数为 0') && text.includes('0.90') &&
      text.includes('0.45') && text.includes('髌骨几何'),
      'the card does not report the candidate patellofemoral data range and the frame split');
    assert(text.includes('520') && text.includes('0.34') && text.includes('腰椎力量上限'),
      'the card does not report that the lumbar gap disappears on a full-body trunk model');
    assert(text.includes('不生成个人肌肉力红色高亮'),
      'the card dropped its statement that no personal muscle force is produced');
  });

  await check('the action and view tabs expose which one is selected', async () => {
    const readTabs = () => evaluate(`(() => {
      const read = (selector) => [...document.querySelectorAll(selector)].map(button => ({
        id: button.dataset.exercise ?? button.dataset.view,
        label: button.textContent.trim(),
        selected: button.classList.contains('selected'),
        pressed: button.getAttribute('aria-pressed'),
      }));
      return { exercise: read('[data-exercise]'), view: read('[data-view]') };
    })()`);
    // The selected tab is drawn with a class; a screen reader only sees aria-pressed, so the two have
    // to agree, and exactly one tab per group may claim to be pressed.
    const assertGroup = (group, tabs) => {
      const pressed = tabs.filter(tab => tab.pressed === 'true');
      assert.equal(pressed.length, 1,
        `${group}: expected exactly one pressed tab, found ${JSON.stringify(tabs)}`);
      assert.equal(pressed[0].selected, true,
        `${group}: the pressed tab ${pressed[0].label} is not the highlighted one`);
      assert.deepEqual(tabs.filter(tab => tab.selected).map(tab => tab.label), [pressed[0].label],
        `${group}: a highlighted tab does not report itself as pressed`);
      for (const tab of tabs) {
        assert.equal(tab.pressed === 'true' || tab.pressed === 'false', true,
          `${group}: tab ${tab.label} has aria-pressed=${JSON.stringify(tab.pressed)}`);
      }
    };
    const before = await readTabs();
    assertGroup('the action tabs', before.exercise);
    assertGroup('the view tabs', before.view);

    await evaluate(`document.querySelector('[data-exercise="bench"]').click()`);
    await sleep(400);
    const afterExercise = await readTabs();
    assertGroup('the action tabs after switching', afterExercise.exercise);
    assert.equal(afterExercise.exercise.find(tab => tab.pressed === 'true').label, '卧推',
      'the pressed action tab did not follow the switch');

    await evaluate(`document.querySelector('[data-view="demand"]').click()`);
    await sleep(400);
    const afterView = await readTabs();
    assertGroup('the view tabs after switching', afterView.view);
    assert.equal(afterView.view.find(tab => tab.pressed === 'true').label, '负重力学',
      'the pressed view tab did not follow the switch');

    // Put the page back the way it was found, so a later failure is not caused by this check.
    const initialExercise = before.exercise.find(tab => tab.pressed === 'true').id;
    const initialView = before.view.find(tab => tab.pressed === 'true').id;
    await evaluate(`document.querySelector('[data-exercise="${initialExercise}"]').click()`);
    await evaluate(`document.querySelector('[data-view="${initialView}"]').click()`);
    await sleep(400);
    const restored = await readTabs();
    assert.equal(restored.exercise.find(tab => tab.pressed === 'true').id, initialExercise,
      'the action tabs did not return to the state this check found');
    assert.equal(restored.view.find(tab => tab.pressed === 'true').id, initialView,
      'the view tabs did not return to the state this check found');
  });

  await check('a dragged ankle preserves bone lengths and changes OpenSim path geometry', async () => {
    await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000,
      deviceScaleFactor: 1, mobile: false });
    await evaluate(`document.querySelector('[data-exercise="squat"]').click()`);
    await evaluate(`document.querySelector('#viewer').scrollIntoView({block:'center'})`);
    await evaluate(`document.querySelector('#pose-edit-toggle').click()`);
    await waitFor(`JSON.parse(document.querySelector('#viewer').dataset.dynamicMuscles ?? '{}').poseEdited === true`,
      'pose edit mode');
    const before = await evaluate(`(() => { const v = document.querySelector('#viewer');
      return { handles: JSON.parse(v.dataset.poseHandles),
        segments: JSON.parse(v.dataset.poseSegments), muscles: JSON.parse(v.dataset.dynamicMuscles) }; })()`);
    assert.equal(before.muscles.count, 80, 'the complete lower-limb path set is missing');
    const ankle = before.handles.ankleR;
    assert(ankle.visible && Number.isFinite(ankle.x) && Number.isFinite(ankle.y),
      `the right ankle handle is unavailable: ${JSON.stringify(ankle)}`);
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: ankle.x, y: ankle.y });
    await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: ankle.x, y: ankle.y,
      button: 'left', clickCount: 1 });
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: ankle.x + 95, y: ankle.y - 65,
      button: 'left', buttons: 1 });
    await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: ankle.x + 95, y: ankle.y - 65,
      button: 'left', clickCount: 1 });
    await sleep(300);
    const after = await evaluate(`(() => { const v = document.querySelector('#viewer');
      return { handles: JSON.parse(v.dataset.poseHandles),
        segments: JSON.parse(v.dataset.poseSegments), muscles: JSON.parse(v.dataset.dynamicMuscles) }; })()`);
    assert(Math.hypot(after.handles.ankleR.x - ankle.x, after.handles.ankleR.y - ankle.y) > 10,
      'dragging the ankle did not change its position');
    for (const key of ['femurR', 'tibiaR', 'upperArmR', 'forearmR']) {
      assert(Math.abs(after.segments[key] - before.segments[key]) < 0.001,
        `${key} changed length while dragging: ${before.segments[key]} -> ${after.segments[key]}`);
    }
    assert(after.muscles.longer + after.muscles.shorter > 0,
      'the 80 OpenSim paths did not respond to the dragged ankle');
    assert.equal(after.muscles.wrappingRecalculated, false,
      'the app must not claim to recompute OpenSim wrapping');
    await evaluate(`document.querySelector('#pose-reset').click()`);
    const reset = await evaluate(`JSON.parse(document.querySelector('#viewer').dataset.dynamicMuscles)`);
    assert.equal(reset.longer + reset.shorter, 0, 'reset did not restore the preset pose');
    await evaluate(`document.querySelector('#pose-edit-toggle').click()`);
    assert.equal(await evaluate(`document.querySelector('#timeline').disabled`), false,
      'the timeline stayed disabled after leaving pose edit mode');
  });

  await check('the model rotates from the keyboard like it does from a pointer', async () => {
    const label = await evaluate(`document.querySelector('#viewer').getAttribute('aria-label')`);
    assert(label && label.includes('方向键'),
      `the viewer does not tell a keyboard user how to rotate it: ${label}`);
    const orientation = () => evaluate(`document.querySelector('#viewer').dataset.orientation ?? ''`);
    await evaluate(`document.querySelector('#viewer').focus()`);
    assert.equal(await evaluate(`document.activeElement.id`), 'viewer',
      'the model container cannot take keyboard focus');
    const start = await orientation();
    assert(/^-?\d+\.\d+,-?\d+\.\d+$/.test(start),
      `the viewer does not expose its orientation: ${JSON.stringify(start)}`);

    await pressKey('ArrowRight', 'ArrowRight', 39);
    const turned = (await orientation()).split(',').map(Number);
    const initial = start.split(',').map(Number);
    assert(Math.abs(turned[0] - initial[0] - 0.08) < 0.002,
      `ArrowRight did not turn the model by one step: ${start} -> ${turned.join(',')}`);
    assert(Math.abs(turned[1] - initial[1]) < 0.002,
      `ArrowRight also tilted the model: ${start} -> ${turned.join(',')}`);

    await pressKey('ArrowUp', 'ArrowUp', 38);
    const tiltedText = await orientation();
    const tilted = tiltedText.split(',').map(Number);
    assert(Math.abs(tilted[1] - turned[1] + 0.08) < 0.002,
      `ArrowUp did not tilt the model by one step: ${turned.join(',')} -> ${tiltedText}`);
    assert(Math.abs(tilted[0] - turned[0]) < 0.002,
      `ArrowUp also turned the model: ${turned.join(',')} -> ${tiltedText}`);

    // A key that is not a rotation must leave the camera alone.
    await pressKey('a', 'KeyA', 65);
    assert.equal(await orientation(), tiltedText, 'a letter key moved the camera');
  });

  await check('the model zooms from the keyboard like the wheel does', async () => {
    // This behaviour leaves the camera at the far zoom bound; no behaviour after it reads the camera.
    const label = await evaluate(`document.querySelector('#viewer').getAttribute('aria-label')`);
    assert(label && label.includes('缩放'),
      `the viewer does not tell a keyboard user how to zoom it: ${label}`);
    const distance = () => evaluate(`Number(document.querySelector('#viewer').dataset.distance)`);
    const orientation = () => evaluate(`document.querySelector('#viewer').dataset.orientation ?? ''`);
    await evaluate(`document.querySelector('#viewer').focus()`);
    const startDistance = await distance();
    assert(Number.isFinite(startDistance) && startDistance >= 1.7 && startDistance <= 6,
      `the viewer does not expose a usable distance: ${startDistance}`);
    const startOrientation = await orientation();

    await pressKey('PageUp', 'PageUp', 33);
    const zoomedIn = await distance();
    assert(Math.abs(zoomedIn - (startDistance - 0.25)) < 0.002,
      `PageUp did not zoom in by one step: ${startDistance} -> ${zoomedIn}`);
    await pressKey('-', 'Minus', 189);
    assert(Math.abs(await distance() - startDistance) < 0.002,
      'the minus key did not undo one PageUp step');
    await pressKey('=', 'Equal', 187);
    assert(Math.abs(await distance() - (startDistance - 0.25)) < 0.002,
      'the equals key did not zoom in by one step');

    // Both ends are bounded, exactly like the wheel handler.
    for (let index = 0; index < 30; index++) await pressKey('PageUp', 'PageUp', 33);
    assert.equal(await distance(), 1.7, 'zooming in past the near bound did not stop at 1.7');
    for (let index = 0; index < 30; index++) await pressKey('PageDown', 'PageDown', 34);
    assert.equal(await distance(), 6, 'zooming out past the far bound did not stop at 6');
    assert.equal(await orientation(), startOrientation, 'zooming also moved the camera around');

    // A key that is not a zoom must leave the distance alone.
    await pressKey('a', 'KeyA', 65);
    assert.equal(await distance(), 6, 'a letter key zoomed the model');
  });

  await check('the page states which build it is running', async () => {
    // The footer is the only place the page names its build, and it must agree with both the service
    // worker that serves the offline bundle and the source that expects that bundle. On the native
    // container the footer is the only place the identity appears at all, so it is what a phone report
    // can quote back.
    const shown = await evaluate(`document.querySelector('#build-identity').textContent.trim()`);
    const marker = /muscle-atlas-v[0-9]+/.exec(readFileSync(join(ROOT, 'public/sw.js'), 'utf8'))?.[0];
    assert(marker, 'public/sw.js no longer names a cache marker');
    assert(shown.includes(marker),
      `the page says ${JSON.stringify(shown)} but the service worker serves ${marker}`);
    assert(readFileSync(join(ROOT, 'src/main.ts'), 'utf8').includes(`'${marker}'`),
      `src/main.ts does not expect the cache marker ${marker}`);
    const visible = await evaluate(`(() => { const node = document.querySelector('#build-identity');
      return node !== null && node.getClientRects().length > 0; })()`);
    assert(visible, 'the build identity is not visible on the page');
  });

  await check('the page raised no uncaught error', () => {
    assert.deepEqual(pageErrors, [], `the page reported errors: ${pageErrors.join(' | ')}`);
  });

  console.log(`${verified.length} interface behaviours verified in ${browser.split(/[\\/]/).pop()} ` +
    `against the production build:\n  - ${verified.join('\n  - ')}`);
} finally {
  try { socket?.close(); } catch {}
  child.kill();
  await new Promise(resolve => { server.close(resolve); setTimeout(resolve, 1500); });
  // Edge keeps helper processes alive after the parent exits on Windows.
  if (process.platform === 'win32') {
    spawn('taskkill', ['/F', '/T', '/PID', String(child.pid)], { stdio: 'ignore' });
    await sleep(500);
  }
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}
