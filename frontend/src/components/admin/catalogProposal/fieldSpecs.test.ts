import { describe, expect, it } from 'vitest';

import { rangeFor } from './fieldSpecs';

describe('rangeFor', () => {
  it('pairs both ends of a card range from either end', () => {
    const nozzle = { base: 'recommended_nozzle_temp', min: 'recommended_nozzle_temp_min', max: 'recommended_nozzle_temp_max' };
    expect(rangeFor('filaments', 'recommended_nozzle_temp_min')).toEqual(nozzle);
    expect(rangeFor('filaments', 'recommended_nozzle_temp_max')).toEqual(nozzle);
    expect(rangeFor('filaments', 'storage_temperature_max_c'))
      .toEqual({ base: 'storage_temperature_c', min: 'storage_temperature_min_c', max: 'storage_temperature_max_c' });
  });

  it('leaves a lone limit as a single value', () => {
    expect(rangeFor('filaments', 'storage_relative_humidity_max_percent')).toBeNull();
  });

  it('pairs a new field whose partner is present in the row', () => {
    expect(rangeFor('filaments', 'print_speed_min', { print_speed_min: 50, print_speed_max: 200 }))
      .toEqual({ base: 'print_speed', min: 'print_speed_min', max: 'print_speed_max' });
  });
});
