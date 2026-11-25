import { siteOrigin } from './siteLocale';

// The organisation behind the site. Its full description is the static
// Organization block in index.html; pages refer to it by the same @id.
export const ORGANIZATION_ID = `${siteOrigin('en')}/#organization`;

export function organizationReference() {
  return {
    '@type': 'Organization',
    '@id': ORGANIZATION_ID,
    name: 'FilamentHub',
    url: `${siteOrigin('en')}/`,
  } as const;
}
