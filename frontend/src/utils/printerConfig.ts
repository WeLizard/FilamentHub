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
