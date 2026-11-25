import { describe, expect, it } from 'vitest';
import type { PhysicalPrinter } from '../api/client';
import { usageSetupProgress } from './printerUsageSetup';

const printer = (overrides: Record<string, unknown>) => ({
  id: 7,
  material_systems: [],
  connectors: [],
  contact_channels: [],
  ...overrides,
}) as unknown as PhysicalPrinter;

const slot = (spoolId: number | null) => ({
  assignment: spoolId == null ? null : { spool_id: spoolId },
  legacy_projection: null,
});

describe('usageSetupProgress', () => {
  it('stops at the slot when the bridge works but no spool is assigned', () => {
    const progress = usageSetupProgress(
      printer({
        material_systems: [{ active: true, provider: 'bambu', slots: [slot(null)] }],
        connectors: [{ active: true, transport: 'orca_plugin_lan', capabilities: ['consumption'] }],
        contact_channels: [{ kind: 'connector', last_contact_at: '2026-11-25T10:00:00Z' }],
      }),
      { has_spools: true, last_usage_at: {} },
    );
    expect(progress.current).toBe('slot');
    expect(progress.viaOrca).toBe(true);
  });

  it('does not count a watching helper as the link that deducts for Klipper', () => {
    // The plugin sees the printer, but only Moonraker itself reports usage.
    const progress = usageSetupProgress(
      printer({
        material_systems: [{ active: true, provider: 'happy_hare', slots: [slot(5)] }],
        connectors: [{ active: true, transport: 'orca_plugin_lan', capabilities: ['read'] }],
        contact_channels: [
          { kind: 'connector', last_contact_at: '2026-11-25T10:00:00Z' },
          { kind: 'native_spoolman', last_contact_at: null },
        ],
      }),
      { has_spools: true, last_usage_at: {} },
    );
    expect(progress.nativeOnly).toBe(true);
    expect(progress.current).toBe('connect');
    // Once Moonraker reports, the print does not depend on OrcaSlicer staying open.
    expect(progress.viaOrca).toBe(false);
  });

  it('counts the plugin as the link that deducts for Klipper once it reports consumption', () => {
    // No [spoolman] in Moonraker: the plugin counts the extruder's figure itself.
    const progress = usageSetupProgress(
      printer({
        material_systems: [{ active: true, provider: 'happy_hare', slots: [slot(5)] }],
        connectors: [
          { active: true, transport: 'orca_plugin_lan', capabilities: ['read', 'spool_identity'] },
          { active: true, transport: 'orca_plugin_lan', capabilities: ['read', 'consumption'] },
        ],
        contact_channels: [
          { kind: 'connector', last_contact_at: '2026-11-25T10:00:00Z' },
          { kind: 'native_spoolman', last_contact_at: null },
        ],
      }),
      { has_spools: true, last_usage_at: {} },
    );
    expect(progress.nativeOnly).toBe(false);
    expect(progress.current).toBe('print');
    expect(progress.viaOrca).toBe(true);
  });

  it('has nothing left to ask once a print was deducted', () => {
    const progress = usageSetupProgress(
      printer({
        material_systems: [{ active: true, provider: 'bambu', slots: [slot(5)] }],
        contact_channels: [{ kind: 'connector', last_contact_at: '2026-11-25T10:00:00Z' }],
      }),
      { has_spools: true, last_usage_at: { 7: '2026-11-25T11:00:00Z' } },
    );
    expect(progress.current).toBeNull();
  });
});
