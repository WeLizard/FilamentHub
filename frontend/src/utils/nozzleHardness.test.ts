import { describe, it, expect } from 'vitest';
import { configuredNozzleHrc, isNozzleTooSoft } from './nozzleHardness';

describe('configuredNozzleHrc', () => {
  it('takes the explicit nozzle_hrc when the profile carries one', () => {
    expect(configuredNozzleHrc({ nozzle_hrc: 62, nozzle_type: 'brass' })).toBe(62);
  });

  it('falls back to the nozzle type table', () => {
    expect(configuredNozzleHrc({ nozzle_type: 'hardened_steel' })).toBe(55);
    expect(configuredNozzleHrc({ nozzle_type: 'brass' })).toBe(2);
    expect(configuredNozzleHrc({ nozzle_type: 'tungsten_carbide' })).toBe(85);
  });

  it('reads Orca array-shaped values', () => {
    expect(configuredNozzleHrc({ nozzle_type: ['hardened_steel'] })).toBe(55);
    expect(configuredNozzleHrc({ nozzle_hrc: ['60'] })).toBe(60);
  });

  it('treats unknown hardness as unknown, not as soft', () => {
    expect(configuredNozzleHrc({ nozzle_type: 'undefine' })).toBeNull();
    expect(configuredNozzleHrc({ nozzle_hrc: 0, nozzle_type: 'undefine' })).toBeNull();
    expect(configuredNozzleHrc({})).toBeNull();
    expect(configuredNozzleHrc(null)).toBeNull();
  });
});

describe('isNozzleTooSoft', () => {
  it('warns when the configured nozzle is softer than the material needs', () => {
    expect(isNozzleTooSoft(50, 2)).toBe(true);
    expect(isNozzleTooSoft(60, 55)).toBe(true);
  });

  it('stays silent when the nozzle is hard enough', () => {
    expect(isNozzleTooSoft(50, 55)).toBe(false);
    expect(isNozzleTooSoft(50, 50)).toBe(false);
  });

  it('stays silent when either side is unknown', () => {
    expect(isNozzleTooSoft(50, null)).toBe(false);
    expect(isNozzleTooSoft(null, 2)).toBe(false);
    expect(isNozzleTooSoft(undefined, undefined)).toBe(false);
  });
});
