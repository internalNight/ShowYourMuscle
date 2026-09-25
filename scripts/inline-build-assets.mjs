import assert from 'node:assert/strict';
import { readFile, writeFile, unlink } from 'node:fs/promises';
import { resolve, sep } from 'node:path';

const dist = resolve('dist');
const index = resolve(dist, 'index.html');
let html = await readFile(index, 'utf8');
const scriptTag = html.match(/<script type="module" crossorigin src="(\/assets\/[^\"]+\.js)"><\/script>/);
const styleTag = html.match(/<link rel="stylesheet" crossorigin href="(\/assets\/[^\"]+\.css)">/);
assert(scriptTag && styleTag, 'Expected one Vite script and one stylesheet');

function assetPath(url) {
  const path = resolve(dist, `.${url}`);
  assert(path.startsWith(`${dist}${sep}`), 'Build asset escaped dist');
  return path;
}

const scriptPath = assetPath(scriptTag[1]);
const stylePath = assetPath(styleTag[1]);
const script = (await readFile(scriptPath, 'utf8')).replace(/<\/script/gi, '<\\/script');
const style = (await readFile(stylePath, 'utf8')).replace(/<\/style/gi, '<\\/style');
// A callback keeps minified JavaScript's literal `$&` and similar sequences
// from being interpreted as String.replace substitution patterns.
html = html.replace(scriptTag[0], () => `<script type="module" data-bundle="inline">${script}</script>`)
  .replace(styleTag[0], () => `<style data-bundle="inline">${style}</style>`);
await writeFile(index, html);
await unlink(scriptPath);
await unlink(stylePath);
console.log(`Inlined script and stylesheet into ${index}`);
