import assert from 'node:assert/strict';
import test from 'node:test';


function instrumentedStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  const calls = [];
  return {
    calls,
    getItem(key) {
      calls.push(['getItem', key]);
      return values.get(key) ?? null;
    },
    setItem(key, value) {
      calls.push(['setItem', key, value]);
      values.set(key, value);
    },
    removeItem(key) {
      calls.push(['removeItem', key]);
      values.delete(key);
    },
    value(key) {
      return values.get(key) ?? null;
    },
  };
}


test('auth token remains memory-only and reloads start locked', async () => {
  const localStorage = instrumentedStorage({
    godfin_auth_token: 'legacy-local-token',
    token: 'legacy-generic-token',
  });
  const sessionStorage = instrumentedStorage({
    auth_token: 'legacy-session-token',
  });
  const navigations = [];
  globalThis.window = {
    localStorage,
    sessionStorage,
    location: {
      protocol: 'http:',
      pathname: '/',
      assign(path) {
        navigations.push(path);
      },
    },
  };

  const client = await import(`../src/api/client.js?auth-memory=${Date.now()}`);

  assert.equal(client.isBackendAlive({ status: 'alive', liveness: true }), true);
  assert.equal(client.isBackendAlive({ status: 'ok' }), false);
  assert.equal(client.isBackendAlive({ status: 'alive', liveness: false }), false);

  for (const key of ['godfin_auth_token', 'token', 'auth_token']) {
    assert.equal(localStorage.value(key), null);
    assert.equal(sessionStorage.value(key), null);
  }
  assert.equal(
    [...localStorage.calls, ...sessionStorage.calls].some(([operation]) => (
      operation === 'getItem' || operation === 'setItem'
    )),
    false,
  );

  client.setAuthToken('current-memory-token');
  assert.equal(client.getAuthToken(), 'current-memory-token');
  assert.equal(
    [...localStorage.calls, ...sessionStorage.calls].some(([operation]) => (
      operation === 'setItem'
    )),
    false,
  );

  const reloaded = await import(`../src/api/client.js?auth-reload=${Date.now()}`);
  assert.equal(reloaded.getAuthToken(), null);

  let logoutAuthorization = null;
  globalThis.fetch = async (_url, options) => {
    logoutAuthorization = new Headers(options.headers).get('Authorization');
    return new Response('{}', {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };
  client.setAuthToken('logout-token');
  const logoutPromise = client.logoutSession();
  assert.equal(client.getAuthToken(), null);
  await logoutPromise;
  assert.equal(logoutAuthorization, 'Bearer logout-token');

  globalThis.fetch = async () => new Response(
    JSON.stringify({ code: 'AUTH_REQUIRED', message: 'Session expired.' }),
    {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    },
  );
  client.setAuthToken('expired-token');
  await assert.rejects(client.apiFetch('/transactions'), /Session expired/);
  assert.equal(client.getAuthToken(), null);
  assert.deepEqual(navigations, ['/pin']);
});
