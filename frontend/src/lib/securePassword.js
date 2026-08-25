const ALPHANUMERIC = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';

export function generateSecureAlphanumericPassword(
  length = 12,
  cryptoProvider = globalThis.crypto,
) {
  if (!Number.isSafeInteger(length) || length < 1 || length > 128) {
    throw new RangeError('Password length must be between 1 and 128.');
  }
  if (!cryptoProvider?.getRandomValues) {
    throw new Error('Secure password generation is unavailable on this device.');
  }

  const rejectionLimit = 256 - (256 % ALPHANUMERIC.length);
  let password = '';
  while (password.length < length) {
    const bytes = new Uint8Array(Math.max(16, (length - password.length) * 2));
    cryptoProvider.getRandomValues(bytes);
    for (const byte of bytes) {
      if (byte >= rejectionLimit) continue;
      password += ALPHANUMERIC[byte % ALPHANUMERIC.length];
      if (password.length === length) break;
    }
  }
  return password;
}

export async function copySecretToClipboard(
  value,
  clipboard = globalThis.navigator?.clipboard,
) {
  if (typeof value !== 'string' || value.length === 0 || !clipboard?.writeText) {
    throw new Error('Clipboard copying is unavailable.');
  }
  await clipboard.writeText(value);
}
