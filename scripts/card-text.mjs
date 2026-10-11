// Scopes card-copy assertions to the description they belong to.
//
// The card checks used to search all of src/main.ts for their phrases, so a sentence could move to another
// card — or into a comment — and the assertion would still pass while the card it names quietly lost it.
// Each view's description is a template literal that starts at that view's own <strong> heading and ends
// at the next heading, so the phrases are checked inside that region instead of inside the whole file.

// The heading that opens the squat research layer's description, shared by the checks that quote its
// numbers so they cannot disagree about which card they mean.
export const RESEARCH_HEADING = '<strong>OpenSim 深蹲参考路径</strong>';

export function headingRegion(source, heading) {
  const start = source.indexOf(heading);
  if (start < 0) return null;
  const next = source.indexOf('<strong>', start + heading.length);
  const end = next < 0 ? source.length : next;
  return { start, end, text: source.slice(start, end) };
}

export function assertHeadlineCopy(source, heading, phrases, label) {
  const region = headingRegion(source, heading);
  if (!region) {
    throw new Error(`${label}: the description headed “${heading}” is gone from src/main.ts`);
  }
  const missing = phrases.filter(phrase => !region.text.includes(phrase));
  if (missing.length) {
    const elsewhere = missing.filter(phrase => source.includes(phrase));
    throw new Error(`${label}: the description headed “${heading}” no longer reports ` +
      missing.map(phrase => `“${phrase}”`).join('、') +
      (elsewhere.length
        ? `（其中 ${elsewhere.length} 条仍出现在 src/main.ts 的别处，所以整文件搜索会照常通过）`
        : ''));
  }
  return region;
}
