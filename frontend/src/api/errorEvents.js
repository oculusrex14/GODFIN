const listeners = new Set();
let lastEvent = { key: '', at: 0 };

export function reportApiError(error) {
  if (!error || error.status === 401) return;

  const key = `${error.code || 'ERROR'}:${error.message || 'Request failed'}`;
  const now = Date.now();
  if (lastEvent.key === key && now - lastEvent.at < 1000) return;
  lastEvent = { key, at: now };

  for (const listener of listeners) {
    listener(error);
  }
}

export function subscribeToApiErrors(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
