// Guards the stage-3 acceptance rule that every output carries a source and a confidence statement.
//
// The interface marks each element that shows a computed number with data-output／data-status／
// data-source, and docs/data/output_provenance.json registers what each of those means and which
// wording must sit next to it. This check serves the production build, walks the DOM in a real
// browser — including the bench and press views and the research layer, where the caveats differ —
// and fails when a registered output changes its status, loses its caveat sentence, shows a number it
// no longer qualifies, or when an output appears in the page without being registered.
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

const provenance = JSON.parse(readFileSync('docs/data/output_provenance.json', 'utf8'));
const main = readFileSync('src/main.ts', 'utf8');

// Static assertions first: the registration itself has to stay coherent.
assert.equal(provenance.status, 'browser_checked_output_provenance');
assert(provenance.limitations.length >= 4, 'the provenance data lost its limitations');
assert(provenance.limitations.some(text => text.includes('不证明')),
  'the provenance data must keep saying it does not prove the caveat correct');
assert(provenance.limitations.some(text => text.includes('未登记') || text.includes('评审')),
  'the provenance data must keep admitting the unregistered-container gap');
assert(provenance.outputs.length >= 10, 'too few registered outputs to be meaningful');
for (const name of provenance.unusedStatuses) {
  const used = provenance.outputs.filter(item => item.status === name);
  assert.deepEqual(used, [],
    `the status ${name} is declared unused but ${used.length} output(s) claim it`);
}
for (const item of provenance.outputs) {
  assert(provenance.vocabulary[item.status], `${item.id} uses an undocumented status ${item.status}`);
  assert(item.source && item.source.length > 3, `${item.id} has no source id`);
  assert(item.caveatTokens.length >= 1, `${item.id} declares no caveat wording`);
  assert(item.meaning && item.meaning.length > 8, `${item.id} has no written meaning`);
  assert(main.includes(`data-output="${item.id}"`),
    `${item.id} is registered but not marked in src/main.ts`);
  assert(main.includes(`data-source="${item.source}"`),
    `${item.id} does not carry its registered data-source in src/main.ts`);
  assert(main.includes(`data-status="${item.status}"`),
    `${item.id} does not carry its registered data-status in src/main.ts`);
}
assert(provenance.vocabulary.measured, 'the vocabulary lost the measured category');
assert(provenance.vocabulary.measured.meaning.includes('没有'),
  'the measured category must explain that nothing measures the user yet');
// The state table is what stops a registered output from passing by being empty.
assert(provenance.states && Object.keys(provenance.states).length >= 5,
  'the registry lost the interface states it checks');
assert(provenance.statePolicy && provenance.statePolicy.includes('清空'),
  'the registry must keep explaining why “has a caveat when it shows a number” is not enough');
for (const item of provenance.outputs) {
  assert(item.shows && Object.keys(item.shows).length >= 1,
    `${item.id} is never required to actually display anything`);
  for (const [state, expectation] of Object.entries(item.shows)) {
    assert(provenance.states[state], `${item.id} names an undocumented state ${state}`);
    assert(['digits', 'text'].includes(expectation),
      `${item.id} declares an unknown expectation ${expectation} in ${state}`);
  }
}
for (const state of Object.keys(provenance.states)) {
  const covering = provenance.outputs.filter(item => item.shows?.[state]);
  assert(covering.length >= 1, `no output is checked in the ${state} state`);
}

const browser = CANDIDATES.find(path => existsSync(path));
if (!browser) {
  console.log('SKIPPED: no Chromium-based browser found. Set ATLAS_BROWSER to an executable path ' +
    'to run the browser half of this check; the registration half above already passed.');
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

const debugPort = 9700 + (process.pid % 200);
const profile = mkdtempSync(join(tmpdir(), 'atlas-prov-'));
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
      throw new Error(`output provenance check failed — ${name}: ${error.message}`);
    }
    verified.push(name);
  };

  // Reads every registered output at once: whether it occupies layout, and what it says.
  const readOutputs = () => evaluate(`[...document.querySelectorAll('[data-output]')].map(node => ({
    id: node.dataset.output,
    visible: node.getClientRects().length > 0,
    text: (node.textContent ?? '').replace(/\\s+/g, ' ').trim(),
  }))`);
  // The state table in the registry is what turns “shows a number only with a caveat” into “shows the
  // number it is supposed to show”: a container that silently empties out fails here.
  const assertState = async (state, readings) => {
    for (const item of provenance.outputs) {
      const expectation = item.shows?.[state];
      const reading = readings.find(entry => entry.id === item.id);
      assert(reading, `${item.id} is registered but missing from the page`);
      if (!expectation) {
        assert(!reading.visible || reading.text.length === 0,
          `${item.id} is showing “${reading.text.slice(0, 60)}” in the ${state} state, ` +
          `where the registry does not expect it`);
        continue;
      }
      assert(reading.visible,
        `${item.id} is registered as showing in the ${state} state but is not visible`);
      // A prompt such as “尚无训练记录” is short on purpose; a container that shows a number has to
      // carry both the number and its caveat, so it is held to a longer minimum.
      assert(reading.text.length > (expectation === 'text' ? 0 : 8),
        `${item.id} is visible but empty in the ${state} state`);
      if (expectation === 'text') continue;
      assert(expectation === 'digits', `${item.id} declares an unknown expectation ${expectation}`);
      assert(/\d/.test(reading.text),
        `${item.id} should show a number in the ${state} state but says “${reading.text.slice(0, 80)}”`);
      const matched = item.caveatTokens.filter(token => reading.text.includes(token));
      assert(matched.length >= 1,
        `${item.id} shows “${reading.text.slice(0, 80)}” in the ${state} state with no caveat from ` +
        `${item.caveatTokens.join(' / ')}`);
    }
    assert.equal(readings.length, provenance.outputs.length,
      `the ${state} state has ${readings.length} marked outputs, the registry lists ` +
      `${provenance.outputs.length}`);
  };

  await check('the page boots and marks only registered outputs', async () => {
    await waitFor(`!!document.querySelector('canvas')`, 'the canvas to exist');
    const marked = await evaluate(`[...document.querySelectorAll('[data-output]')]
      .map(node => node.dataset.output).sort()`);
    const registered = provenance.outputs.map(item => item.id).sort();
    assert.deepEqual(marked, registered,
      'the page and docs/data/output_provenance.json disagree about which outputs exist');
  });

  await check('every marked output carries its registered status and source', async () => {
    for (const item of provenance.outputs) {
      const attributes = await evaluate(`(() => {
        const node = document.querySelector('[data-output=${JSON.stringify(item.id)}]');
        return node ? { status: node.dataset.status, source: node.dataset.source } : null;
      })()`);
      assert(attributes, `${item.id} is registered but missing from the page`);
      assert.equal(attributes.status, item.status, `${item.id} reports status ${attributes.status}`);
      assert.equal(attributes.source, item.source, `${item.id} reports source ${attributes.source}`);
      assert(provenance.vocabulary[attributes.status],
        `${item.id} uses a status outside the vocabulary`);
    }
  });

  await check('the default view shows every output the registry expects there', async () => {
    await assertState('default', await readOutputs());
  });

  await check('a recorded set keeps the estimate qualified', async () => {
    const seeded = await evaluate(`(() => {
      const form = document.querySelector('#training-form');
      const values = { loadKg: '100', repetitions: '5', rir: '2', equipment: 'barbell' };
      for (const [name, value] of Object.entries(values)) {
        const input = form.querySelector('[name="' + name + '"]');
        if (!input) return name;
        input.value = value;
        input.dispatchEvent(new Event('change', { bubbles: true }));
      }
      form.requestSubmit();
      return true;
    })()`);
    assert.equal(seeded, true, `the training form has no field named ${seeded}`);
    await waitFor(`document.querySelector('[data-output="capacity-hint"]').textContent.includes('粗估') ||
      document.querySelector('[data-output="capacity-hint"]').textContent.includes('1RM')`,
      'the capacity hint to be filled');
    const readings = await readOutputs();
    await assertState('recorded', readings);
    const capacity = readings.find(entry => entry.id === 'capacity-hint');
    assert(capacity.text.includes('1RM') || /%。/.test(capacity.text),
      `the capacity hint no longer states a share of the estimated 1RM: ${capacity.text}`);
  });

  await check('the demand-view study overlay keeps its reference wording', async () => {
    await evaluate(`document.querySelector('[data-exercise="squat"]').click()`);
    await evaluate(`document.querySelector('[data-view="demand"]').click()`);
    await waitFor(`!document.querySelector('#squat-demand-mode-control').hidden`,
      'the squat demand mode control to appear');
    await evaluate(`(() => {
      const select = document.querySelector('#squat-demand-mode');
      select.value = 'study';
      select.dispatchEvent(new Event('change', { bubbles: true }));
    })()`);
    await waitFor(`!document.querySelector('[data-output="viewer-research-readout"]').hidden`,
      'the study readout to appear', 30);
    await assertState('squat-study', await readOutputs());
  });

  await check('the bench and press views keep their reference wording', async () => {
    for (const [exercise, state] of [['bench', 'bench'], ['press', 'press']]) {
      await evaluate(`document.querySelector('[data-exercise="${exercise}"]').click()`);
      await sleep(1500);
      await assertState(state, await readOutputs());
    }
  });

  await check('the page raised no uncaught error', () => {
    assert.deepEqual(pageErrors, [], `the page reported errors: ${pageErrors.join(' | ')}`);
  });

  console.log(`Output provenance verified in ${browser.split(/[\\/]/).pop()}: ` +
    `${provenance.outputs.length} registered outputs carry a status, a source and a caveat across ` +
    `${Object.keys(provenance.states).length} interface states ` +
    `(${Object.keys(provenance.vocabulary).filter(name => !provenance.unusedStatuses.includes(name))
      .join(', ')} in use; ` +
    `${provenance.unusedStatuses.join(', ')} deliberately unused), and each one is required to be ` +
    `visible with content where the registry says so — the check is about wording, not about ` +
    `whether the wording is right.`);
} finally {
  try { socket?.close(); } catch {}
  child.kill();
  await new Promise(resolve => { server.close(resolve); setTimeout(resolve, 1500); });
  if (process.platform === 'win32') {
    spawn('taskkill', ['/F', '/T', '/PID', String(child.pid)], { stdio: 'ignore' });
    await sleep(500);
  }
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}
