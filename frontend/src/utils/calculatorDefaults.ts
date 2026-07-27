import { safeStorage } from './storage';

/** Where the calculator keeps the numbers a person set once for the account. */
export const CALCULATOR_DEFAULTS_STORAGE_KEY = 'filamenthub_calculator_defaults_v1';

/**
 * The machine-shaped part of those account defaults. A machine nobody has
 * configured yet starts from these instead of an empty form — they are what the
 * person already told us about their printing, just in the wrong place.
 */
export interface AccountMachineDefaults {
  printerPowerW: number;
  printingRatePerHour: number;
  amortizationRatePerHour: number;
  printerPurchasePrice: number;
  printerUsefulHours: number;
}

const EMPTY: AccountMachineDefaults = {
  printerPowerW: 0,
  printingRatePerHour: 0,
  amortizationRatePerHour: 0,
  printerPurchasePrice: 0,
  printerUsefulHours: 0,
};

const positiveNumber = (value: unknown): number =>
  typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : 0;

export function loadAccountMachineDefaults(): AccountMachineDefaults {
  if (typeof window === 'undefined') {
    return EMPTY;
  }
  try {
    const raw = safeStorage.get(CALCULATOR_DEFAULTS_STORAGE_KEY);
    if (!raw) {
      return EMPTY;
    }
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return {
      printerPowerW: positiveNumber(parsed.printerPowerW),
      printingRatePerHour: positiveNumber(parsed.printingRatePerHour),
      amortizationRatePerHour: positiveNumber(parsed.amortizationRatePerHour),
      printerPurchasePrice: positiveNumber(parsed.printerPurchasePrice),
      printerUsefulHours: positiveNumber(parsed.printerUsefulHours),
    };
  } catch {
    return EMPTY;
  }
}
