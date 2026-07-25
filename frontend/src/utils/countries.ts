export const COUNTRY_CODES = [
  'AE', 'AM', 'AR', 'AT', 'AU', 'AZ', 'BE', 'BG', 'BR', 'BY', 'CA', 'CH', 'CL', 'CN',
  'CO', 'CZ', 'DE', 'DK', 'EE', 'EG', 'ES', 'FI', 'FR', 'GB', 'GE', 'GR', 'HK', 'HR',
  'HU', 'ID', 'IE', 'IL', 'IN', 'IR', 'IS', 'IT', 'JP', 'KG', 'KR', 'KZ', 'LT', 'LU',
  'LV', 'MA', 'MD', 'MX', 'MY', 'NL', 'NO', 'NZ', 'PE', 'PH', 'PL', 'PT', 'RO', 'RS',
  'RU', 'SA', 'SE', 'SG', 'SI', 'SK', 'TH', 'TR', 'TW', 'UA', 'US', 'UY', 'UZ', 'VN',
  'ZA',
] as const;

export function countryName(code: string, locale: string): string {
  try {
    const names = new Intl.DisplayNames([locale], { type: 'region' });
    return names.of(code) ?? code;
  } catch {
    return code;
  }
}

export function sortedCountries(locale: string): { code: string; name: string }[] {
  const collator = new Intl.Collator(locale);
  return COUNTRY_CODES
    .map((code) => ({ code, name: countryName(code, locale) }))
    .sort((a, b) => collator.compare(a.name, b.name));
}
