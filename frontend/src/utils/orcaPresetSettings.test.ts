import { describe, expect, it } from 'vitest';

import {
  applyOrcaLinesFromUi,
  applyOrcaUiSetting,
  cloneOrcaSettings,
  formatOrcaFlowRatio,
  isOrcaBedTemperatureSentinel,
  normalizeOrcaSettingsForUi,
  readOrcaNumber,
  readOrcaText,
} from './orcaPresetSettings';

describe('Orca preset settings', () => {
  it('normalizes scalar and array values for the editor without truncating scalars', () => {
    const normalized = normalizeOrcaSettingsForUi({
      nozzle_temperature: '260',
      pressure_advance: ['0.02'],
      filament_soluble: 0,
    });

    expect(normalized.nozzle_temperature[0]).toBe('260');
    expect(normalized.pressure_advance[0]).toBe('0.02');
    expect(normalized.filament_soluble[0]).toBe(0);
  });

  it('reads numbers from scalar and array settings', () => {
    expect(readOrcaNumber({ value: '460' }, 'value')).toBe(460);
    expect(readOrcaNumber({ value: ['1.0348'] }, 'value')).toBe(1.0348);
    expect(readOrcaNumber({ value: ['0'] }, 'value')).toBe(0);
    expect(readOrcaNumber({ value: ['nil'] }, 'value')).toBeNull();
  });

  it('reads text settings without losing zero and treats nil as empty', () => {
    expect(readOrcaText({ value: 0 }, 'value')).toBe('0');
    expect(readOrcaText({ value: ['0'] }, 'value')).toBe('0');
    expect(readOrcaText({ value: ['nil'] }, 'value')).toBe('');
  });

  it('recognizes Orca inherited bed-temperature sentinels', () => {
    expect(isOrcaBedTemperatureSentinel('nil')).toBe(true);
    expect(isOrcaBedTemperatureSentinel('V')).toBe(true);
    expect(isOrcaBedTemperatureSentinel('60')).toBe(false);
  });

  it('clones the source object so unknown plugin settings survive an edit', () => {
    const source = { filament_plugin_config_overrides: '{"fixture":true}' };
    const cloned = cloneOrcaSettings(source);
    cloned.nozzle_temperature = ['220'];

    expect(cloned.filament_plugin_config_overrides).toBe('{"fixture":true}');
    expect(source).not.toHaveProperty('nozzle_temperature');
  });

  it('preserves unchanged arrays, zero and nil while editing another setting', () => {
    const source = {
      pressure_advance: ['0', '0.02'],
      additional_cooling_fan_speed: ['nil'],
      plugin_owned: { fixture: true },
    };
    const target = cloneOrcaSettings(source);

    applyOrcaUiSetting(target, source, 'pressure_advance', 0);
    applyOrcaUiSetting(target, source, 'additional_cooling_fan_speed', '');

    expect(target).toEqual(source);
  });

  it('preserves line arrays exactly until their field is edited', () => {
    const source = { filament_start_gcode: ['G28', '', 'M117 Ready'] };
    const target = cloneOrcaSettings(source);

    applyOrcaLinesFromUi(target, source, 'filament_start_gcode', 'G28\n\nM117 Ready');
    expect(target.filament_start_gcode).toEqual(['G28', '', 'M117 Ready']);

    applyOrcaLinesFromUi(target, source, 'filament_start_gcode', 'G28\n\nM117 Printing');
    expect(target.filament_start_gcode).toEqual(['G28', '', 'M117 Printing']);
  });

  it('serializes flow ratio without reducing Orca precision', () => {
    expect(formatOrcaFlowRatio(92.6)).toBe('0.926');
    expect(formatOrcaFlowRatio(103.48)).toBe('1.0348');
  });
});
