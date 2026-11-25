import type { PhysicalPrinter, PrinterUsageSetup as UsageSetup } from '../api/client';

const NATIVE_PROVIDERS = new Set(['happy_hare', 'legacy']);
export const USAGE_SETUP_STEPS = ['connect', 'spools', 'slot', 'print'] as const;
type Step = (typeof USAGE_SETUP_STEPS)[number];

/** Which of the steps towards automatic filament accounting this printer has passed. */
export function usageSetupProgress(printer: PhysicalPrinter, setup: UsageSetup) {
  const systems = printer.material_systems.filter(
    (system) => system.active && system.provider !== 'manual',
  );
  const channels = printer.contact_channels ?? [];
  const connectors = printer.connectors.filter((connector) => connector.active);
  // A helper deducts only when it says so. For Klipper the plugin and Edge count
  // the extruder's own figure unless Moonraker reports usage itself; a helper
  // that only watches the printer is not a way to deduct.
  const deducting = connectors.filter((connector) => connector.capabilities.includes('consumption'));
  const nativeOnly = systems.length > 0
    && systems.every((system) => NATIVE_PROVIDERS.has(system.provider))
    && deducting.length === 0;
  const connected = nativeOnly
    ? channels.some((channel) => channel.kind === 'native_spoolman' && channel.last_contact_at != null)
    : channels.some((channel) => channel.last_contact_at != null);
  const done: Record<Step, boolean> = {
    connect: connected,
    spools: setup.has_spools,
    slot: systems.some((system) => system.slots.some(
      (slot) => (slot.assignment?.spool_id ?? slot.legacy_projection?.spool_id) != null,
    )),
    print: setup.last_usage_at[printer.id] != null,
  };
  return {
    applicable: systems.length > 0,
    done,
    current: USAGE_SETUP_STEPS.find((step) => !done[step]) ?? null,
    nativeOnly,
    // Only when OrcaSlicer is the sole helper that deducts does it have to stay open.
    viaOrca: deducting.length > 0
      && deducting.every((connector) => connector.transport === 'orca_plugin_lan'),
  };
}
