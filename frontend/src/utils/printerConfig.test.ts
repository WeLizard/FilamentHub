import { describe, expect, it } from 'vitest';

import type { PrinterProfile } from '../types/api';
import { printerConfigurationCardLabel } from './printerConfig';

const t = ((key: string) => key) as never;

function profile(overrides: Partial<PrinterProfile>): PrinterProfile {
  return {
    id: 1,
    name: 'Configuration',
    nozzle_diameters: [0.4],
    printer_model: null,
    printer_name: null,
    ...overrides,
  } as PrinterProfile;
}

describe('printerConfigurationCardLabel', () => {
  it('shortens a redundant physical printer and nozzle label', () => {
    expect(
      printerConfigurationCardLabel(
        profile({ name: 'Voron 2.4 350 0.4 nozzle' }),
        'Voron 2.4 350',
        t,
      ),
    ).toBe('profilePage.nozzles: 0.4 profilePage.mm');
  });

  it('shortens the exact physical printer name when the nozzle is stored separately', () => {
    expect(
      printerConfigurationCardLabel(
        profile({ name: 'Voron 2.4 350' }),
        'Voron 2.4 350',
        t,
      ),
    ).toBe('profilePage.nozzles: 0.4 profilePage.mm');
  });

  it('keeps a meaningful custom suffix', () => {
    const name = 'Voron 2.4 350 0.4 nozzle - Fast prototype';
    expect(
      printerConfigurationCardLabel(profile({ name }), 'Voron 2.4 350', t),
    ).toBe(name);
  });

  it('does not hide model numbers when only a generic parent name matches', () => {
    const name = 'Voron 2.4 350 0.4 nozzle';
    expect(printerConfigurationCardLabel(profile({ name }), 'Voron', t)).toBe(name);
  });

  it('keeps an unrelated custom configuration name', () => {
    const name = 'MyKlipper 0.4 nozzle';
    expect(
      printerConfigurationCardLabel(profile({ name }), 'Voron 2.4 350', t),
    ).toBe(name);
  });
});
