import { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Cpu, Clock, Layers, Zap, Trash2, Loader2, Wifi, WifiOff, AlertTriangle, Copy, Check, RefreshCw } from 'lucide-react';
import { physicalPrintersAPI, presetsAPI, spoolsAPI } from '../../api/client';
import type { GateState, MaterialSlot, MaterialSystem, PhysicalPrinter, UserSpool } from '../../api/client';
import type { Preset } from '../../types/api';
import { GateMapGrid } from './GateMapGrid';
import { PresetAssignModal } from './PresetAssignModal';
import { toast } from '../Toast';
import { translateApiError } from '../../utils/translateApiError';
import { formatLastSeen, getDeviceLinkState, useNow } from '../../utils/deviceLink';
import { useAuth } from '../../contexts/AuthContext';

interface MaterialSystemSectionProps {
  printer: PhysicalPrinter;
  system: MaterialSystem;
  presetsSeedMap: Record<number, Pick<Preset, 'id' | 'name' | 'extruder_temp' | 'bed_temp'>>;
  spools: UserSpool[];
  printerProfileName?: string | null;
  onGateClick: (
    gate: GateState | null,
    slot: MaterialSlot,
    printer: PhysicalPrinter,
    system: MaterialSystem,
  ) => void;
}

function gateSource(value: string | undefined): GateState['source'] {
  if (value === 'hh_snapshot' || value === 'manual_orca' || value === 'web_manual') {
    return value;
  }
  return 'web_manual';
}

function materialSlotGateState(slot: MaterialSlot): GateState | null {
  const assignment = slot.assignment;
  const projection = slot.legacy_projection;
  if (!assignment && !projection) return null;
  return {
    id: projection?.gate_state_id ?? assignment!.id,
    gate_index: slot.provider_index,
    preset_id: assignment?.preset_id ?? projection?.preset_id ?? null,
    spool_id: assignment?.spool_id ?? projection?.spool_id ?? null,
    hh_material: projection?.hh_material ?? null,
    hh_color_hex: projection?.hh_color_hex ?? null,
    hh_status: projection?.hh_status ?? null,
    source: gateSource(assignment?.source ?? projection?.source),
    source_ts: assignment?.source_ts ?? projection!.source_ts,
    is_active: assignment?.active ?? projection?.is_active ?? true,
    updated_at: projection?.updated_at ?? assignment!.source_ts,
  };
}

function MaterialSystemSection({ printer, system, presetsSeedMap, spools, printerProfileName = null, onGateClick }: MaterialSystemSectionProps) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [clearing, setClearing] = useState(false);
  const [pairingCommandCopied, setPairingCommandCopied] = useState(false);
  const now = useNow();
  const connector = printer.connectors.find(
    (item) => item.material_system_id === system.id && item.active,
  ) ?? null;
  const linkState = getDeviceLinkState(connector?.last_seen_at ?? null, now);
  const isHappyHare = system.provider === 'happy_hare';
  const gates = useMemo(
    () => system.slots.map(materialSlotGateState).filter((gate): gate is GateState => gate !== null),
    [system.slots],
  );

  const pairingGate = useMemo(
    () => gates.find((gate) => gate.spool_id != null) ?? null,
    [gates],
  );
  const pairingCommand = pairingGate?.spool_id != null
    ? `MMU_SPOOLMAN GATE=${pairingGate.gate_index} SPOOLID=${pairingGate.spool_id}`
    : null;

  const handleCopyPairingCommand = async () => {
    if (!pairingCommand) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(pairingCommand);
      } else {
        const textarea = document.createElement('textarea');
        textarea.value = pairingCommand;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        document.execCommand('copy');
        textarea.remove();
      }
      setPairingCommandCopied(true);
      window.setTimeout(() => setPairingCommandCopied(false), 1800);
    } catch {
      toast.error(t('common.error'));
    }
  };

  const handleCheckPairing = async () => {
    await queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
  };

  const missingPresetIds = useMemo(() => {
    const ids = new Set<number>();
    for (const gate of gates) {
      if (gate.preset_id != null && !presetsSeedMap[gate.preset_id]) {
        ids.add(gate.preset_id);
      }
    }
    return Array.from(ids).sort((a, b) => a - b);
  }, [gates, presetsSeedMap]);

  const { data: missingPresets = [] } = useQuery({
    queryKey: ['material-slot-missing-presets', system.id, missingPresetIds],
    queryFn: async () => {
      const results = await Promise.all(
        missingPresetIds.map(async (presetId) => {
          try {
            return await presetsAPI.get(presetId);
          } catch {
            return null;
          }
        }),
      );
      return results.filter((preset): preset is Preset => preset !== null);
    },
    enabled: missingPresetIds.length > 0,
    staleTime: 60_000,
  });

  const effectivePresetsMap = useMemo(() => {
    const map = { ...presetsSeedMap };
    for (const preset of missingPresets) {
      map[preset.id] = {
        id: preset.id,
        name: preset.name,
        extruder_temp: preset.extruder_temp,
        bed_temp: preset.bed_temp,
      };
    }
    return map;
  }, [missingPresets, presetsSeedMap]);

  const handleClearAll = async () => {
    if (!window.confirm(t('presetSlots.clearAllConfirm', { name: system.name }))) return;
    setClearing(true);
    try {
      await physicalPrintersAPI.clearSystem(printer.id, system.id);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['physical-printers'] }),
        queryClient.invalidateQueries({ queryKey: ['spools'] }),
      ]);
      toast.success(t('presetSlots.cleared'));
    } catch (err: any) {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="rounded-2xl border border-white/10 bg-white/3 p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-500/20">
            <Cpu className="h-5 w-5 text-purple-300" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-white">{printer.name}</h2>
            <p className="mt-0.5 text-[11px] text-gray-400">{system.name}</p>
            {printerProfileName && (
              <p className="text-[11px] text-purple-300 mt-0.5">
                {t('presetSlots.mappedPrinter', { name: printerProfileName })}
              </p>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span
            title={t('deviceLink.tooltip')}
            className={[
              'flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium',
              linkState === 'active'
                ? 'bg-emerald-500/15 text-emerald-300'
                : linkState === 'delayed'
                  ? 'bg-amber-500/15 text-amber-300'
                  : linkState === 'inactive'
                    ? 'bg-white/10 text-gray-400'
                    : 'bg-white/5 text-gray-500',
            ].join(' ')}
          >
            {linkState === 'active' ? (
              <Wifi className="h-3 w-3" />
            ) : linkState === 'delayed' ? (
              <AlertTriangle className="h-3 w-3" />
            ) : linkState === 'inactive' ? (
              <WifiOff className="h-3 w-3" />
            ) : (
              <Clock className="h-3 w-3" />
            )}
            {t(`deviceLink.${linkState}`)}
          </span>

          {isHappyHare ? (
            <span className="flex items-center gap-1 rounded-full bg-green-500/15 px-2.5 py-1 text-xs font-medium text-green-400">
              <Zap className="h-3 w-3" />
              {t('presetSlots.hhActive')}
            </span>
          ) : (
            <span className="flex items-center gap-1 rounded-full bg-blue-500/15 px-2.5 py-1 text-xs font-medium text-blue-300">
              <Layers className="h-3 w-3" />
              {system.provider === 'manual' ? t('presetSlots.manualMode') : system.provider}
            </span>
          )}
          <span className="flex items-center gap-1 rounded-full bg-white/5 px-2.5 py-1 text-xs text-gray-400">
            <Layers className="h-3 w-3" />
            {t('presetSlots.gates', { count: system.slots.length })}
          </span>
          <span className="flex items-center gap-1 rounded-full bg-white/5 px-2.5 py-1 text-xs text-gray-500">
            <Clock className="h-3 w-3" />
            {formatLastSeen(connector?.last_seen_at ?? null, t, i18n.language, now)}
          </span>
          <button
            type="button"
            onClick={handleClearAll}
            disabled={clearing || gates.every((g) => !g.preset_id && !g.spool_id)}
            className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-red-400 transition hover:bg-red-500/10 disabled:opacity-40"
          >
            {clearing ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Trash2 className="h-3.5 w-3.5" />
            )}
            {t('presetSlots.clearAll')}
          </button>
        </div>
      </div>

      {isHappyHare && connector?.last_seen_at == null && (
        <div className="mb-4 rounded-xl border border-amber-400/25 bg-amber-500/10 p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-amber-100">{t('presetSlots.pairing.title')}</p>
              <p className="mt-1 text-xs leading-relaxed text-amber-100/75">
                {t('presetSlots.pairing.description')}
              </p>
              {pairingCommand ? (
                <>
                  <p className="mt-3 text-[11px] font-medium uppercase tracking-wide text-amber-200/70">
                    {t('presetSlots.pairing.commandLabel')}
                  </p>
                  <code className="mt-1 block overflow-x-auto rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-xs text-white">
                    {pairingCommand}
                  </code>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={handleCopyPairingCommand}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-amber-400 px-3 py-1.5 text-xs font-medium text-black transition hover:bg-amber-300"
                    >
                      {pairingCommandCopied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                      {t(pairingCommandCopied ? 'presetSlots.pairing.copied' : 'presetSlots.pairing.copy')}
                    </button>
                    <button
                      type="button"
                      onClick={handleCheckPairing}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-amber-300/25 bg-white/5 px-3 py-1.5 text-xs text-amber-100 transition hover:bg-white/10"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      {t('presetSlots.pairing.check')}
                    </button>
                  </div>
                </>
              ) : (
                <p className="mt-3 text-xs text-amber-200/80">{t('presetSlots.pairing.waitingForSpool')}</p>
              )}
            </div>
          </div>
        </div>
      )}

      <GateMapGrid
        slots={system.slots}
        gates={gates}
        presets={effectivePresetsMap}
        spools={spools}
        onGateClick={(gate, slot) => onGateClick(gate, slot, printer, system)}
      />
    </div>
  );
}

interface PresetSlotsPanelProps {
  compact?: boolean;
  spools?: UserSpool[];
  printerBindings?: Array<{ id: number; name: string }>;
}

export function PresetSlotsPanel({
  compact = false,
  spools: externalSpools,
  printerBindings,
}: PresetSlotsPanelProps) {
  const { t } = useTranslation();
  const { user } = useAuth();

  const [modalState, setModalState] = useState<{
    open: boolean;
    gate: GateState | null;
    slot: MaterialSlot | null;
    printer: PhysicalPrinter | null;
    system: MaterialSystem | null;
  }>({ open: false, gate: null, slot: null, printer: null, system: null });

  const { data: physicalPrinters = [], isLoading: loadingPrinters } = useQuery({
    queryKey: ['physical-printers'],
    queryFn: physicalPrintersAPI.list,
    staleTime: 60_000,
  });

  const { data: presetsPage } = useQuery({
    queryKey: ['presets', { page: 1, size: 100, userId: user?.id }],
    queryFn: () => presetsAPI.list({ page: 1, size: 100, user_id: user?.id }),
    staleTime: 60_000,
    enabled: physicalPrinters.length > 0 && !!user,
  });

  const shouldFetchSpools = externalSpools == null;
  const { data: fetchedSpools = [] } = useQuery({
    queryKey: ['spools'],
    queryFn: spoolsAPI.list,
    staleTime: 60_000,
    enabled: physicalPrinters.length > 0 && shouldFetchSpools,
  });

  const spools = externalSpools ?? fetchedSpools;

  const printerNameById = useMemo(() => {
    const map = new Map<number, string>();
    for (const binding of printerBindings ?? []) {
      map.set(binding.id, binding.name);
    }
    return map;
  }, [printerBindings]);

  const filteredPrinters = useMemo(() => {
    if (!printerBindings || printerBindings.length === 0) {
      return physicalPrinters;
    }
    return physicalPrinters.filter(
      (printer) => printer.material_systems.some((system) => system.provider === 'happy_hare') ||
      (printer.printer_id != null && printerNameById.has(printer.printer_id))
    );
  }, [physicalPrinters, printerBindings, printerNameById]);

  const materialSections = useMemo(
    () => filteredPrinters.flatMap((printer) =>
      printer.material_systems
        .filter((system) => system.active)
        .map((system) => ({ printer, system })),
    ),
    [filteredPrinters],
  );

  const presetsMap: Record<number, Pick<Preset, 'id' | 'name' | 'extruder_temp' | 'bed_temp'>> = {};
  (presetsPage?.items ?? []).forEach((preset) => {
    presetsMap[preset.id] = preset;
  });

  const handleGateClick = (
    gate: GateState | null,
    slot: MaterialSlot,
    printer: PhysicalPrinter,
    system: MaterialSystem,
  ) => {
    setModalState({ open: true, gate, slot, printer, system });
  };

  if (loadingPrinters) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader2 className="h-8 w-8 animate-spin text-purple-400" />
      </div>
    );
  }

  if (physicalPrinters.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 py-12 text-center">
        <Cpu className="mb-4 h-12 w-12 text-gray-600" />
        <h2 className="mb-2 text-lg font-semibold text-white">{t('presetSlots.noDevices')}</h2>
        <p className="max-w-sm text-sm text-gray-500">{t('presetSlots.noDevicesDesc')}</p>
      </div>
    );
  }

  if (filteredPrinters.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 py-12 text-center">
        <Cpu className="mb-4 h-12 w-12 text-gray-600" />
        <h2 className="mb-2 text-lg font-semibold text-white">{t('presetSlots.noMappedDevices')}</h2>
        <p className="max-w-sm text-sm text-gray-500">{t('presetSlots.noMappedDevicesDesc')}</p>
      </div>
    );
  }

  if (materialSections.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 py-12 text-center">
        <Layers className="mb-4 h-12 w-12 text-gray-600" />
        <h2 className="mb-2 text-lg font-semibold text-white">{t('presetSlots.noMaterialSystems')}</h2>
        <p className="max-w-sm text-sm text-gray-500">{t('presetSlots.noMaterialSystemsDesc')}</p>
      </div>
    );
  }

  return (
    <>
      <div className={compact ? 'space-y-4' : 'space-y-6'}>
        {materialSections.map(({ printer, system }) => (
          <MaterialSystemSection
            key={system.id}
            printer={printer}
            system={system}
            presetsSeedMap={presetsMap}
            spools={spools}
            printerProfileName={printer.printer_id != null ? (printerNameById.get(printer.printer_id) ?? null) : null}
            onGateClick={handleGateClick}
          />
        ))}
      </div>

      {modalState.printer && modalState.system && modalState.slot && (
        <PresetAssignModal
          isOpen={modalState.open}
          gateIndex={modalState.slot.provider_index}
          gate={modalState.gate}
          physicalPrinterId={modalState.printer.id}
          materialSlotId={modalState.slot.id}
          deviceName={modalState.printer.name}
          systemName={modalState.system.name}
          provider={modalState.system.provider}
          spools={spools}
          onClose={() => setModalState((s) => ({ ...s, open: false }))}
          onAssigned={() => setModalState((s) => ({ ...s, open: false }))}
        />
      )}
    </>
  );
}
