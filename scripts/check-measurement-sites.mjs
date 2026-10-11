import assert from 'node:assert/strict';
import { build } from 'esbuild';

async function load(entry) {
  const bundled = await build({ entryPoints: [entry], bundle: true, platform: 'node', format: 'esm', write: false });
  const source = bundled.outputFiles[0].text;
  return import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
}

const { measurementDiagramSvg, measurementLegendHtml, measurementDiagramHtml } = await load('src/measurement-diagram.ts');
const { bodyFields, measurementSites } = await load('src/domain.ts');

// Every input field must have exactly one stated measurement site, and vice versa.
const fieldKeys = bodyFields.map(field => field.key).sort();
const siteKeys = measurementSites.map(site => site.key).sort();
assert.deepEqual(siteKeys, fieldKeys, 'measurement sites must cover every body field exactly once');
assert.equal(new Set(siteKeys).size, siteKeys.length, 'measurement sites must not repeat a field');

const svg = measurementDiagramSvg();
const legend = measurementLegendHtml();

// The figure and the legend are both generated from that list, so nothing may go missing.
// Tape and length sites need a drawn mark; weight and body fat are whole-body values with a legend row only.
const siteGroup = key => {
  const match = svg.match(new RegExp(`<g class="measure-site" data-site="${key}"[^>]*>([\\s\\S]*?)</g>`));
  assert.ok(match, `figure has no group for ${key}`);
  return match[1];
};
for (const site of measurementSites) {
  assert.equal(svg.split(`data-site="${site.key}"`).length - 1, 1, `${site.key} must appear once in the figure`);
  assert.ok(legend.includes(`data-site="${site.key}"`), `legend is missing ${site.key}`);
  const marks = siteGroup(site.key);
  if (site.anchor === 'mass' || site.anchor === 'fat') {
    assert.ok(marks.trim() === '', `${site.key} is a whole-body value and must not claim a tape site`);
  } else {
    assert.ok(marks.includes('<line'), `${site.key} needs a drawn measurement mark`);
  }
}

// The labels in the figure use the same wording as the form, so both name the same landmark.
for (const site of measurementSites) {
  const field = bodyFields.find(item => item.key === site.key);
  assert.ok(field, `${site.key} must be a form field`);
  if (site.anchor === 'mass' || site.anchor === 'fat') continue;
  const short = field.label.replace(/\s*cm$|\s*kg$|\s*%$/, '');
  assert.ok(svg.includes(`>${short}</text>`), `figure label ${short} missing for ${site.key}`);
  assert.ok(legend.includes(`<strong>${field.label}</strong>`), `legend label ${field.label} missing for ${site.key}`);
}

// The card must stay offline-safe and must not claim to have measured the user.
const card = measurementDiagramHtml();
assert.ok(card.includes('<svg'), 'card must embed the figure');
assert.ok(!/<img|https?:\/\/|\ssrc=/.test(card), 'the measurement card must not load external assets');
assert.ok(card.includes('自报'), 'the card must state that the values are self-reported');

console.log(`${measurementSites.length} body inputs have one stated measurement site each; `
  + 'figure, legend and form labels agree, and the card embeds no external asset.');
