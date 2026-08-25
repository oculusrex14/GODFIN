import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { spawnSync } from 'node:child_process';

import { parse } from '@babel/parser';
import traverseModule from '@babel/traverse';

const traverse = traverseModule.default || traverseModule;
const frontendRoot = path.resolve(import.meta.dirname, '..');
const projectRoot = path.resolve(frontendRoot, '..');
const sourceRoot = path.join(frontendRoot, 'src');
const outputArgument = process.argv.indexOf('--output');
const outputPath = outputArgument >= 0
  ? path.resolve(process.cwd(), process.argv[outputArgument + 1])
  : path.join(frontendRoot, 'build', 'interactive-action-manifest.json');

const PAGE_ROUTES = {
  'Advisor.jsx': '/advisor',
  'AuditManager.jsx': '/audit',
  'BehaviorInsights.jsx': '/behavior-insights',
  'Budget.jsx': '/budget',
  'CashFlow.jsx': '/cash-flow',
  'Dashboard.jsx': '/',
  'Income.jsx': '/income',
  'LearnGodfin.jsx': '/learn',
  'NetWorth.jsx': '/net-worth',
  'Onboarding.jsx': '/onboarding',
  'PinScreen.jsx': '/pin',
  'Reports.jsx': '/reports',
  'ReviewQueue.jsx': '/review',
  'Settings.jsx': '/settings',
  'Subscriptions.jsx': '/subscriptions',
  'Transactions.jsx': '/transactions',
  'Transfers.jsx': '/transfers',
  'Upload.jsx': '/upload',
};

const SETTINGS_COMPONENTS = new Set([
  'AccountSettings.jsx',
  'ClassificationMemorySettings.jsx',
  'DataContributionSettings.jsx',
  'GmailSettings.jsx',
  'LLMSettings.jsx',
  'LicenseSettings.jsx',
  'LocalAISetup.jsx',
]);
const INTERACTIVE_COMPONENTS = new Set([
  'GlassButton', 'GlassInput', 'GlassSelect', 'NavLink', 'Link', 'DialogSurface',
]);
const DESTRUCTIVE_WORDS = /\b(delete|remove|reset|discard|deactivate|disconnect|restore|void|revoke|forget)\b/i;

async function filesUnder(directory, pattern) {
  let entries;
  try {
    entries = await readdir(directory, { withFileTypes: true });
  } catch {
    return [];
  }
  const nested = await Promise.all(entries.map(async (entry) => {
    const fullPath = path.join(directory, entry.name);
    return entry.isDirectory() ? filesUnder(fullPath, pattern) : [fullPath];
  }));
  return nested.flat().filter((filename) => pattern.test(filename));
}

function jsxName(node) {
  if (node?.type === 'JSXIdentifier') return node.name;
  if (node?.type === 'JSXMemberExpression') {
    return `${jsxName(node.object)}.${jsxName(node.property)}`;
  }
  return '';
}

function attribute(opening, name) {
  return opening.attributes.find((item) => (
    item.type === 'JSXAttribute' && item.name?.name === name
  ));
}

function attributeText(opening, name, source) {
  const item = attribute(opening, name);
  if (!item) return '';
  if (!item.value) return 'true';
  if (item.value.type === 'StringLiteral') return item.value.value.trim();
  if (item.value.type === 'JSXExpressionContainer') {
    const expression = item.value.expression;
    if (expression.type === 'StringLiteral') return expression.value.trim();
    return source.slice(expression.start, expression.end).replace(/\s+/g, ' ').trim();
  }
  return '';
}

function childText(node, source) {
  const parts = [];
  for (const child of node.children || []) {
    if (child.type === 'JSXText') parts.push(child.value);
    if (child.type === 'JSXElement') parts.push(childText(child, source));
    if (child.type === 'JSXExpressionContainer') {
      const expression = child.expression;
      if (expression.type === 'StringLiteral') parts.push(expression.value);
      if (expression.type === 'TemplateLiteral') {
        parts.push(expression.quasis.map((item) => item.value.cooked).join(' '));
      }
      if (expression.type === 'Identifier') parts.push(`{${expression.name}}`);
    }
  }
  return parts.join(' ').replace(/\s+/g, ' ').trim().slice(0, 160);
}

function routeFor(relative) {
  const basename = path.basename(relative);
  if (PAGE_ROUTES[basename]) return PAGE_ROUTES[basename];
  if (SETTINGS_COMPONENTS.has(basename)) return '/settings';
  return '*';
}

function classifyControl(opening, name, accessibleName, source) {
  const role = attributeText(opening, 'role', source);
  const type = attributeText(opening, 'type', source);
  if (name === 'DialogSurface' || role === 'dialog') return 'dialog';
  if (role === 'tab') return 'tab';
  if (role === 'menuitem') return 'menuitem';
  if (role === 'switch' || type === 'checkbox' || attribute(opening, 'aria-pressed')) return 'toggle';
  if (type === 'file') return 'upload';
  if (/\b(next|previous|page \d|pagination)\b/i.test(accessibleName)) return 'pagination';
  if (['input', 'GlassInput'].includes(name)) return 'input';
  if (['select', 'GlassSelect'].includes(name)) return 'select';
  if (name === 'textarea') return 'textarea';
  if (['a', 'NavLink', 'Link'].includes(name)) return 'link';
  if (name === 'button' || name === 'GlassButton' || role === 'button') return 'button';
  return 'keyboard-shortcut';
}

function testTarget(route, kind, destructive) {
  if (destructive || kind === 'upload') {
    return {
      mode: 'manual-native',
      target: 'docs/production-remediation/NATIVE_CONTROL_ACCEPTANCE.md',
      status: 'pending-final-candidate',
    };
  }
  if (['/pin', '/onboarding', '/settings', '/learn', '*'].includes(route)) {
    return {
      mode: 'playwright',
      target: 'playwright-tests/tests/accessibility-smoke.test.js',
      status: 'mapped-awaiting-final-run',
    };
  }
  return {
    mode: 'playwright',
    target: 'playwright-tests/tests/remediation-ui.test.js',
    status: 'mapped-awaiting-final-run',
  };
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

async function directoryDigest(directory) {
  const files = (await filesUnder(directory, /./)).sort();
  if (!files.length) return null;
  const hash = createHash('sha256');
  for (const filename of files) {
    hash.update(path.relative(directory, filename));
    hash.update(await readFile(filename));
  }
  return hash.digest('hex');
}

function gitSha() {
  const result = spawnSync('git', ['rev-parse', 'HEAD'], {
    cwd: projectRoot,
    encoding: 'utf8',
    shell: false,
  });
  const candidate = String(result.stdout || '').trim().toLowerCase();
  return /^[0-9a-f]{40}$/.test(candidate) ? candidate : 'unknown';
}

const controls = [];
const sourceFiles = await filesUnder(sourceRoot, /\.(?:jsx|tsx)$/);
for (const filename of sourceFiles.sort()) {
  const source = await readFile(filename, 'utf8');
  const relative = path.relative(projectRoot, filename);
  const ast = parse(source, { sourceType: 'module', plugins: ['jsx'] });
  traverse(ast, {
    JSXElement(nodePath) {
      const opening = nodePath.node.openingElement;
      const name = jsxName(opening.name);
      const role = attributeText(opening, 'role', source);
      const handlers = opening.attributes
        .filter((item) => item.type === 'JSXAttribute' && /^on[A-Z]/.test(item.name?.name || ''))
        .map((item) => item.name.name)
        .sort();
      const native = ['button', 'a', 'input', 'select', 'textarea'].includes(name);
      const interactive = native
        || INTERACTIVE_COMPONENTS.has(name)
        || ['button', 'switch', 'tab', 'menuitem', 'dialog'].includes(role)
        || handlers.includes('onKeyDown');
      if (!interactive) return;
      if (name === 'input' && attributeText(opening, 'type', source) === 'hidden') return;

      const line = opening.loc.start.line;
      const route = routeFor(relative);
      const accessibleName = (
        attributeText(opening, 'aria-label', source)
        || attributeText(opening, 'ariaLabel', source)
        || attributeText(opening, 'label', source)
        || attributeText(opening, 'title', source)
        || childText(nodePath.node, source)
        || `${name} at line ${line}`
      ).slice(0, 160);
      const kind = classifyControl(opening, name, accessibleName, source);
      const handlerText = handlers.map((handler) => attributeText(opening, handler, source)).join(' ');
      const destructive = DESTRUCTIVE_WORDS.test(`${accessibleName} ${handlerText}`);
      const coverage = testTarget(route, kind, destructive);
      const location = `${relative}:${line}`;
      const id = `control-${sha256(`${location}|${kind}|${accessibleName}`).slice(0, 16)}`;
      const states = ['normal', 'keyboard'];
      if (attribute(opening, 'disabled')) states.push('disabled', 'loading-or-pending');
      if (['input', 'select', 'textarea', 'upload'].includes(kind)) {
        states.push('validation-failure', 'slow-input-paste-ime');
      }
      if (handlers.includes('onClick') || handlers.includes('onSubmit')) states.push('repeat-or-double-action');
      if (kind === 'dialog') states.push('escape', 'focus-return', 'focus-trap');
      controls.push({
        id,
        route,
        kind,
        accessible_name: accessibleName,
        source: location,
        handlers,
        destructive,
        required_states: [...new Set(states)],
        coverage,
      });
    },
  });
}

assert.ok(controls.length >= 300, `Expected at least 300 interactive controls, found ${controls.length}`);
assert.equal(new Set(controls.map((item) => item.id)).size, controls.length, 'Control IDs must be unique');
assert.ok(controls.every((item) => item.coverage?.target), 'Every control must have a coverage mapping');

const manifest = {
  schema_version: 1,
  candidate_sha: gitSha(),
  evidence_status: 'mapping-only; final browser/native evidence not yet attached',
  generated_at_utc: new Date().toISOString(),
  source_digest_sha256: await directoryDigest(sourceRoot),
  production_build_digest_sha256: await directoryDigest(path.join(frontendRoot, 'dist')),
  routes: [...new Set(controls.map((item) => item.route))].sort(),
  summary: {
    controls: controls.length,
    playwright_mapped: controls.filter((item) => item.coverage.mode === 'playwright').length,
    manual_native_mapped: controls.filter((item) => item.coverage.mode === 'manual-native').length,
    final_evidence_attached: 0,
  },
  controls,
};

await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
process.stdout.write(
  `Interactive action manifest: ${controls.length} controls, ${manifest.routes.length} route scopes -> ${outputPath}\n`,
);
