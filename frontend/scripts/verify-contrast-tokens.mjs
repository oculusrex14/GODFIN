import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';

const root = path.resolve(process.cwd(), 'src');

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map(async (entry) => {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(target);
    return /\.(?:css|js|jsx)$/.test(entry.name) ? [target] : [];
  }));
  return nested.flat();
}

function luminance(hex) {
  const channels = [1, 3, 5].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16) / 255);
  const linear = channels.map((value) => (
    value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  ));
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrast(foreground, background) {
  const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

const indexCss = await readFile(path.join(root, 'index.css'), 'utf8');
const tokens = {
  primary: '#f8fafc',
  secondary: '#e2ebf3',
  muted: '#c7d6e5',
};
for (const [name, color] of Object.entries(tokens)) {
  assert.match(indexCss, new RegExp(`--color-ink-${name}:\\s*${color}`, 'i'));
  assert.ok(
    contrast(color, '#395772') >= 4.5,
    `${name} text token must remain at least 4.5:1 on the lightest supported glass`,
  );
}

const forbidden = [
  /text-white\/\d+/g,
  /text-(?:slate|gray)-(?:400|500)/g,
  /text-(?:amber|blue|cyan|emerald|green|orange|red|rose|violet)-\d+\/\d+/g,
];
const violations = [];
for (const filename of await sourceFiles(root)) {
  const source = await readFile(filename, 'utf8');
  for (const pattern of forbidden) {
    for (const match of source.matchAll(pattern)) {
      violations.push(`${path.relative(root, filename)}: ${match[0]}`);
    }
  }
}
assert.deepEqual(
  violations,
  [],
  `Required text must use opaque semantic/accessible colors:\n${violations.join('\n')}`,
);

console.log('Semantic text colors pass the static WCAG contrast contract.');
