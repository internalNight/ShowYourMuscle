// Verifies the user-data flows in a real browser, not only in unit-level data checks.
//
// Two claims in this project are about the user's own data and were previously only checked by hand:
// that parameters and records survive a reload, and that the exported backup file contains exactly the
// profile and the training records (docs/隐私与本地数据.md). This check drives the built page over the
// Chrome DevTools Protocol — filling the form, recording a barbell set and a dumbbell set, exporting
// through the page's own download path, wiping storage, importing the same file back — and fails if the
// interface loses data, if the 1RM pool rule changes, if the backup carries anything else, or if the
// narrow phone layout starts scrolling sideways.
//
// A browser is required. Set ATLAS_BROWSER to an executable path when auto-detection fails.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
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

const debugPort = 9900 + (process.pid % 100);
const profile = mkdtempSync(join(tmpdir(), 'atlas-data-'));
const downloads = mkdtempSync(join(tmpdir(), 'atlas-downloads-'));
const child = spawn(browser, ['--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run',
  '--enable-unsafe-swiftshader', `--remote-debugging-port=${debugPort}`,
  `--user-data-dir=${profile}`, `${origin}/`], { stdio: 'ignore' });
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

const PROFILE_INPUTS = { heightCm: '176', weightKg: '78', bodyFatPct: '18', thighCm: '58', calfCm: '38' };
const BARBELL = { loadKg: '100', repetitions: '5', rir: '2', equipment: 'barbell' };
const DUMBBELL = { loadKg: '30', repetitions: '8', rir: '1', equipment: 'dumbbell' };
// Epley with the reserve reps folded in, exactly as src/domain.ts defines the estimate.
const BARBELL_ESTIMATE = (100 * (1 + (5 + 2) / 30)).toFixed(1);

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
  const setInput = (selector, value) => evaluate(`(() => {
    const input = document.querySelector(${JSON.stringify(selector)});
    if (!input) return false;
    input.value = ${JSON.stringify(value)};
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  })()`);

  await send('Runtime.enable');
  await send('Page.enable');
  await send('DOM.enable');
  await send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: downloads })
    .catch(() => {});
  await send('Page.setDownloadBehavior', { behavior: 'allow', downloadPath: downloads }).catch(() => {});

  const verified = [];
  const check = async (name, fn) => {
    try {
      await fn();
    } catch (error) {
      throw new Error(`data flow check failed — ${name}: ${error.message}`);
    }
    verified.push(name);
  };

  await check('the page boots', async () => {
    await waitFor(`!!document.querySelector('canvas')`, 'the canvas to exist');
    await waitFor(`!!document.querySelector('#profile-form')`, 'the profile form to exist');
  });

  // The browser profile is fresh, so whatever the form shows at boot is the built-in default; the wipe
  // step later compares against these instead of hard-coding numbers that could drift.
  const defaults = await evaluate(`(() => {
    const form = document.querySelector('#profile-form');
    const out = {};
    for (const name of ['heightCm', 'weightKg', 'bodyFatPct', 'thighCm', 'calfCm']) {
      out[name] = form.querySelector('[name="' + name + '"]')?.value ?? null;
    }
    return out;
  })()`);
  assert(Object.values(defaults).every(value => value !== null),
    `the profile form is missing a default field: ${JSON.stringify(defaults)}`);

  await check('body parameters save and survive a reload', async () => {
    for (const [name, value] of Object.entries(PROFILE_INPUTS)) {
      assert(await setInput(`#profile-form [name="${name}"]`, value), `no input named ${name}`);
    }
    await evaluate(`document.querySelector('#profile-form').requestSubmit()`);
    await waitFor(`document.querySelector('#profile-message').textContent.includes('已更新')`,
      'the profile save message');
    const stored = JSON.parse(await evaluate(`localStorage.getItem('muscle-atlas-profile-v1')`));
    // Every entered field, not a sample: the earlier version of this check looked at two of the five.
    for (const [name, value] of Object.entries(PROFILE_INPUTS)) {
      assert.equal(stored[name], Number(value),
        `the stored ${name} (${stored[name]}) differs from the entered ${value}`);
    }

    await evaluate(`location.reload()`);
    await waitFor(`!!document.querySelector('#profile-form [name="heightCm"]')`, 'the form after reload');
    const afterReload = await evaluate(`(() => {
      const form = document.querySelector('#profile-form');
      const out = {};
      for (const name of ['heightCm', 'weightKg', 'bodyFatPct', 'thighCm', 'calfCm']) {
        out[name] = form.querySelector('[name="' + name + '"]').value;
      }
      return out;
    })()`);
    assert.deepEqual(afterReload, PROFILE_INPUTS,
      `the form lost a saved value after a reload: ${JSON.stringify(afterReload)}`);
  });

  await check('a barbell set enters the 1RM pool and a dumbbell set does not', async () => {
    const addRecord = async (record) => {
      for (const [name, value] of Object.entries(record)) {
        assert(await setInput(`#training-form [name="${name}"]`, value),
          `no training input named ${name}`);
      }
      await evaluate(`document.querySelector('#training-form').requestSubmit()`);
      await sleep(400);
    };
    await addRecord(BARBELL);
    await waitFor(`document.querySelector('#training-list').innerText.includes(${JSON.stringify(BARBELL_ESTIMATE)})`,
      `the barbell estimate ${BARBELL_ESTIMATE} to appear`);
    const barbellRows = await evaluate(`[...document.querySelectorAll('#training-list .training-row')]
      .filter(row => row.innerText.includes('估算动作 1RM')).length`);
    assert.equal(barbellRows, 1, `expected one estimated row, found ${barbellRows}`);

    await addRecord(DUMBBELL);
    const afterDumbbell = await evaluate(`(() => {
      const rows = [...document.querySelectorAll('#training-list .training-row')];
      return {
        rows: rows.length,
        estimated: rows.filter(row => row.innerText.includes('估算动作 1RM')).length,
        dumbbell: rows.filter(row => row.innerText.includes('30 kg')).map(row => row.innerText)[0] ?? '',
      };
    })()`);
    assert.equal(afterDumbbell.rows, 2, `expected two records, found ${afterDumbbell.rows}`);
    assert.equal(afterDumbbell.estimated, 1,
      'the dumbbell record entered the barbell 1RM pool');
    assert(afterDumbbell.dumbbell.includes('1RM 粗估'),
      'the dumbbell record no longer says it stays out of the 1RM pool');
    const stored = JSON.parse(await evaluate(`localStorage.getItem('muscle-atlas-training-v1')`));
    assert.equal(stored.length, 2, 'the training records were not stored');
    assert.equal(stored[0].equipment, 'barbell', 'the first stored record is not the barbell set');
    assert.equal(stored[1].equipment, 'dumbbell', 'the second stored record is not the dumbbell set');
    assert(stored[0].recordedAt, 'the stored record lost its timestamp');
  });

  await check('the record list can be filtered and expanded without changing the data', async () => {
    const add = async (record) => {
      for (const [name, value] of Object.entries(record)) {
        assert(await setInput(`#training-form [name="${name}"]`, value),
          `no training input named ${name}`);
      }
      await evaluate(`document.querySelector('#training-form').requestSubmit()`);
      await sleep(350);
    };
    // Six more records on top of the two from the previous flow, so the five-row default really hides some.
    for (let index = 0; index < 3; index++) {
      await add({ exercise: 'squat', loadKg: String(90 + index * 5), repetitions: '5', equipment: 'barbell' });
      await add({ exercise: 'bench', loadKg: String(60 + index * 5), repetitions: '5', equipment: 'barbell' });
    }
    const listState = () => evaluate(`(() => {
      const rows = [...document.querySelectorAll('#training-list .training-row')];
      const button = document.querySelector('#training-show-all');
      return {
        rows: rows.length,
        bench: rows.filter(row => row.innerText.includes('卧推')).length,
        squat: rows.filter(row => row.innerText.includes('深蹲')).length,
        count: document.querySelector('#training-count').textContent,
        label: button.textContent,
        pressed: button.getAttribute('aria-pressed'),
        disabled: button.disabled,
        title: document.querySelector('#training-list .summary-title')?.textContent ?? '',
        capacity: document.querySelector('#capacity-hint').innerText,
        stored: JSON.parse(localStorage.getItem('muscle-atlas-training-v1')).length,
        storageKeys: Object.keys(localStorage).sort().join(','),
        query: document.querySelector('#training-search').value,
        sort: document.querySelector('#training-sort').value,
        loads: rows.map(row => Number(/([\\d.]+) kg/.exec(row.innerText)?.[1] ?? 'NaN')),
        estimates: rows.map(row => /估算动作 1RM ≈ ([\\d.]+) kg/.exec(row.innerText)?.[1])
          .filter(Boolean).map(Number),
        estimateFlags: rows.map(row => /估算动作 1RM ≈ ([\\d.]+) kg/.test(row.innerText)),
      };
    })()`);
    const collapsed = await listState();
    assert.equal(collapsed.stored, 8, `expected eight stored records, found ${collapsed.stored}`);
    assert.equal(collapsed.rows, 5, `the list should show five rows by default, found ${collapsed.rows}`);
    assert.equal(collapsed.title, '最近记录', 'the collapsed list no longer says it is the recent five');
    assert.equal(collapsed.pressed, 'false', 'the expand button starts pressed');
    assert(collapsed.count.includes('共 8 条记录') && collapsed.count.includes('当前显示 5 条'),
      `the count does not say what is hidden: ${collapsed.count}`);

    await evaluate(`document.querySelector('#training-show-all').click()`);
    await sleep(200);
    const expanded = await listState();
    assert.equal(expanded.rows, 8, `expanding should show every record, found ${expanded.rows}`);
    assert.equal(expanded.title, '全部记录', 'the expanded list still calls itself the recent five');
    assert.equal(expanded.pressed, 'true', 'the expand button does not report its pressed state');
    assert(expanded.disabled === false, 'the expand button cannot be collapsed again');
    assert(expanded.label.includes('只显示最近 5 条'),
      `the expand button does not offer to collapse: ${expanded.label}`);

    // Filtering is display-only: the stored records and the capacity pool must not move.
    await evaluate(`(() => { const select = document.querySelector('#training-filter');
      select.value = 'bench'; select.dispatchEvent(new Event('change')); })()`);
    await sleep(200);
    const filtered = await listState();
    assert.equal(filtered.rows, 3, `filtering to bench should show the three bench sets, found ${filtered.rows}`);
    assert.equal(filtered.squat, 0, 'a squat row survived the bench filter');
    assert.equal(filtered.stored, 8, 'filtering changed the stored records');
    assert.equal(filtered.capacity, collapsed.capacity, 'filtering changed the capacity estimate');
    assert(filtered.count.includes('该动作共 3 条'), `the filtered count is wrong: ${filtered.count}`);

    await evaluate(`(() => { const select = document.querySelector('#training-filter');
      select.value = 'press'; select.dispatchEvent(new Event('change')); })()`);
    await sleep(200);
    const empty = await listState();
    assert.equal(empty.rows, 0, `an action with no records still showed ${empty.rows} rows`);
    const prompt = await evaluate(`document.querySelector('#training-list').innerText`);
    assert(prompt.includes('这个动作还没有记录。'),
      `the empty filter does not explain itself: ${prompt.slice(0, 60)}`);

    // Search is display-only as well: it narrows the rows, the count line keeps the unfiltered total, and
    // neither the stored records nor the capacity estimate may move.
    const search = async (text) => {
      await evaluate(`(() => { const select = document.querySelector('#training-filter');
        select.value = 'all'; select.dispatchEvent(new Event('change'));
        const input = document.querySelector('#training-search');
        input.value = ${JSON.stringify(text)}; input.dispatchEvent(new Event('input'));
        const showAll = document.querySelector('#training-show-all');
        if (showAll.textContent.includes('只显示')) showAll.click(); })()`);
      await sleep(200);
      return listState();
    };
    const cleared = await search('');
    assert.equal(cleared.rows, 5, `clearing the search should return the five-row default, found ${cleared.rows}`);
    const nineties = await search('90');
    assert.equal(nineties.rows, 1, `searching for 90 should match one set, found ${nineties.rows}`);
    assert(nineties.count.includes('共 8 条记录') && nineties.count.includes('当前显示 1 条'),
      `the count does not separate the search from the total: ${nineties.count}`);
    assert.equal(nineties.stored, 8, 'searching changed the stored records');
    assert.equal(nineties.capacity, collapsed.capacity, 'searching changed the capacity estimate');
    const unmatched = await search('史密斯');
    assert.equal(unmatched.rows, 0, `a search with no match still showed ${unmatched.rows} rows`);
    const searchPrompt = await evaluate(`document.querySelector('#training-list').innerText`);
    assert(searchPrompt.includes('没有匹配这条搜索的记录。'),
      `the empty search does not explain itself: ${searchPrompt.slice(0, 60)}`);

    // Sorting is display order only. Each order is required to be non-increasing, and the sorted view must
    // stop claiming to be the recent five; the dumbbell set never enters the 1RM pool, so it has no
    // estimate and must not be counted among the estimated rows either.
    await evaluate(`(() => { const input = document.querySelector('#training-search');
      input.value = ''; input.dispatchEvent(new Event('input'));
      const sort = document.querySelector('#training-sort');
      sort.value = 'load'; sort.dispatchEvent(new Event('change'));
      document.querySelector('#training-show-all').click(); })()`);
    await sleep(250);
    const byLoad = await listState();
    assert.equal(byLoad.rows, 8, `sorting by load should show every record, found ${byLoad.rows}`);
    assert(byLoad.loads.every((value, index) => index === 0 || byLoad.loads[index - 1] >= value),
      `the load order is not descending: ${byLoad.loads.join(', ')}`);
    assert.equal(byLoad.title, '重量优先', `the sorted list does not say how it is sorted: ${byLoad.title}`);
    assert(byLoad.label.includes('只显示前 5 条'),
      `the sorted list still offers to collapse to the recent five: ${byLoad.label}`);
    assert.equal(byLoad.stored, 8, 'sorting changed the stored records');
    assert.equal(byLoad.capacity, collapsed.capacity, 'sorting changed the capacity estimate');

    await evaluate(`(() => { const sort = document.querySelector('#training-sort');
      sort.value = 'estimate'; sort.dispatchEvent(new Event('change')); })()`);
    await sleep(250);
    const byEstimate = await listState();
    assert(byEstimate.estimates.every((value, index) => index === 0 || byEstimate.estimates[index - 1] >= value),
      `the estimate order is not descending: ${byEstimate.estimates.join(', ')}`);
    // Only records with a known proximity to failure get an estimate at all, and the sort must put every
    // record that has one above every record that does not — otherwise the list claims an order it lacks.
    const firstWithout = byEstimate.estimateFlags.indexOf(false);
    assert(byEstimate.estimates.length > 0 && firstWithout !== -1,
      `the estimate sort needs both kinds of record: rows ${byEstimate.rows}, ` +
      `estimates ${byEstimate.estimates.length}`);
    assert(!byEstimate.estimateFlags.slice(firstWithout).includes(true),
      `a record without an estimate is listed above one with an estimate: ${byEstimate.estimateFlags}`);
    assert.equal(byEstimate.capacity, collapsed.capacity, 'sorting changed the capacity estimate');

    // Neither control is persisted: a reload returns to the default view, and no new storage key exists.
    await evaluate(`location.reload()`);
    await waitFor(`!!document.querySelector('#training-filter')`, 'the filter after a reload');
    const reloaded = await listState();
    assert.equal(reloaded.storageKeys, collapsed.storageKeys,
      `the record controls added a storage key: ${reloaded.storageKeys}`);
    assert.equal(await evaluate(`document.querySelector('#training-filter').value`), 'all',
      'the action filter survived a reload');
    assert.equal(reloaded.query, '', 'the search text survived a reload');
    assert.equal(reloaded.sort, 'recent', 'the sort order survived a reload');
    assert.equal(reloaded.rows, 5, `the reloaded list should be collapsed again, found ${reloaded.rows}`);

    // Leave the store as the later flows expect it. The six records added above are the newest, so
    // deleting from the top six times restores the two records the export flow exported.
    await evaluate(`window.confirm = () => true`);
    for (let index = 0; index < 6; index++) {
      await evaluate(`document.querySelector('#training-list .delete-button').click()`);
      await sleep(250);
    }
    assert.equal(await evaluate(`JSON.parse(localStorage.getItem('muscle-atlas-training-v1')).length`), 2,
      'the filter flow did not restore the two records it found');
  });

  await check('the exported backup contains only the profile and the records', async () => {
    // Change a setting the app persists but the backup must not carry, so the exclusion is exercised
    // rather than assumed.
    await evaluate(`document.querySelector('[data-exercise="bench"]').click()`);
    await waitFor(`(localStorage.getItem('muscle-atlas-exercise-v1') ?? '').includes('bench')`,
      'the exercise choice to be persisted');
    // The browser export prefers the Web Share API on Windows; force the download path so the file
    // this check inspects is the one the page builds.
    await evaluate(`Object.defineProperty(navigator, 'canShare', { value: () => false, configurable: true })`);
    await evaluate(`document.querySelector('#backup-export').click()`);
    const file = await (async () => {
      for (let attempt = 0; attempt < 40; attempt++) {
        const found = readdirSync(downloads).filter(name => name.endsWith('.json'));
        if (found.length) return join(downloads, found[0]);
        await sleep(500);
      }
      throw new Error(`no backup file appeared in ${downloads}; the page said ` +
        `${await evaluate(`document.querySelector('#backup-message').textContent`)}`);
    })();
    const backup = JSON.parse(readFileSync(file, 'utf8'));
    assert.deepEqual(Object.keys(backup).sort(),
      ['exportedAt', 'format', 'profile', 'training', 'version'],
      `the backup carries unexpected keys: ${Object.keys(backup).join(', ')}`);
    assert.equal(backup.format, 'muscle-atlas-local-backup', 'the backup format marker changed');
    assert.equal(backup.version, 1, 'the backup version changed');
    assert(Number.isFinite(Date.parse(backup.exportedAt)), 'the backup has no usable timestamp');
    assert.equal(backup.profile.heightCm, 176, 'the backup lost the height');
    assert.equal(backup.profile.calfCm, 38, 'the backup lost a circumference');
    assert.equal(backup.training.length, 2, 'the backup lost training records');
    assert.equal(backup.training[0].equipment, 'barbell', 'the backup reordered the records');

    // The other saved settings must stay out of the file, which is the claim on the privacy page.
    const appKeys = await evaluate(`Object.keys(localStorage).sort()`);
    const excluded = appKeys.filter(key => key !== 'muscle-atlas-profile-v1' &&
      key !== 'muscle-atlas-training-v1');
    assert(excluded.length >= 1,
      'expected at least one local setting that stays out of the backup, found none');
    assert(excluded.includes('muscle-atlas-exercise-v1'),
      `the exercise choice was not persisted at all: ${appKeys.join(', ')}`);
    const serialised = JSON.stringify(backup);
    for (const key of excluded) {
      assert(!serialised.includes(key), `${key} leaked into the backup file`);
    }
    assert(!serialised.includes('bench'),
      'the saved exercise choice leaked into the backup file');
  });

  await check('importing the backup restores the wiped data', async () => {
    const file = readdirSync(downloads).filter(name => name.endsWith('.json'))
      .map(name => join(downloads, name))[0];
    assert(file, 'no exported backup to import');
    await evaluate(`localStorage.clear()`);
    await evaluate(`location.reload()`);
    await waitFor(`!!document.querySelector('#training-form')`, 'the form after wiping storage');
    const wiped = await evaluate(`(() => {
      const form = document.querySelector('#profile-form');
      const out = { rows: document.querySelectorAll('#training-list .training-row').length };
      for (const name of ['heightCm', 'weightKg', 'bodyFatPct', 'thighCm', 'calfCm']) {
        out[name] = form.querySelector('[name="' + name + '"]').value;
      }
      return out;
    })()`);
    assert.equal(wiped.rows, 0, `expected no records after the wipe, found ${wiped.rows}`);
    // The wipe has to reach the stored profile too, not only the records, or “restoring” proves nothing.
    for (const [name, value] of Object.entries(defaults)) {
      assert.equal(wiped[name], value,
        `the wiped profile still shows ${name}=${wiped[name]} instead of the default ${value}`);
    }
    await evaluate(`window.confirm = () => true`);

    const document_ = await send('DOM.getDocument', { depth: -1 });
    const root = document_.result.root.nodeId;
    const input = await send('DOM.querySelector', { nodeId: root, selector: '#backup-file' });
    assert(input.result?.nodeId, 'the backup file input is missing');
    await send('DOM.setFileInputFiles', { nodeId: input.result.nodeId, files: [file] });
    await waitFor(`document.querySelector('#backup-message').textContent.includes('已从本地备份恢复')`,
      'the import confirmation message');
    const restored = await evaluate(`(() => {
      const form = document.querySelector('#profile-form');
      const out = {
        rows: document.querySelectorAll('#training-list .training-row').length,
        estimate: document.querySelector('#training-list').innerText.includes(${JSON.stringify(BARBELL_ESTIMATE)}),
        profileMessage: document.querySelector('#profile-message').textContent,
      };
      for (const name of ['heightCm', 'weightKg', 'bodyFatPct', 'thighCm', 'calfCm']) {
        out[name] = form.querySelector('[name="' + name + '"]').value;
      }
      return out;
    })()`);
    assert.equal(restored.rows, 2, `expected two restored records, found ${restored.rows}`);
    assert(restored.estimate, 'the restored barbell record lost its 1RM estimate');
    for (const [name, value] of Object.entries(PROFILE_INPUTS)) {
      assert.equal(restored[name], value,
        `the restored profile form shows ${name}=${restored[name]} instead of ${value}`);
    }
    assert(restored.profileMessage.includes('已从备份恢复'),
      'the profile message does not report the restore');
    const stored = JSON.parse(await evaluate(`localStorage.getItem('muscle-atlas-training-v1')`));
    assert.equal(stored.length, 2, 'the restored records were not written to local storage');
    assert.equal(stored[0].equipment, 'barbell', 'the restored first record changed equipment');
    assert.equal(stored[1].equipment, 'dumbbell', 'the restored second record changed equipment');
    assert.equal(stored[1].loadKg, 30, 'the restored dumbbell load changed');
  });

  await check('an oversized backup is refused without touching the restored data', async () => {
    // The page refuses files over 1 MB before parsing them. That guard was never exercised: the only
    // file this check had ever handed the input was one the app itself had just written.
    const oversized = join(downloads, 'oversized.json');
    writeFileSync(oversized, JSON.stringify({ padding: 'x'.repeat(1_100_000) }));
    const document_ = await send('DOM.getDocument', { depth: -1 });
    const input = await send('DOM.querySelector',
      { nodeId: document_.result.root.nodeId, selector: '#backup-file' });
    await send('DOM.setFileInputFiles', { nodeId: input.result.nodeId, files: [oversized] });
    await waitFor(`document.querySelector('#backup-message').textContent.includes('文件超过 1 MB')`,
      'the refusal of an oversized backup file');
    const after = await evaluate(`(() => ({
      rows: document.querySelectorAll('#training-list .training-row').length,
      stored: JSON.parse(localStorage.getItem('muscle-atlas-training-v1') ?? '[]').length,
      height: document.querySelector('#profile-form [name="heightCm"]').value,
    }))()`);
    assert.equal(after.rows, 2, `the refused file still changed the visible records: ${after.rows}`);
    assert.equal(after.stored, 2, `the refused file still changed stored records: ${after.stored}`);
    assert.equal(after.height, PROFILE_INPUTS.heightCm, 'the refused file still changed the profile');
  });

  await check('the narrow phone layout does not scroll sideways', async () => {
    await send('Emulation.setDeviceMetricsOverride',
      { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
    await sleep(1200);
    const layout = await evaluate(`(() => {
      const canvas = document.querySelector('canvas');
      return {
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
        canvasWidth: canvas ? canvas.getBoundingClientRect().width : 0,
      };
    })()`);
    assert.equal(layout.clientWidth, 390, `the viewport is ${layout.clientWidth} px wide`);
    assert(layout.scrollWidth <= 391,
      `the page scrolls sideways at 390 px: ${layout.scrollWidth} px wide`);
    assert(layout.canvasWidth > 0 && layout.canvasWidth <= 391,
      `the canvas is ${layout.canvasWidth} px wide at a 390 px viewport`);
  });

  await check('nothing is cut off by the panels that clip their content', async () => {
    // The panels use overflow: hidden, so an element wider than the viewport can be clipped without
    // ever making the document scroll — the previous, document-level assertion could not see it.
    // Content inside a deliberately scrollable strip (the press study table) is still reachable.
    const overflow = await evaluate(`(() => {
      const vw = document.documentElement.clientWidth;
      const inScrollableStrip = (node) => {
        for (let current = node; current && current !== document.documentElement;
          current = current.parentElement) {
          const style = getComputedStyle(current);
          if (style.overflowX === 'auto' || style.overflowX === 'scroll') return true;
        }
        return false;
      };
      const offenders = [];
      for (const node of document.querySelectorAll('body *')) {
        // Inside <svg> the geometry is the drawing, not the layout.
        if (node.ownerSVGElement) continue;
        const rect = node.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) continue;
        const style = getComputedStyle(node);
        if (style.display === 'none' || style.visibility === 'hidden') continue;
        const over = Math.max(rect.right - vw, -rect.left);
        if (over <= 1 || inScrollableStrip(node)) continue;
        offenders.push({
          tag: node.tagName.toLowerCase(),
          id: node.id,
          cls: String(node.className).slice(0, 40),
          over: Math.round(over),
          width: Math.round(rect.width),
        });
      }
      offenders.sort((a, b) => b.over - a.over);
      return { vw, scrollWidth: document.documentElement.scrollWidth,
        count: offenders.length, worst: offenders.slice(0, 5) };
    })()`);
    assert.equal(overflow.count, 0,
      `${overflow.count} element(s) stick out past the ${overflow.vw} px viewport, where the panels ` +
      `clip them invisibly (document scrollWidth is ${overflow.scrollWidth}): ` +
      JSON.stringify(overflow.worst));
  });

  await check('the skeleton scaling follows stature and ignores girth', async () => {
    const readScale = async () => JSON.parse(await evaluate(
      `document.querySelector('#viewer').dataset.skeletonScale`));
    // A profile is applied on the form's submit event, not on the input event.
    const applyProfile = async values => {
      for (const [name, value] of Object.entries(values)) {
        await setInput(`#profile-form [name="${name}"]`, value);
      }
      await evaluate(`document.querySelector('#profile-form').requestSubmit()`);
      await sleep(500);
    };
    await applyProfile({ heightCm: '190' });
    const tall = await readScale();
    assert.equal(Number(tall.referenceHeightCm), 175);
    assert.ok(Math.abs(Number(tall.heightFactor) - 190 / 175) < 1e-9, `height factor ${tall.heightFactor}`);
    const bodies = Object.keys(tall.bones);
    assert.equal(bodies.length, 22, 'the exposed skeleton is not the 22-body OpenSim skeleton');
    for (const body of bodies) {
      const factors = tall.bones[body].map(Number);
      assert.deepEqual(factors, [Number(tall.heightFactor), Number(tall.heightFactor), Number(tall.heightFactor)],
        `${body} did not take the stature factor on all three axes`);
    }
    // A circumference must not touch a bone: the OpenSim probe measured girth as a mesh-level change that
    // leaves joint positions alone, which is why it is exposed as a separate transverse-only group.
    await applyProfile({ thighCm: '80', waistCm: '120' });
    const wide = await readScale();
    for (const body of bodies) {
      assert.deepEqual(wide.bones[body].map(Number), tall.bones[body].map(Number),
        `${body} moved when only a circumference changed`);
    }
    for (const [segment, factors] of Object.entries(wide.girth)) {
      assert.equal(Number(factors[1]), 1, `${segment}: a circumference changed a length`);
      assert.ok(Number(factors[0]) > 0 && Number(factors[2]) > 0, `${segment}: an empty cross-section`);
    }
    assert.ok(Number(wide.girth.thigh[0]) > 1, 'a wider thigh did not widen the cross-section');
    // The default view's skeleton is the exported OpenSim skeleton: the app reports what it fitted, and the
    // numbers here are the ones check:full-body-skeleton pins on the GLB itself (9 segments, 28 bone meshes,
    // because both forearms carry a ulna and a radius).
    let bones = null;
    for (let attempt = 0; attempt < 40 && bones === null; attempt++) {
      const raw = await evaluate(`document.querySelector('#viewer').dataset.fullBodyBones`);
      if (raw) bones = JSON.parse(raw);
      else await sleep(250);
    }
    assert.ok(bones, 'the exported OpenSim skeleton never reached the default view');
    assert.equal(bones.model, 'RajagopalLaiUhlrich2023');
    // The muscle data layer: the 80 muscles of the same OpenSim model, with the paths and wrapping surfaces
    // `scripts/export_full_body_muscle_paths.py` writes. The numbers are the export's; re-running that script on
    // a changed model is what moves them.
    let musclePaths = null;
    for (let attempt = 0; attempt < 40 && musclePaths === null; attempt++) {
      const raw = await evaluate(`document.querySelector('#viewer').dataset.musclePaths`);
      if (raw) musclePaths = JSON.parse(raw);
      else await sleep(250);
    }
    assert.ok(musclePaths, 'the exported OpenSim muscle paths never reached the viewer');
    assert.equal(musclePaths.muscles, 80, `the viewer reports ${musclePaths.muscles} muscles, not 80`);
    assert.equal(musclePaths.points, 348, `the viewer reports ${musclePaths.points} muscle path points, not 348`);
    assert.equal(musclePaths.wrapping, 42, `the viewer reports ${musclePaths.wrapping} muscles with wrapping, not 42`);
    assert.ok(musclePaths.wrapObjects >= 44,
      `the viewer reports ${musclePaths.wrapObjects} wrap objects, fewer than the 44 the model holds`);
    // And the geometry itself: one tube per exported muscle, swept from the same paths.
    const muscleGeometry = JSON.parse(await evaluate(`document.querySelector('#viewer').dataset.muscleGeometry ?? 'null'`));
    assert.ok(muscleGeometry, 'the real muscle tubes never reached the scene');
    assert.equal(muscleGeometry.tubes, 80, `the scene drew ${muscleGeometry.tubes} muscle tubes, not 80`);
    assert.equal(muscleGeometry.pathPoints, musclePaths.points,
      'the tube layer and the reported path count disagree');
    // View presets: the standing views a reviewer compares. Driven from the keyboard here, and each one is held
    // to its exact camera, so a preset cannot silently drift to a different angle.
    const presets = [['1', 'front', '0.000,0.000'], ['2', 'back', '3.142,0.000'],
      ['3', 'left', '1.571,0.000'], ['4', 'right', '-1.571,0.000'], ['5', 'threeQuarter', '0.160,0.220']];
    for (const [key, name, expected] of presets) {
      await evaluate(`(() => { const make = () => new KeyboardEvent('keydown', { key: '${key}',
        code: 'Digit${key}', bubbles: true }); window.dispatchEvent(make());
        document.querySelector('#viewer')?.dispatchEvent(make()); })()`);
      await sleep(150);
      assert.equal(await evaluate(`document.querySelector('#viewer').dataset.viewPreset`), name,
        `the ${key} key did not select the ${name} view preset`);
      assert.equal(await evaluate(`document.querySelector('#viewer').dataset.orientation`), expected,
        `the ${name} preset does not sit at ${expected}`);
    }
    // The same presets as buttons, floating on the canvas: each one must exist, be big enough to hit, report its
    // state, move the camera exactly like its key does, and not push the model canvas under its height floor
    // (that floor is `check:desktop-layout`'s; here we only prove the buttons are on the canvas, not the toolbar).
    const presetButtons = await evaluate(`Array.from(document.querySelectorAll('[data-preset]')).map(button => ({
      preset: button.dataset.preset, pressed: button.getAttribute('aria-pressed'),
      inViewer: Boolean(button.closest('#viewer')),
      width: Math.round(button.getBoundingClientRect().width),
      height: Math.round(button.getBoundingClientRect().height) }))`);
    assert.equal(presetButtons.length, 5, `the page offers ${presetButtons.length} view presets, not 5`);
    for (const button of presetButtons) {
      assert.ok(button.inViewer, `the ${button.preset} preset button is not on the model canvas`);
      assert.ok(button.width >= 24 && button.height >= 24,
        `the ${button.preset} preset button is ${button.width}x${button.height}, under 24px`);
      assert.ok(button.pressed === 'true' || button.pressed === 'false',
        `the ${button.preset} preset button has no aria-pressed state`);
    }
    for (const target of ['back', 'threeQuarter']) {
      await evaluate(`document.querySelector('[data-preset="${target}"]').click()`);
      await sleep(150);
      assert.equal(await evaluate(`document.querySelector('#viewer').dataset.viewPreset`), target,
        `the ${target} preset button did not move the camera`);
      assert.equal(await evaluate(`document.querySelector('[data-preset="${target}"]').getAttribute('aria-pressed')`),
        'true', `the ${target} preset button never reported itself pressed`);
    }
    // The real muscle tubes are a layer of their own: the toolbar switch must hide them and the canvas must say
    // how many are visible, so "the switch works" is measured rather than assumed. The layer is shown in the
    // standing view only, so the check compares against whatever the current view shows rather than a fixed 80.
    assert.equal(await evaluate(`Boolean(document.querySelector('#muscle-tubes-toggle'))`), true,
      'the real muscle layer has no switch');
    assert.equal(await evaluate(`Boolean(document.querySelector('#viewer #muscle-tubes-toggle'))`), true,
      'the real muscle layer switch is in the toolbar: there it wraps the layer row and costs the canvas its floor');
    const readTubes = async () => JSON.parse(await evaluate(
      `document.querySelector('#viewer').dataset.muscleTubes`));
    const before = await readTubes();
    assert.equal(before.tubes, 80, `the canvas holds ${before.tubes} muscle tubes, not 80`);
    assert.ok(before.visible === 80 || before.visible === 0,
      `the canvas reports ${before.visible} visible muscle tubes, which is neither none nor all`);
    await evaluate(`(() => { const box = document.querySelector('#muscle-tubes-toggle'); box.checked = false;
      box.dispatchEvent(new Event('change', { bubbles: true })); })()`);
    await sleep(200);
    assert.equal((await readTubes()).visible, 0, 'turning the real muscle layer off left tubes on the canvas');
    await evaluate(`(() => { const box = document.querySelector('#muscle-tubes-toggle'); box.checked = true;
      box.dispatchEvent(new Event('change', { bubbles: true })); })()`);
    await sleep(200);
    assert.equal((await readTubes()).visible, before.visible,
      'turning the real muscle layer back on did not restore what the view showed');
    // Hover labels: the label names what is under the pointer, sits fully inside the viewport, takes no pointer
    // events (so it cannot block a control or the model centre), and is legible against its own background. One
    // label exists at a time, which is what makes "labels never overlap each other" true by construction.
    const rect = await evaluate(`(() => { const r = document.querySelector('#viewer').getBoundingClientRect();
      return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; })()`);
    const probes = [[0.5, 0.5], [0.5, 0.4], [0.45, 0.55], [0.55, 0.45], [0.5, 0.6], [0.4, 0.5]];
    let hover = null;
    for (const [fx, fy] of probes) {
      const x = rect.x + Math.round(rect.w * fx);
      const y = rect.y + Math.round(rect.h * fy);
      await evaluate(`document.querySelector('#viewer').dispatchEvent(new PointerEvent('pointermove', { clientX: ${x}, clientY: ${y}, bubbles: true }))`);
      await sleep(120);
      const state = JSON.parse(await evaluate(`document.querySelector('#viewer').dataset.hoverLabel ?? 'null'`));
      if (state && state.visible) { hover = state; break; }
    }
    assert.ok(hover, 'hovering the model never produced a label on any of the sampled points');
    assert.ok(hover.text.length > 0, 'the hover label came up with no name');
    assert.ok(hover.insideViewport, `the hover label "${hover.text}" is not fully inside the viewport`);
    assert.equal(hover.pointerEvents, 'none',
      'the hover label takes pointer events, so it can block a control or the model centre');
    const contrast = await evaluate(`(() => { const label = document.querySelector('.viewer-hover-label');
      const parse = (value) => value.match(/[\\d.]+/g).map(Number);
      const lum = (rgb) => { const parts = rgb.slice(0, 3).map((v) => { const c = v / 255;
        return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
        return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]; };
      const style = getComputedStyle(label);
      const a = lum(parse(style.color)); const b = lum(parse(style.backgroundColor));
      return Math.round(((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)) * 100) / 100; })()`);
    assert.ok(contrast >= 4.5, `the hover label contrast is ${contrast}:1, under the 4.5:1 floor`);
    await evaluate(`document.querySelector('#viewer').dispatchEvent(new PointerEvent('pointerleave', { bubbles: true }))`);
    await sleep(150);
    assert.equal(JSON.parse(await evaluate(`document.querySelector('#viewer').dataset.hoverLabel`)).visible, false,
      'the hover label stayed after the pointer left the canvas');
    // Joint angles: values with units a reviewer can quote, held to the same constraints as the hover label.
    const readouts = JSON.parse(await evaluate(
      "document.querySelector('#viewer').dataset.jointReadouts ?? 'null'"));
    assert.ok(readouts, 'the viewer reports no joint readouts at all');
    assert.equal(readouts.items, 3, "the readout panel shows " + readouts.items + " items, not 3");
    for (const key of ['hipDeg', 'kneeDeg', 'ankleDeg']) {
      const value = readouts[key];
      assert.ok(typeof value === 'number' && Number.isFinite(value) && value > 10 && value < 200,
        "the readout " + key + " is " + value + ", outside the plausible 10-200 degree range");
    }
    assert.equal(readouts.pointerEvents, 'none', 'the readout panel takes pointer events');
    assert.ok(readouts.insideCanvas, 'the readout panel is not fully inside the canvas it belongs to');
    assert.equal(readouts.coversCentre, false, 'the readout panel covers the model centre');

  // 解剖完整度基线（增补之九十六～一百零三）：真实骨网格与骨段不许减少，退回教学圆柱的体段不许增加。
  // 三个界限只写一遍：断言与失败信息共用同一常量，避免"报错里的界限和实际用的不一致"。
  {
    const readBones = function readBones() {
      const node = document.querySelector('[data-full-body-bones]') || document.body;
      return (node && node.dataset && node.dataset.fullBodyBones) || '{}';
    };
    const bones = JSON.parse(await evaluate('(' + readBones.toString() + ')()'));
    const segments = Array.isArray(bones.segments) ? bones.segments : [];
    const fallbacks = Array.isArray(bones.fallbackSegments) ? bones.fallbackSegments : [];
    const meshes = Number(bones.meshes || 0);
    const FLOOR_MESHES = 28;
    const FLOOR_SEGMENTS = 16;
    const CEIL_FALLBACKS = 5;
    console.log('解剖完整度实测：模型 ' + (bones.model || '?') + '，真实骨网格 ' + meshes + ' 个，覆盖体段 '
      + segments.length + ' 段（三角面 ' + (bones.triangles || 0) + '），教学圆柱体段 ' + (bones.teachingSegments || 0)
      + ' 段，仍退回圆柱 ' + fallbacks.length + ' 段');
    console.log('解剖完整度·真实体段：' + segments.join(', '));
    console.log('解剖完整度·退回圆柱：' + fallbacks.join(', '));
    assert.ok(meshes >= FLOOR_MESHES, '默认视图的真实骨网格变少了：' + meshes + ' 个（下限 ' + FLOOR_MESHES + '）');
    assert.ok(segments.length >= FLOOR_SEGMENTS, '默认视图的真实骨段变少了：' + segments.length
      + ' 段（下限 ' + FLOOR_SEGMENTS + '）：' + segments.join(', '));
    assert.ok(fallbacks.length <= CEIL_FALLBACKS, '退回教学圆柱的体段变多了：' + fallbacks.length
      + ' 段（上限 ' + CEIL_FALLBACKS + '）：' + fallbacks.join(', '));
  }

  // 最小可点区域（增补之九十五，修正口径）：WCAG 2.2 AA 目标尺寸 24×24 CSS px，但按标准的两条例外：
  //   ① 表单控件的有效目标包含其关联 <label>（标签本身就是合法目标）；
  //   ② 行内文本中的链接适用 inline 例外，不计入。
  {
    const walkTargets = function walkTargets() {
  const describe = (element) => {
    if (element.id) return '#' + element.id;
    const classes = String(element.className || '').trim().split(/\s+/).filter(Boolean).slice(0, 2);
    return classes.length > 0 ? element.tagName.toLowerCase() + '.' + classes.join('.') : element.tagName.toLowerCase();
  };
  const unionOf = (a, b) => ({
    width: Math.max(a.right, b.right) - Math.min(a.left, b.left),
    height: Math.max(a.bottom, b.bottom) - Math.min(a.top, b.top),
  });
  const effectiveBox = (element) => {
    const own = element.getBoundingClientRect();
    const label = element.closest('label')
      || (element.id ? document.querySelector('label[for="' + element.id + '"]') : null);
    if (!label) return own;
    const box = unionOf(own, label.getBoundingClientRect());
    return { width: box.width, height: box.height };
  };
  const selector = 'button, a[href], input:not([type="hidden"]), select, textarea, summary, [role="button"], [tabindex]:not([tabindex="-1"])';
  const measured = [];
  let labelExpanded = 0;
  let inlineExempt = 0;
  for (const element of document.querySelectorAll(selector)) {
    const style = getComputedStyle(element);
    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) continue;
    // WCAG inline exception: links that are part of a sentence are not subject to the target-size rule.
    if (element.tagName === 'A' && style.display === 'inline') { inlineExempt += 1; continue; }
    const own = element.getBoundingClientRect();
    if (own.width < 1 || own.height < 1) continue;
    const label = element.closest('label')
      || (element.id ? document.querySelector('label[for="' + element.id + '"]') : null);
    if (label) labelExpanded += 1;
    const box = effectiveBox(element);
    measured.push({
      selector: describe(element),
      tag: element.tagName.toLowerCase(),
      width: Math.round(box.width * 10) / 10,
      height: Math.round(box.height * 10) / 10,
      labelled: Boolean(label),
    });
  }
  const undersized = measured.filter(entry => entry.width < 24 || entry.height < 24);
  const compliant = measured.filter(entry => entry.width >= 24 && entry.height >= 24);
  compliant.sort((a, b) => (a.width * a.height) - (b.width * b.height));
  return JSON.stringify({
    total: measured.length,
    undersized,
    compliant: compliant.slice(0, 6),
    labelExpanded,
    inlineExempt,
    smallest: measured.slice().sort((a, b) => (a.width * a.height) - (b.width * b.height)).slice(0, 5),
  });
};
    const targets = JSON.parse(await evaluate('(' + walkTargets.toString() + ')()'));
    const detail = targets.undersized.map(entry => entry.selector + '=' + entry.width + 'x' + entry.height);
    console.log('最小可点区域实测：计入元素 ' + targets.total + ' 个（含 label 扩展 ' + targets.labelExpanded
      + ' 个，行内链接豁免 ' + targets.inlineExempt + ' 个），小于 24×24 的 ' + targets.undersized.length + ' 个');
    console.log('最小可点区域最小的五个：' + targets.smallest.map(entry => entry.selector + '=' + entry.width + 'x' + entry.height).join(' '));
    console.log('最小可点区域合规候选：' + targets.compliant.map(entry => entry.selector + '=' + entry.width + 'x' + entry.height).join(' '));
    if (detail.length > 0) console.log('最小可点区域不达标明细：' + detail.join(' | '));
    assert.ok(targets.undersized.length <= 0, "可点区域小于 24×24 的控件变多了" + '：' + targets.undersized.length + ' 个（上限 0）：' + detail.slice(0, 6).join('; '));
  }
    // 层级开关守卫：先建立可用前置状态（深蹲 + OpenSim），把"控件不可用"变成显式失败，再双向断言场景对象。
    await evaluate("document.querySelector('[data-exercise=\"squat\"]')?.click()");
    await evaluate("document.querySelector('[data-view=\"opensim\"]')?.click()");
    let toggleEnabled = false;
    for (let attempt = 0; attempt < 40; attempt += 1) {
      toggleEnabled = (await evaluate("document.querySelector('#registered-bones-toggle')?.disabled")) === false;
      if (toggleEnabled) break;
      await sleep(250);
    }
    assert.ok(toggleEnabled, '研究图层开关在当前状态下不可用，无法验证图层行为');
    const toggleLayer = async (checked) => {
      await evaluate("(() => { const box = document.querySelector('#registered-bones-toggle');"
        + " box.checked = " + checked + "; box.dispatchEvent(new Event('change', { bubbles: true })); })()");
    };
    const waitForLayer = async (expected) => {
      let state = null;
      for (let attempt = 0; attempt < 20; attempt += 1) {
        state = JSON.parse(await evaluate("document.querySelector('#viewer').dataset.layerVisibility ?? '{}'"));
        if (state.groupVisible === expected) break;
        await sleep(250);
      }
      return state;
    };
    await toggleLayer(true);
    await waitForLayer(true);
    await toggleLayer(false);
    const layerOff = await waitForLayer(false);
    assert.equal(layerOff.groupVisible, false, "研究图层在场景里仍然可见：关掉开关后 visible 仍为 true");
    await toggleLayer(true);
    const layerBackOn = await waitForLayer(true);
    assert.equal(layerBackOn.groupVisible, true, "研究图层没有出现在场景里：打开开关后 visible 仍为 false");
    // 增补之七十六：读数是真实几何量，而且**跟随姿态**（探针已验证：播放按钮让相位从 40% 走到 82%，
    // 三个角度随之从 120.2/137.3/80.7 变为 99.5/126.9/82.6）。所以这里断言两件真事：三个角度不全相等，
    // 且姿态推进后读数必须变化。相位标签是"姿态确实变了"的独立证据——它不动就说明驱动无效，此时不下结论。
    assert(readouts.hipDeg !== readouts.kneeDeg || readouts.kneeDeg !== readouts.ankleDeg,
      'the three joint readouts are all equal — a constant would satisfy a range check');
    const phaseBefore = await evaluate("document.querySelector('#phase-label')?.textContent ?? null");
    await evaluate("document.querySelector('#play-button')?.click()");
    await sleep(3000);
    const phaseAfter = await evaluate("document.querySelector('#phase-label')?.textContent ?? null");
    assert(phaseBefore !== phaseAfter, 'the play control did not advance the pose (' + phaseBefore + ' -> '
      + phaseAfter + '), so readout behaviour cannot be judged');
    const moved = JSON.parse(await evaluate("document.querySelector('#viewer').dataset.jointReadouts ?? '{}'"));
    const changed = ['hipDeg', 'kneeDeg', 'ankleDeg'].filter(key => moved[key] !== readouts[key]).length;
    assert(changed >= 1, 'the joint readouts did not change while the pose advanced (' + changed + ' changed)');
    // ③ 的包裹面：44 个圆柱必须真的画出来、必须是线框（实体圆柱会被误读成肌肉），并记录它们到最近肌肉路径点
    // 的距离——变换链写错时这个数字会变大，而不是悄悄画错位置。
    const wrapState = JSON.parse(await evaluate("document.querySelector('#viewer').dataset.wrapSurfaces ?? 'null'"));
    assert.ok(wrapState, 'the viewer reports no wrapping surfaces at all');
    assert.equal(wrapState.rendered, 44, `only ${wrapState.rendered} of 44 wrapping cylinders were drawn`);
    assert.equal(wrapState.wireframe, true, 'the wrapping cylinders are not wireframe, so they read as anatomy');


    assert.equal(Number(bones.meshes), 28, `the default view fitted ${bones.meshes} bone meshes, not 28`);
    assert.deepEqual([...bones.segments].sort(), ['ankleL->footL', 'ankleR->footR', 'elbowL->wristL', 'elbowR->wristR', 'hipL->kneeL', 'hipR->kneeR', 'kneeL->ankleL', 'kneeL->patellaL', 'kneeR->ankleR', 'kneeR->patellaR', 'neck->head', 'pelvis->chest', 'shoulderL->elbowL', 'shoulderR->elbowR', 'wristL->handL', 'wristR->handR'],
    `the fitted segments are ${bones.segments.join(', ')}`);
    assert.ok(Number(bones.triangles) > 20000, `only ${bones.triangles} bone triangles reached the view`);
    assert.equal(Number(bones.segments.length) + Number(bones.fallbackSegments.length),
      Number(bones.teachingSegments), 'a teaching segment is neither fitted nor accounted for as a fallback');
    assert.ok(Number(bones.teachingSegments) >= 14,
      `the teaching skeleton only reports ${bones.teachingSegments} segments`);
    assert.ok([0, 28].includes(Number(tall.boneMeshesVisible)),
      `boneMeshesVisible is ${tall.boneMeshesVisible}, which is neither none nor all of the bone meshes`);
  });

  await check('the page raised no uncaught error', () => {
    assert.deepEqual(pageErrors, [], `the page reported errors: ${pageErrors.join(' | ')}`);
  });

  await check('the privacy page describes this round trip', () => {
    const doc = readFileSync('docs/隐私与本地数据.md', 'utf8');
    for (const phrase of ['check:ui-data-flows', 'exportedAt', '还没有做过']) {
      assert(doc.includes(phrase), `the privacy page no longer states “${phrase}”`);
    }
    assert(doc.includes('系统分享'), 'the privacy page no longer marks the Android path as unverified');
  });

  console.log(`${verified.length} user-data flows verified in ${browser.split(/[\\/]/).pop()} ` +
    `against the production build:\n  - ${verified.join('\n  - ')}`);
} finally {
  try { socket?.close(); } catch {}
  child.kill();
  await new Promise(resolve => { server.close(resolve); setTimeout(resolve, 1500); });
  if (process.platform === 'win32') {
    spawn('taskkill', ['/F', '/T', '/PID', String(child.pid)], { stdio: 'ignore' });
    await sleep(500);
  }
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
  try { rmSync(downloads, { recursive: true, force: true }); } catch {}
}
