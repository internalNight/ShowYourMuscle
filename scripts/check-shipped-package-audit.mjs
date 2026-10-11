// Guards the shipped-package audit and the data-handling claims built on it.
//
// docs/data/shipped_package_audit.json is produced by scripts/audit_shipped_package.py, which reads a
// built APK, the packaged page and the source call sites. This check keeps the raw facts honest
// (the audited build is the shipped one, the permission list is exactly the audited one, the network
// surface has not grown) and keeps docs/隐私与本地数据.md tied to those facts. Anything unreviewed —
// a new permission, a new fetch, a new external host, a new storage key — fails here until someone
// classifies it in the auditor.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';

const read = name => JSON.parse(readFileSync(`docs/data/${name}`, 'utf8'));
const audit = read('shipped_package_audit.json');
const doc = readFileSync('docs/隐私与本地数据.md', 'utf8');
const androidDoc = readFileSync('docs/安卓构建.md', 'utf8');
const main = readFileSync('src/main.ts', 'utf8');
const serviceWorker = readFileSync('public/sw.js', 'utf8');

assert.equal(audit.status, 'static_package_audit_not_runtime_verification');
assert.equal(audit.limitations.length >= 5, true, 'the audit lost its limitations');
assert(audit.limitations.some(text => text.includes('静态')),
  'the audit must still say it is static analysis, not a runtime guarantee');
assert(audit.limitations.some(text => text.includes('真机')),
  'the audit must still name the missing device acceptance');

// The audited artifact must be the shipped one, and the docs must describe the same bytes.
//
// The audit JSON carries `crossCheck.androidDoc*Match` flags, but a flag is only a claim about the last
// time the auditor ran: with a stale JSON this check used to pass while docs/安卓构建.md quoted a byte
// count or SHA-256 that no longer described the APK on disk. So the facts are recomputed here — the APK
// is re-hashed and the document is re-read — and the cached flags must agree with that recomputation.
const apk = audit.apk;
assert(apk.path.startsWith('releases/muscle-atlas-debug-v'), `unexpected audited path ${apk.path}`);
assert(existsSync(apk.path), `the audited APK ${apk.path} is no longer in releases/`);
assert(/^[0-9A-F]{64}$/.test(apk.sha256), 'the audited SHA-256 is not a digest');
const apkBytes = readFileSync(apk.path);
const apkSha = createHash('sha256').update(apkBytes).digest('hex').toUpperCase();
assert.equal(apkBytes.length, apk.bytes,
  `the audit records ${apk.bytes} bytes but ${apk.path} is ${apkBytes.length} bytes`);
assert.equal(apkSha, apk.sha256.toUpperCase(),
  `the audit records SHA-256 ${apk.sha256} but ${apk.path} hashes to ${apkSha}`);
const quotedBytes = [String(apk.bytes), apk.bytes.toLocaleString('en-US')];
assert(quotedBytes.some(form => androidDoc.includes(form)),
  `docs/安卓构建.md does not quote the audited byte count (${quotedBytes[1]})`);
assert(androidDoc.toUpperCase().includes(apkSha),
  `docs/安卓构建.md does not quote the audited SHA-256 (${apkSha})`);
assert.equal(audit.crossCheck.androidDocBytesMatch, true,
  'docs/安卓构建.md no longer quotes the audited byte count');
assert.equal(audit.crossCheck.androidDocShaMatch, true,
  'docs/安卓构建.md no longer quotes the audited SHA-256');
assert.equal(audit.crossCheck.serviceWorkerMarker, audit.archive.cacheMarker,
  'the service worker cache marker and the audited package disagree');
assert.equal(audit.crossCheck.currentDistMarker, audit.archive.cacheMarker,
  'the current build and the audited package disagree; rebuild before auditing');
assert.equal(main.includes(`'${audit.archive.cacheMarker}'`), true,
  'the audited cache marker is not the one src/main.ts expects');
assert.equal(serviceWorker.includes(`'${audit.archive.cacheMarker}'`), true,
  'the audited cache marker is not the one public/sw.js uses');
assert.equal(audit.archive.arm26Entries, 0, 'the package grew an arm26 entry');
assert.deepEqual(audit.archive.cardTokensMissing, [],
  'the packaged card is missing audited sentences');
assert(audit.archive.cardTokensPresent.includes('不穿模'),
  'the packaged card lost the research-layer wording');

// The permission list is a privacy claim, so it is asserted exactly.
const permissions = audit.manifest.permissions.map(item => item.name).sort();
assert.deepEqual(permissions,
  ['android.permission.INTERNET', 'com.muscleatlas.prototype.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION'],
  'the shipped permission list changed; review it and update the auditor before shipping');
for (const item of audit.manifest.permissions) {
  assert.notEqual(item.reason, 'unreviewed', `${item.name} has no written reason`);
  assert(item.reason.length > 10, `${item.name} needs a fuller reason`);
}
assert.equal(audit.manifest.debuggable, true, 'the audited artifact is no longer the debug build');
assert.equal(audit.manifest.nativeCode.length, 0, 'the package now ships native code');
assert.equal(audit.packagedManifest.allowBackup, 'false',
  'cloud backup is no longer disabled in the packaged manifest');
assert.equal(audit.packagedManifest.usesCleartextTraffic, null,
  'the packaged manifest now sets usesCleartextTraffic explicitly');
assert.equal(audit.sourceManifest.fileProviderExported, 'false',
  'the export FileProvider is no longer private');
assert.equal(audit.sourceManifest.allowBackup, 'false',
  'the hand-written manifest no longer disables cloud backup');
const unguarded = audit.packagedManifest.exportedComponents.filter(item => !item.permission);
assert.deepEqual(unguarded.map(item => item.name),
  [`${audit.manifest.packageName}.MainActivity`],
  'an exported component without a permission guard appeared in the merged manifest');
assert(doc.includes('android.permission.INTERNET') && doc.includes('allowBackup'),
  'the privacy page no longer names the audited permission and backup flag');
assert(doc.includes('调试签名包'), 'the privacy page no longer marks the audited artifact as a debug build');
assert(doc.includes('还没有做过'), 'the privacy page no longer admits the missing device acceptance');

// The source's network and bridge surface is re-scanned here, so the audit cannot go stale.
const sinkPattern = /\b(fetch\s*\(|new\s+XMLHttpRequest|new\s+WebSocket|sendBeacon|new\s+EventSource|CapacitorHttp|axios|navigator\.share\s*\(|Share\.share\s*\()/;
const sources = ['src/main.ts'];
const foundSinks = [];
for (const file of sources) {
  readFileSync(file, 'utf8').split('\n').forEach((line, index) => {
    if (sinkPattern.test(line)) {
      foundSinks.push({ file, line: index + 1, code: line.trim().slice(0, 160) });
    }
  });
}
for (const scanned of foundSinks) {
  const audited = audit.networkSinks.find(item => item.file === scanned.file && item.code === scanned.code);
  assert(audited, `the audit is stale: ${scanned.file}:${scanned.line} is not in it`);
  assert.notEqual(audited.classification, 'unreviewed',
    `${scanned.file}:${scanned.line} has an unreviewed network or bridge call`);
}
assert.equal(foundSinks.length, audit.networkSinks.length,
  'the audit lists network calls that no longer exist in src/');
assert.equal(audit.networkSinks.filter(item => item.classification === 'local asset').length, 1,
  'the app no longer has exactly one in-package data request');

const keyPattern = /localStorage\.(?:setItem|getItem|removeItem)\(\s*['"`]([^'"`]+)/;
const foundKeys = new Set();
for (const file of sources.concat(['src/domain.ts'])) {
  for (const line of readFileSync(file, 'utf8').split('\n')) {
    const match = keyPattern.exec(line);
    if (match) foundKeys.add(match[1]);
  }
}
assert.deepEqual([...foundKeys].sort(), Object.keys(audit.localStorageKeys).sort(),
  'the stored keys changed; update the auditor and the privacy page');
for (const [key, item] of Object.entries(audit.localStorageKeys)) {
  assert.notEqual(item.contains, 'unreviewed', `${key} has no description`);
  assert.notEqual(item.leavesDevice, 'unreviewed', `${key} has no export rule`);
}

// Every external host inside the packaged page must be a classified citation, not a service endpoint.
const hosts = [...new Set((readFileSync('dist/index.html', 'utf8').match(/https?:\/\/([A-Za-z0-9._-]+)/g) ?? [])
  .map(url => url.replace(/^https?:\/\//, '')))].sort();
assert.deepEqual(hosts, Object.keys(audit.externalHostsInPackagedPage).sort(),
  'the packaged page gained or lost an external host; classify it in the auditor');
for (const [host, item] of Object.entries(audit.externalHostsInPackagedPage)) {
  assert.notEqual(item.classification, 'unreviewed', `${host} is not classified`);
  assert(!/service|api|telemetry|analytics/i.test(item.classification),
    `${host} is classified as a service endpoint`);
}

// The card tells the user the same thing the audit measured.
for (const phrase of ['没有账号、统计或广告', '只有一处网络请求', '系统云备份已关闭',
  '要你自己点开才会访问', '只在你按“导出备份”时写出']) {
  assert(main.includes(phrase), `the card no longer states “${phrase}”`);
}
assert(androidDoc.includes('shipped_package_audit.json') || androidDoc.includes('隐私与本地数据'),
  'the Android build page no longer points at the package audit');

console.log(`Shipped package audited: ${apk.path} (${apk.bytes} bytes, ${audit.archive.cacheMarker}), ` +
  `permissions ${permissions.length} (${audit.manifest.permissions.map(item => item.name.split('.').pop()).join(', ')}), ` +
  `${audit.networkSinks.length} network/bridge calls of which 1 reads packaged data, ` +
  `${Object.keys(audit.externalHostsInPackagedPage).length} external hosts all citations, ` +
  `${Object.keys(audit.localStorageKeys).length} local storage keys, cloud backup ` +
  `${audit.packagedManifest.allowBackup}, cleartext traffic ` +
  `${audit.packagedManifest.usesCleartextTraffic === null ? 'not enabled' : 'explicit'} — and it remains a ` +
  `static audit with no device acceptance.`);
