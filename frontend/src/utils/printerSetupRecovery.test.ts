import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PendingPrinterSetup } from './printerSetupRecovery';

const intent: PendingPrinterSetup = {
  targetId: 0, probe: null, route: 'edge',
  payload: { name: 'Workshop', request_id: '67c89b41-510d-4f52-ab77-fc7bb9dc9411',
    printer_profile_ids: [], material_system: { name: 'Direct', provider: 'manual',
      kind: 'direct_feed', capabilities: [], slot_count: 1 } },
};

describe('printer setup recovery', () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
    window.history.replaceState({ usr: { filter: 'printers' }, key: 'router-key', idx: 3 }, '');
  });
  afterEach(() => vi.restoreAllMocks());

  it('recovers the exact request after page memory is discarded with storage denied', async () => {
    vi.spyOn(window, 'localStorage', 'get').mockImplementation(() => {
      throw new DOMException('Blocked', 'SecurityError');
    });
    const before = window.history.state;
    const url = window.location.href;
    const firstPage = await import('./printerSetupRecovery');
    expect(firstPage.persistPrinterSetupIntent(1, intent)).toBe(true);
    expect(window.history.state).toMatchObject(before);
    expect(window.location.href).toBe(url);
    vi.resetModules(); // A reload loses the safeStorage memory fallback.
    const reloadedPage = await import('./printerSetupRecovery');
    expect(reloadedPage.readPrinterSetupIntent(1)).toEqual(intent);
    expect(reloadedPage.readPrinterSetupIntent(2)).toBeNull();
    reloadedPage.clearPrinterSetupIntent(2, intent.payload.request_id);
    expect(reloadedPage.readPrinterSetupIntent(1)).toEqual(intent);
    reloadedPage.clearPrinterSetupIntent(1, intent.payload.request_id);
    expect(reloadedPage.readPrinterSetupIntent(1)).toBeNull();
    expect(window.history.state).toEqual(before);
  });

  it('does not let acknowledgement in one tab remove another tab’s pending request', async () => {
    const recovery = await import('./printerSetupRecovery');
    recovery.persistPrinterSetupIntent(1, intent);
    const other = { ...intent, payload: { ...intent.payload,
      request_id: '6b993c61-0280-4e92-be2b-f0a2b1f72335', name: 'Another printer' } };
    localStorage.setItem('fh-printer-setup-1', JSON.stringify(other));
    expect(recovery.readPrinterSetupIntent(1)).toEqual(intent);
    recovery.clearPrinterSetupIntent(1, intent.payload.request_id);
    expect(JSON.parse(localStorage.getItem('fh-printer-setup-1')!)).toEqual(other);
    expect(window.history.state.fhPrinterSetup).toBeUndefined();
  });
});
