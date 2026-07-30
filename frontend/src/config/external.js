export function openExternalUrl(rawUrl) {
  const url = new URL(rawUrl);
  if (url.protocol !== 'https:') {
    throw new Error('Only secure website links can be opened.');
  }
  window.open(url.toString(), '_blank', 'noopener,noreferrer');
}
