import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const layout = await readFile(
  new URL('../src/components/AppLayout.jsx', import.meta.url),
  'utf8',
);
const settings = await readFile(
  new URL('../src/pages/Settings.jsx', import.meta.url),
  'utf8',
);

test('sidebar and support details use the backend build identity', () => {
  assert.match(layout, /fetchSystemStatus/);
  assert.match(layout, /build\?\.version/);
  assert.match(layout, /build\.channel/);
  assert.match(layout, /build\?\.short_sha/);
  assert.doesNotMatch(layout, />\s*v2\.0\s*</);

  assert.match(settings, /systemStatus\?\.build\?\.version/);
  assert.match(settings, /systemStatus\?\.build\?\.short_sha/);
  assert.match(settings, /systemStatus\?\.build\?\.channel/);
});
