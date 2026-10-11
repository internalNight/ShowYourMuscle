// A front-view figure showing where each body input is meant to be measured.
// It is drawn from the same list the form uses, so the stated landmarks cannot drift apart.
// The figure is a teaching diagram: it is not a measurement, a photo or a body scan.
import { bodyFields, measurementSites, type MeasurementAnchor } from './domain';

const anchorGeometry: Record<MeasurementAnchor, string> = {
  // Vertical double arrow at the left of the figure.
  stature: '<line x1="26" y1="19" x2="26" y2="304" /><line x1="21" y1="19" x2="31" y2="19" /><line x1="21" y1="304" x2="31" y2="304" />',
  // Horizontal double arrow at fingertip height.
  span: '<line x1="63" y1="141" x2="177" y2="141" /><line x1="63" y1="136" x2="63" y2="146" /><line x1="177" y1="136" x2="177" y2="146" />',
  chest: '<line x1="92" y1="84" x2="148" y2="84" />',
  waist: '<line x1="100" y1="124" x2="140" y2="124" />',
  arm: '<line x1="171" y1="104" x2="184" y2="109" />',
  thigh: '<line x1="104" y1="186" x2="136" y2="186" />',
  calf: '<line x1="101" y1="262" x2="139" y2="262" />',
  // Vertical double arrow from crotch to floor.
  inseam: '<line x1="120" y1="152" x2="120" y2="304" /><line x1="115" y1="152" x2="125" y2="152" /><line x1="115" y1="304" x2="125" y2="304" />',
  // Not drawn on the figure; these are whole-body values, not tape sites.
  mass: '',
  fat: '',
};

const bodyOutline = [
  '<circle cx="120" cy="34" r="15" />',
  '<path d="M112 50 L128 50 L130 60 L110 60 Z" />',
  '<path d="M110 60 L98 66 L94 96 L100 126 L102 152 L138 152 L140 126 L146 96 L142 66 L130 60" />',
  '<path d="M98 66 L82 96 L70 132 L63 141" />',
  '<path d="M142 66 L158 96 L170 132 L177 141" />',
  '<path d="M106 152 L102 216 L100 250 L99 292 L111 292 L113 250 L116 216" />',
  '<path d="M134 152 L138 216 L140 250 L141 292 L129 292 L127 250 L124 216" />',
  '<path d="M99 292 L95 304 M111 292 L115 304 M129 292 L125 304 M141 292 L145 304" />',
].join('\n    ');

export function measurementDiagramSvg(): string {
  const drawn = measurementSites
    .map(site => `    <g class="measure-site" data-site="${site.key}" data-anchor="${site.anchor}">${anchorGeometry[site.anchor]}</g>`)
    .join('\n');
  return `<svg class="measure-figure" viewBox="0 0 240 318" role="img" aria-label="身体测量位置示意：身高、臂展、胸围、放松臂围、腰围、大腿围、小腿围与内侧腿长">
    <g class="measure-body">
    ${bodyOutline}
    </g>
    <g class="measure-marks">
${drawn}
    </g>
    <g class="measure-labels">
      <text x="34" y="166" data-label="stature">身高</text>
      <text x="120" y="134" text-anchor="middle" data-label="span">臂展</text>
      <text x="151" y="82" data-label="chest">胸围</text>
      <text x="143" y="122" data-label="waist">腰围</text>
      <text x="186" y="112" data-label="arm">放松臂围</text>
      <text x="139" y="184" data-label="thigh">大腿围</text>
      <text x="142" y="260" data-label="calf">小腿围</text>
      <text x="126" y="232" data-label="inseam">内侧腿长</text>
    </g>
  </svg>`;
}

// Legend rows reuse the form's labels so both describe the same field.
export function measurementLegendHtml(): string {
  return measurementSites.map(site => {
    const field = bodyFields.find(item => item.key === site.key);
    const label = field?.label ?? site.key;
    const optional = field?.required ? '必填' : '可选';
    return `<li data-site="${site.key}"><strong>${label}</strong><span>${optional} · ${site.note}</span></li>`;
  }).join('');
}

export function measurementDiagramHtml(): string {
  return `<details class="measure-sites">
          <summary>测量位置图示</summary>
          <div class="measure-sites-body">
            ${measurementDiagramSvg()}
            <ul class="measure-legend">${measurementLegendHtml()}</ul>
          </div>
          <p class="measure-note">图示只说明量尺位置；所有数值都由你自报，App 不测量你的身体。围度先约束外轮廓，不能据此算出单块肌肉的体积或力量。</p>
        </details>`;
}
