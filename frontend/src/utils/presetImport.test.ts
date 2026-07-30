import { describe, expect, it } from 'vitest';
import {
  formatImportedPresetTemperature,
  isImportedPresetFieldMissing,
} from './presetImport';

describe('imported preset helpers', () => {
  it('marks only explicitly missing imported fields', () => {
    const settings = {
      import_requires_review: true,
      import_missing_fields: ['bed_temp'],
    };

    expect(isImportedPresetFieldMissing(settings, 'bed_temp')).toBe(true);
    expect(isImportedPresetFieldMissing(settings, 'extruder_temp')).toBe(false);
  });

  it('renders an unknown imported temperature as a dash', () => {
    const settings = { import_missing_fields: ['bed_temp'] };

    expect(formatImportedPresetTemperature(settings, 'bed_temp', 0)).toBe('—');
    expect(formatImportedPresetTemperature(settings, 'extruder_temp', 182)).toBe('182°C');
  });

  it('keeps a real zero when the source explicitly supplied it', () => {
    expect(formatImportedPresetTemperature({}, 'bed_temp', 0)).toBe('0°C');
  });
});
