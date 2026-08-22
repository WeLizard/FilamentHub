import type { TFunction } from 'i18next';
import type { PrinterProfile } from '../types/api';

/** Human label for an Orca configuration: catalog model + primary nozzle. */
export function configLabel(profile: PrinterProfile, t: TFunction): string {
  const model =
    profile.printer_model || profile.printer_name || profile.name;
  const nozzle =
    profile.nozzle_diameters && profile.nozzle_diameters.length > 0
      ? profile.nozzle_diameters[0]
      : null;
  return nozzle ? `${model} · ${nozzle} ${t('printerConfig.mm')}` : model;
}

function isNozzleOnlySuffix(suffix: string, nozzles: number[]): boolean {
  const withoutLabels = suffix
    .toLowerCase()
    .replace(/\bnozzles?\b/gu, ' ')
    .replace(/\bmm\b/gu, ' ')
    .replace(/мм/gu, ' ')
    .replace(/сопл(?:о|а)/gu, ' ')
    .replace(/喷嘴/gu, ' ');
  const numericTokens = withoutLabels.match(/\d+(?:[.,]\d+)?/gu) ?? [];
  const textRemainder = withoutLabels
    .replace(/\d+(?:[.,]\d+)?/gu, ' ')
    .replace(/[()[\]{}.,;:·/_+&–—-]/gu, ' ')
    .replace(/\s/gu, '');

  if (textRemainder.length > 0 || numericTokens.length === 0) return false;

  return numericTokens.every((token) => {
    const value = Number.parseFloat(token.replace(',', '.'));
    return nozzles.some((nozzle) => Math.abs(nozzle - value) < 0.0001);
  });
}

/**
 * Compact display label for a machine configuration inside its physical
 * printer card. Stored Orca names are never changed: only a demonstrably
 * redundant "printer name + nozzle" label is shortened.
 */
export function printerConfigurationCardLabel(
  profile: PrinterProfile,
  physicalPrinterName: string | null | undefined,
  t: TFunction,
): string {
  const nozzles = profile.nozzle_diameters ?? [];
  if (nozzles.length === 0) return profile.name;

  const candidates = Array.from(
    new Set(
      [physicalPrinterName, profile.printer_model, profile.printer_name]
        .map((value) => value?.trim())
        .filter((value): value is string => Boolean(value)),
    ),
  ).sort((left, right) => right.length - left.length);
  const profileName = profile.name.trim();

  const redundant = candidates.some((candidate) => {
    if (profileName.localeCompare(candidate, undefined, { sensitivity: 'accent' }) === 0) {
      return true;
    }
    if (!profileName.toLowerCase().startsWith(candidate.toLowerCase())) return false;

    const suffix = profileName.slice(candidate.length);
    if (!/^[\s()[\]{}.,;:·/_+&–—-]/u.test(suffix)) return false;
    return isNozzleOnlySuffix(suffix, nozzles);
  });

  if (!redundant) return profile.name;

  return `${t('profilePage.nozzles')}: ${nozzles.join(', ')} ${t('profilePage.mm')}`;
}
