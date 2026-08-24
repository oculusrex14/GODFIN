import assert from 'node:assert/strict';
import test from 'node:test';

import {
  copySecretToClipboard,
  generateSecureAlphanumericPassword,
} from '../src/lib/securePassword.js';


test('generated CA tax-pack password is exactly 12 alphanumeric characters', () => {
  const value = generateSecureAlphanumericPassword();

  assert.equal(value.length, 12);
  assert.match(value, /^[A-Za-z0-9]{12}$/);
});


test('generation uses secure random bytes and is not deterministic', () => {
  let seed = 0;
  const provider = {
    getRandomValues(bytes) {
      for (let index = 0; index < bytes.length; index += 1) {
        bytes[index] = (seed + index) % 248;
      }
      seed += 31;
      return bytes;
    },
  };

  const first = generateSecureAlphanumericPassword(12, provider);
  const second = generateSecureAlphanumericPassword(12, provider);

  assert.notEqual(first, second);
  assert.match(first, /^[A-Za-z0-9]{12}$/);
  assert.match(second, /^[A-Za-z0-9]{12}$/);
});


test('generation fails closed when secure randomness is unavailable', () => {
  assert.throws(
    () => generateSecureAlphanumericPassword(12, {}),
    /Secure password generation is unavailable/,
  );
});


test('copy sends the exact password to the Clipboard API', async () => {
  const writes = [];
  const clipboard = {
    async writeText(value) {
      writes.push(value);
    },
  };

  await copySecretToClipboard('Aa09Bb18Cc27', clipboard);

  assert.deepEqual(writes, ['Aa09Bb18Cc27']);
});
