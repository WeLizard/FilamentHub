export type ImportedPresetRequiredField = 'extruder_temp' | 'bed_temp';

export const isImportedPresetFieldMissing = (
  settings: Record<string, unknown> | null | undefined,
  field: ImportedPresetRequiredField,
): boolean => {
  const missingFields = settings?.import_missing_fields;
  return Array.isArray(missingFields) && missingFields.includes(field);
};

export const formatImportedPresetTemperature = (
  settings: Record<string, unknown> | null | undefined,
  field: ImportedPresetRequiredField,
  value: number,
): string => (
  isImportedPresetFieldMissing(settings, field) ? '—' : `${value}°C`
);
