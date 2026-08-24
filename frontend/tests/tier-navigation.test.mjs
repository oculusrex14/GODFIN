import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  lockedRouteMetadata,
  navigationGroupsForLicense,
} from '../src/lib/tierNavigation.js';

const routes = {
  '/transfers': {
    feature: 'multiple_accounts',
    required_tier: 'pro',
    label: 'Transfers',
    explanation: 'Pro transfer matching.',
  },
  '/net-worth': {
    feature: 'net_worth',
    required_tier: 'max',
    label: 'Net Worth',
    explanation: 'Max net worth.',
  },
};
const groups = [{ label: 'Test', items: [
  { to: '/', label: 'Dashboard' },
  { to: '/transfers', label: 'Transfers' },
  { to: '/net-worth', label: 'Net Worth' },
] }];

test('Core, Pro, and Max navigation states are deterministic', () => {
  const core = { tier: 'free', features: [], routes };
  const pro = { tier: 'pro', features: ['multiple_accounts'], routes };
  const max = { tier: 'max', features: ['multiple_accounts', 'net_worth'], routes };

  assert.deepEqual(
    navigationGroupsForLicense(groups, core)[0].items.map((item) => [item.to, item.lock?.required_tier || null]),
    [['/', null], ['/transfers', 'pro'], ['/net-worth', 'max']],
  );
  assert.deepEqual(
    navigationGroupsForLicense(groups, pro)[0].items.map((item) => [item.to, item.lock?.required_tier || null]),
    [['/', null], ['/transfers', null], ['/net-worth', 'max']],
  );
  assert.deepEqual(
    navigationGroupsForLicense(groups, max)[0].items.map((item) => [item.to, item.lock?.required_tier || null]),
    [['/', null], ['/transfers', null], ['/net-worth', null]],
  );
});

test('direct locked routes return their precise upgrade explanation', () => {
  const core = { tier: 'free', features: [], routes };
  assert.equal(lockedRouteMetadata('/', core), null);
  assert.deepEqual(lockedRouteMetadata('/transfers', core), routes['/transfers']);
  assert.deepEqual(lockedRouteMetadata('/net-worth', core), routes['/net-worth']);
});

test('direct routes wait for license metadata and fail closed on lookup errors', () => {
  const source = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8');

  assert.match(source, /if \(isAuthenticated && licenseNavigationLoading\)/);
  assert.match(source, /if \(isAuthenticated && licenseNavigationError\)/);
  assert.match(source, /GODFIN could not check feature access/);
  assert.match(source, /refetchLicenseNavigation/);
});
