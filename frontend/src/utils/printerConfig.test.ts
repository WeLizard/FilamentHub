import { describe, expect, it } from 'vitest';

import type { PrinterProfile } from '../types/api';
import { configLabel, printerConfigurationCardLabel } from './printerConfig';

const t = ((key: string) => key) as never;

function profile(overrides: Partial<PrinterProfile>): PrinterProfile {
  return {
    id: 1,
    name: 'Configuration',
    nozzle_diameters: [0.4],
    printer_model: null,
    printer_name: null,
    orca_printer_model: null,
    ...overrides,
  } as PrinterProfile;
}

describe('configLabel', () => {
  it('uses exact system identity even when vendor and short model differ', () => {
    expect(configLabel(profile({
      name: 'My custom settings',
      orca_printer_model: 'Bambu Lab P2S',
      printer_manufacturer: 'BambuLab',
      printer_model: 'P2S',
      printer_name: 'Legacy display name',
    }), t)).toBe('Bambu Lab P2S · 0.4 printerConfig.mm');
  });

  it('keeps catalog or configuration labels when no system identity is linked', () => {
    expect(configLabel(profile({ printer_name: 'Custom rig' }), t))
      .toBe('Custom rig · 0.4 printerConfig.mm');
    expect(configLabel(profile({ name: 'Unresolved machine', nozzle_diameters: null }), t))
      .toBe('Unresolved machine');
  });
});

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
