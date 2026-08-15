/**
 * Links to networks owned by Meta Platforms, whose activity is banned in Russia.
 *
 * A brand fills its own social links, so these can appear on a public brand page
 * without FilamentHub ever naming the company. Russian law expects a note about
 * the ban next to such a mention, so the page needs to know when one is present.
 */

const META_HOSTS = ['facebook.com', 'fb.com', 'instagram.com', 'threads.net'];

function isMetaHost(value: string | null | undefined): boolean {
  if (!value) return false;
  try {
    const host = new URL(value).hostname.replace(/^www\./, '').toLowerCase();
    return META_HOSTS.some((meta) => host === meta || host.endsWith(`.${meta}`));
  } catch {
    return false;
  }
}

export function hasMetaNetworkLink(urls: (string | null | undefined)[]): boolean {
  return urls.some(isMetaHost);
}
