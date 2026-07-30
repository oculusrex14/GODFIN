export const GODFIN_WEBSITE_ORIGIN = (
  import.meta.env.VITE_GODFIN_WEBSITE_URL || 'https://godfin.vercel.app'
).replace(/\/$/, '');

export function websiteUrl(path = '/') {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${GODFIN_WEBSITE_ORIGIN}${normalizedPath}`;
}

export function openWebsite(path) {
  window.open(websiteUrl(path), '_blank', 'noopener,noreferrer');
}

