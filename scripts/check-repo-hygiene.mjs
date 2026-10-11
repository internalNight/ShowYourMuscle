import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

// The check registry is the set of `check:*` scripts in package.json, and it is the only thing that
// decides whether a check ever runs. A check file that no script points at is invisible evidence: the
// repository looks covered and nothing is verified. The same goes for a document that names a check
// that no longer exists, or that pins a check by its position in the registry — the position moves
// whenever a check is added (new checks go first), so an ordinal in prose goes stale silently.
const root = process.cwd();
const scripts = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')).scripts;
const registered = Object.entries(scripts)
  .filter(([name]) => name.startsWith('check:'))
  .map(([name, command]) => {
    const match = /^node (scripts\/[\w.-]+\.mjs)$/.exec(command.trim());
    assert(match, `${name} does not run a single scripts/*.mjs file: ${command}`);
    return { name, file: match[1] };
  });
assert(registered.length > 0, 'package.json registers no check:* scripts');

// 1. Every registered check runs an existing script, and the two names agree.
for (const { name, file } of registered) {
  assert(existsSync(join(root, file)), `${name} points at a missing file: ${file}`);
  const expected = `scripts/check-${name.slice('check:'.length)}.mjs`;
  assert.equal(file, expected, `${name} runs ${file} instead of ${expected}`);
}

// 2. Every scripts/check-*.mjs is run by exactly one registered check — no dead check files.
const onDisk = readdirSync(join(root, 'scripts')).filter(name => /^check-.*\.mjs$/.test(name)).sort();
const run = registered.map(entry => entry.file.slice('scripts/'.length)).sort();
assert.deepEqual(run, onDisk,
  `registered checks and scripts/check-*.mjs disagree — registered only: ` +
  `${run.filter(name => !onDisk.includes(name)).join(', ') || '—'}; on disk only: ` +
  `${onDisk.filter(name => !run.includes(name)).join(', ') || '—'}`);

// 3. Documents may only name registered checks.
const documents = readdirSync(join(root, 'docs')).filter(name => name.endsWith('.md'))
  .map(name => `docs/${name}`).concat(['README.md']);
const registeredNames = new Set(registered.map(entry => entry.name));
const mentioned = new Set();
for (const file of documents) {
  const text = readFileSync(join(root, file), 'utf8');
  for (const match of text.matchAll(/check:[a-z0-9-]+/g)) mentioned.add(match[0]);
}
const unknown = [...mentioned].filter(name => !registeredNames.has(name)).sort();
assert.deepEqual(unknown, [],
  `documents name checks that are not registered: ${unknown.join(', ')}`);

// 4. No document pins a check by its position in the registry.
for (const file of documents) {
  const stale = /第\s*\d+\s*项检查/.exec(readFileSync(join(root, file), 'utf8'));
  assert.equal(stale, null,
    `${file} pins a check by position (${stale?.[0]}); name it as check:<name> instead`);
}

// 5. No text file carries a UTF-8 BOM. PowerShell's `Set-Content -Encoding UTF8` writes one, and a BOM
// has already made package.json unparsable for the whole toolchain in this repository — Node then reports
// a syntax error at the first character of a file that looks fine in an editor. Line endings are NOT
// checked: this repository mixes LF and CRLF (which is pre-existing and harmless), so only the BOM is an
// error. Generated directories are skipped, and the counts are printed so drift stays visible.
const SKIP = new Set(['.cache', '.git', 'android', 'dist', 'node_modules', 'releases']);
const TEXT = /\.(css|html|json|md|mjs|py|ts)$/;
const walk = directory => readdirSync(join(root, directory), { withFileTypes: true }).flatMap(entry => {
  const relative = `${directory}/${entry.name}`;
  if (entry.isDirectory()) return SKIP.has(entry.name) ? [] : walk(relative);
  return TEXT.test(entry.name) ? [relative] : [];
});
const textFiles = walk('.');
const boms = textFiles.filter(file => {
  const bytes = readFileSync(join(root, file));
  return bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf;
});
assert.deepEqual(boms, [], `these text files start with a UTF-8 BOM: ${boms.join(', ')}`);
const crlf = textFiles.filter(file => readFileSync(join(root, file)).includes('\r\n'));

// 6. Every registered check appears in the negative-verification ledger with a status from the allowed
// vocabulary, and the ledger's own summary agrees with what it contains. A check that is trusted but
// never broken is a claim, not evidence, so the ledger has to say which is which for all of them.
const ledgerPath = 'docs/检查与负向验证.md';
const ledger = readFileSync(join(root, ledgerPath), 'utf8');
const rows = [...ledger.matchAll(/^\| `(check:[a-z0-9-]+)` \| (.+?) \| (.+?) \|$/gm)]
  .map(match => ({ name: match[1], guards: match[2], status: match[3] }));
assert(rows.length > 0, `${ledgerPath} has no check table rows`);
const ledgerNames = rows.map(row => row.name);
assert.deepEqual([...ledgerNames].sort(), [...registeredNames].sort(),
  `the ledger and the registry disagree — in registry only: ` +
  `${[...registeredNames].filter(name => !ledgerNames.includes(name)).join(', ') || '—'}; ` +
  `in ledger only: ${ledgerNames.filter(name => !registeredNames.has(name)).join(', ') || '—'}`);
for (const row of rows) {
  assert(/^(已做（.+）|待做)$/.test(row.status),
    `${row.name} has a status outside the ledger vocabulary: ${row.status}`);
  assert(row.guards.trim().length > 8, `${row.name} has no description of what it guards`);
}
const done = rows.filter(row => row.status.startsWith('已做')).length;
const stated = /已做破坏验证：(\d+) 项；待做：(\d+) 项/.exec(ledger);
assert(stated, `${ledgerPath} no longer states the counts`);
assert.equal(Number(stated[1]), done,
  `the ledger says ${stated[1]} checks were broken on purpose but ${done} rows say so`);
assert.equal(Number(stated[2]), rows.length - done,
  `the ledger says ${stated[2]} checks are pending but ${rows.length - done} rows say so`);

console.log(`CHECK_REGISTRY ${JSON.stringify({ checks: registered.length, files: onDisk.length,
  documents: documents.length, documentedChecks: mentioned.size, textFiles: textFiles.length,
  bomFiles: boms.length, crlfFiles: crlf.length, ledgerRows: rows.length, ledgerVerified: done,
  ledgerPending: rows.length - done })}`);
