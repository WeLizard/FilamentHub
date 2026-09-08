import type {
  EconomicsReadiness,
  EconomicsReadinessFieldKey,
  EconomicsReadinessStatus,
  EconomicsSource,
} from '../types/api';

export const ECONOMICS_SOURCE_I18N_KEYS: Record<EconomicsSource, string> = {
  printer_explicit: 'printerCost.readiness.sources.printer_explicit',
  account_explicit: 'printerCost.readiness.sources.account_explicit',
  orca_import: 'printerCost.readiness.sources.orca_import',
  platform_default: 'printerCost.readiness.sources.platform_default',
  catalog_estimate: 'printerCost.readiness.sources.catalog_estimate',
  none: 'printerCost.readiness.sources.none',
};

export const ECONOMICS_FIELD_I18N_KEYS: Record<EconomicsReadinessFieldKey, string> = {
  currency: 'printerCost.readiness.fields.currency',
  machine_hour_rate: 'printerCost.readiness.fields.machine_hour_rate',
  electricity_cost_per_kwh: 'printerCost.readiness.fields.electricity_cost_per_kwh',
  printer_power_w: 'printerCost.readiness.fields.printer_power_w',
  machine_wear_per_hour: 'printerCost.readiness.fields.machine_wear_per_hour',
};

const READINESS_RANK: Record<EconomicsReadinessStatus, number> = {
  configured: 0,
  partial: 1,
  incomplete: 2,
};

export function worstEconomicsReadinessStatus(
  contracts: Array<EconomicsReadiness | null | undefined>,
): EconomicsReadinessStatus | null {
  let result: EconomicsReadinessStatus | null = null;
  for (const contract of contracts) {
    if (!contract) continue;
    if (!result || READINESS_RANK[contract.status] > READINESS_RANK[result]) {
      result = contract.status;
    }
  }
  return result;
}

export function economicsReadinessField(
  readiness: EconomicsReadiness | null | undefined,
  key: EconomicsReadinessFieldKey,
) {
  return readiness?.required_fields.find((field) => field.key === key) ?? null;
}

export function isEconomicsFieldMissing(
  readiness: EconomicsReadiness | null | undefined,
  key: EconomicsReadinessFieldKey,
): boolean | null {
  const field = economicsReadinessField(readiness, key);
  return field ? !field.usable : null;
}

export function enqueueEconomicsSave<T>(
  currentTail: Promise<void>,
  request: () => Promise<T>,
): { task: Promise<T>; tail: Promise<void> } {
  const task = currentTail.catch(() => undefined).then(request);
  return {
    task,
    tail: task.then(() => undefined, () => undefined),
  };
}

export function economicsReadinessResultNoteKey(
  status: EconomicsReadinessStatus | null,
  unavailable: boolean,
): string | null {
  if (unavailable) return 'printerCost.readiness.resultUnavailable';
  if (status === 'incomplete') return 'printerCost.readiness.resultIncomplete';
  if (status === 'partial') return 'printerCost.readiness.resultPartial';
  return null;
}
