import { describe, expect, it } from 'vitest';
import type { PrinterConnectionBinding } from '../api/client';
import { visiblePrinterConnections } from './printerConnections';

const binding = (
  overrides: Partial<PrinterConnectionBinding>,
): PrinterConnectionBinding => ({
  id: 1,
  physical_printer_id: 1,
  physical_printer_name: 'Workshop printer',
  connection_ref: 'local-ref',
  preset_name: 'Workshop preset',
  provider: 'octoprint',
  display_endpoint: null,
  endpoint_shared: false,
  last_seen_at: '2026-08-22T10:00:00Z',
  ...overrides,
});

describe('visiblePrinterConnections', () => {
  it('does not hide a conflicted connection behind an old disclosed address', () => {
    const result = visiblePrinterConnections([
      binding({ status: 'conflict', connection_ref: 'current' }),
      binding({ status: 'bound', display_endpoint: 'old.local:5000' }),
    ]);
    expect(result).toHaveLength(2);
    expect(result.some((item) => item.status === 'conflict')).toBe(true);
  });
  it('shows the disclosed endpoint instead of duplicate local-only labels', () => {
    const result = visiblePrinterConnections([
      binding({ connection_ref: 'local-a' }),
      binding({ connection_ref: 'local-b', last_seen_at: '2026-08-22T10:01:00Z' }),
      binding({
        connection_ref: null,
        display_endpoint: '192.168.31.200:5000',
        endpoint_shared: true,
        last_seen_at: '2026-08-08T10:00:00Z',
      }),
    ]);

    expect(result).toHaveLength(1);
    expect(result[0].display_endpoint).toBe('192.168.31.200:5000');
    expect(result[0].last_seen_at).toBe('2026-08-22T10:01:00Z');
  });

  it('keeps one newest fallback when the endpoint stays local', () => {
    const result = visiblePrinterConnections([
      binding({ connection_ref: 'older', last_seen_at: '2026-08-22T09:00:00Z' }),
      binding({ connection_ref: 'newer', last_seen_at: '2026-08-22T10:00:00Z' }),
    ]);

    expect(result).toHaveLength(1);
    expect(result[0].connection_ref).toBe('newer');
  });

  it('preserves distinct providers and disclosed endpoints', () => {
    const result = visiblePrinterConnections([
      binding({ display_endpoint: 'octo-one.local:5000' }),
      binding({ display_endpoint: 'octo-two.local:5000', connection_ref: 'octo-two' }),
      binding({ provider: 'moonraker', display_endpoint: 'voron.local:7125' }),
    ]);

    expect(result.map((item) => `${item.provider}:${item.display_endpoint}`)).toEqual([
      'octoprint:octo-one.local:5000',
      'octoprint:octo-two.local:5000',
      'moonraker:voron.local:7125',
    ]);
  });

  it('keeps the newest copy of the same disclosed endpoint', () => {
    const result = visiblePrinterConnections([
      binding({ display_endpoint: 'Printer.Local:5000', last_seen_at: '2026-08-22T09:00:00Z' }),
      binding({
        connection_ref: 'new-ref',
        display_endpoint: 'printer.local:5000',
        last_seen_at: '2026-08-22T10:00:00Z',
      }),
    ]);

    expect(result).toHaveLength(1);
    expect(result[0].connection_ref).toBe('new-ref');
  });
});
