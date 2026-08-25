import assert from 'node:assert/strict';
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

import { parse } from '@babel/parser';
import traverseModule from '@babel/traverse';

const traverse = traverseModule.default || traverseModule;
const frontendRoot = path.resolve(import.meta.dirname, '..');
const sourceRoot = path.join(frontendRoot, 'src');

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map((entry) => {
    const fullPath = path.join(directory, entry.name);
    return entry.isDirectory() ? sourceFiles(fullPath) : [fullPath];
  }));
  return nested.flat().filter((file) => /\.(jsx|tsx)$/.test(file));
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

function staticAttributeValue(opening, name) {
  const value = attribute(opening, name)?.value;
  return value?.type === 'StringLiteral' ? value.value : null;
}

function containsAccessibleText(children, iconNames) {
  for (const child of children) {
    if (child.type === 'JSXText' && child.value.trim()) return true;
    if (child.type === 'JSXExpressionContainer') {
      if (!['JSXEmptyExpression', 'BooleanLiteral', 'NullLiteral'].includes(child.expression.type)) {
        return true;
      }
    }
    if (child.type === 'JSXElement') {
      if (iconNames.has(jsxName(child.openingElement.name))) continue;
      if (containsAccessibleText(child.children, iconNames)) return true;
    }
  }
  return false;
}

const files = await sourceFiles(sourceRoot);
const violations = [];
let buttonCount = 0;
let fieldCount = 0;
let dialogCount = 0;

for (const file of files) {
  const relative = path.relative(frontendRoot, file);
  const source = await readFile(file, 'utf8');
  const ast = parse(source, { sourceType: 'module', plugins: ['jsx'] });
  const iconNames = new Set();
  const explicitLabels = new Set();

  traverse(ast, {
    ImportDeclaration(nodePath) {
      if (nodePath.node.source.value !== 'lucide-react') return;
      for (const specifier of nodePath.node.specifiers) {
        if (specifier.local?.name) iconNames.add(specifier.local.name);
      }
    },
    JSXOpeningElement(nodePath) {
      if (jsxName(nodePath.node.name) !== 'label') return;
      const target = staticAttributeValue(nodePath.node, 'htmlFor');
      if (target) explicitLabels.add(target);
    },
  });

  traverse(ast, {
    JSXElement(nodePath) {
      const opening = nodePath.node.openingElement;
      const name = jsxName(opening.name);
      const location = `${relative}:${opening.loc.start.line}`;

      if (name === 'button') {
        buttonCount += 1;
        const hasAccessibleAttribute = Boolean(
          attribute(opening, 'aria-label') || attribute(opening, 'aria-labelledby'),
        );
        if (!hasAccessibleAttribute && !containsAccessibleText(nodePath.node.children, iconNames)) {
          violations.push(`${location} icon-only button has no accessible name`);
        }
      }

      if (['input', 'select', 'textarea'].includes(name)) {
        fieldCount += 1;
        if (staticAttributeValue(opening, 'type') === 'hidden') return;
        const hasAccessibleAttribute = Boolean(
          attribute(opening, 'aria-label') || attribute(opening, 'aria-labelledby'),
        );
        const id = staticAttributeValue(opening, 'id');
        const nestedInLabel = Boolean(nodePath.findParent((parent) => (
          parent.isJSXElement() && jsxName(parent.node.openingElement.name) === 'label'
        )));
        const isSharedLabelPrimitive = ['src/components/GlassInput.jsx', 'src/components/GlassSelect.jsx'].includes(relative);
        if (!hasAccessibleAttribute && !(id && explicitLabels.has(id)) && !nestedInLabel && !isSharedLabelPrimitive) {
          violations.push(`${location} ${name} has no programmatic label`);
        }
      }

      if (name === 'DialogSurface') {
        dialogCount += 1;
        if (!attribute(opening, 'labelledBy') && !attribute(opening, 'ariaLabel')) {
          violations.push(`${location} DialogSurface has no accessible name`);
        }
      }

      if (relative !== 'src/components/DialogSurface.jsx' && (
        staticAttributeValue(opening, 'role') === 'dialog'
        || staticAttributeValue(opening, 'aria-modal') === 'true'
      )) {
        violations.push(`${location} bypasses the shared DialogSurface`);
      }
    },
  });
}

const appLayout = await readFile(path.join(sourceRoot, 'components/AppLayout.jsx'), 'utf8');
assert.match(appLayout, /href="#main-content"/);
assert.match(appLayout, />\s*Skip to main content\s*</);
assert.match(appLayout, /<main id="main-content"[^>]*tabIndex=\{-1\}/);
assert.match(appLayout, /querySelector\('h1'\)/);

const app = await readFile(path.join(sourceRoot, 'App.jsx'), 'utf8');
assert.match(app, /<MotionConfig reducedMotion="user">/);
for (const routePage of [
  'Advisor.jsx',
  'AuditManager.jsx',
  'BehaviorInsights.jsx',
  'Budget.jsx',
  'CashFlow.jsx',
  'Dashboard.jsx',
  'Income.jsx',
  'LearnGodfin.jsx',
  'NetWorth.jsx',
  'Reports.jsx',
  'ReviewQueue.jsx',
  'Settings.jsx',
  'Subscriptions.jsx',
  'Transactions.jsx',
  'Transfers.jsx',
  'Upload.jsx',
]) {
  assert.match(
    await readFile(path.join(sourceRoot, 'pages', routePage), 'utf8'),
    /<h1\b/,
    `${routePage} must expose a route heading for focus management.`,
  );
}
const styles = await readFile(path.join(sourceRoot, 'index.css'), 'utf8');
assert.match(styles, /@media \(prefers-reduced-motion: reduce\)/);
assert.match(styles, /:focus-visible/);

const toast = await readFile(path.join(sourceRoot, 'context/ToastContext.jsx'), 'utf8');
assert.match(toast, /role=\{toast\.type === 'error' \? 'alert' : 'status'\}/);
assert.match(toast, /aria-label="Dismiss notification"/);

const dialog = await readFile(path.join(sourceRoot, 'components/DialogSurface.jsx'), 'utf8');
for (const requiredContract of [
  /role="dialog"/,
  /aria-modal="true"/,
  /event\.key === 'Escape'/,
  /event\.key !== 'Tab'/,
  /previouslyFocused\.focus/,
  /sibling\.inert = true/,
  /document\.body\.style\.overflow = 'hidden'/,
]) {
  assert.match(dialog, requiredContract);
}

assert.equal(violations.length, 0, violations.join('\n'));
assert.ok(buttonCount >= 150, `Expected broad button coverage, found ${buttonCount}`);
assert.ok(fieldCount >= 45, `Expected broad form-field coverage, found ${fieldCount}`);
assert.ok(dialogCount >= 20, `Expected every modal to use DialogSurface, found ${dialogCount}`);

process.stdout.write(
  `Accessibility contracts pass: ${buttonCount} buttons, ${fieldCount} raw fields, ${dialogCount} dialogs.\n`,
);
