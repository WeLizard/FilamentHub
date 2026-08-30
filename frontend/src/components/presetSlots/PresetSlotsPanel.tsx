import { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Cpu, Clock, Eraser, KeyRound, Layers, Trash2, Loader2, Wifi, WifiOff, AlertTriangle, Check, ChevronDown, Plus, Settings2 } from 'lucide-react';
import { devicesAPI, physicalPrintersAPI, presetsAPI, printerProfilesAPI, spoolsAPI } from '../../api/client';
import type {
  GateState,
  MaterialSlot,
  MaterialSystem,
  PhysicalPrinter,
  UserSpool,
} from '../../api/client';
import type { Preset } from '../../types/api';
import { ConfirmDeleteModal } from '../ConfirmDeleteModal';
import { feedAdapterFor } from './adapters';
import { AddPhysicalPrinterModal } from '../AddPhysicalPrinterModal';
import { PrinterSetupWizard } from '../PrinterSetupWizard';
import { GateMapGrid } from './GateMapGrid';
import { LinkInstructions } from './LinkInstructions';
import { removeBambuBridgeInPlugin } from '../../utils/pluginBridge';
import { PresetAssignModal } from './PresetAssignModal';
import { toast } from '../Toast';
import { translateApiError } from '../../utils/translateApiError';
import { formatLastSeen, getDeviceLinkState, latestDeviceContact, useNow } from '../../utils/deviceLink';
import { configuredNozzleHrc } from '../../utils/nozzleHardness';
import { useAuth } from '../../contexts/AuthContext';
import { safeStorage } from '../../utils/storage';

interface MaterialSystemSectionProps {
  printer: PhysicalPrinter;
  system: MaterialSystem;
  presetsSeedMap: Record<number, Pick<Preset, 'id' | 'name' | 'extruder_temp' | 'bed_temp'>>;
  spools: UserSpool[];
  spoolCompatBaseUrl: string;
  printerProfileName?: string | null;
  nozzleHrc?: number | null;
  onGateClick: (
    gate: GateState | null,
    slot: MaterialSlot,
    printer: PhysicalPrinter,
    system: MaterialSystem,
  ) => void;
}

// Names we generate ourselves are placeholders, not something a person typed.
const GENERATED_SYSTEM_NAMES = new Set([
  'Material system',
  'Happy Hare',
  'Legacy material system',
  'Direct feed',
]);

function gateSource(value: string | undefined): GateState['source'] {
  if (
    value === 'hh_snapshot'
    || value === 'manual_orca'
    || value === 'web_manual'
    || value === 'provider_report'
  ) {
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




function MaterialSystemSection({ printer, system, presetsSeedMap, spools, spoolCompatBaseUrl, printerProfileName = null, nozzleHrc = null, onGateClick }: MaterialSystemSectionProps) {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const adapter = feedAdapterFor(system.provider);
  const [clearing, setClearing] = useState(false);
  const [slotCountDraft, setSlotCountDraft] = useState('');
  const [editingSlots, setEditingSlots] = useState(false);
  const [savingSlotCount, setSavingSlotCount] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [issuedKey, setIssuedKey] = useState<string | null>(null);
  const [issuingKey, setIssuingKey] = useState(false);
  const [setupOpen, setSetupOpen] = useState(false);
  const canCollapse = adapter.alwaysCollapsible === true
    || system.kind === 'mmu'
    || adapter.topologyFromProvider === true
    || system.slots.filter((slot) => slot.active).length > 1;
  const collapseStorageKey = `filamenthub:material-system:collapsed:${user?.id ?? 'anonymous'}:${system.id}`;
  const [collapsed, setCollapsed] = useState(
    () => canCollapse && safeStorage.get(collapseStorageKey) === '1',
  );
  const now = useNow();
  const connector = printer.connectors.find(
    (item) => item.material_system_id === system.id && item.active,
  ) ?? null;
  // The key belongs to the printer, so a system without its own connector still
  // hears from it; falling back keeps a reporting printer from looking silent.
  const lastSeenAt = latestDeviceContact(connector?.last_seen_at, printer.last_seen_at);
  const linkState = getDeviceLinkState(lastSeenAt, now, adapter.contactMode);
  const linkConfirmed = printer.reports_feed;
  const providerLabel = t(`presetSlots.provider.${system.provider}`, {
    defaultValue: system.provider,
  });
  const systemLabel = GENERATED_SYSTEM_NAMES.has(system.name) ? providerLabel : system.name;
  const visibleSlots = useMemo(
    () => system.slots.filter((slot) => slot.active),
    [system.slots],
  );
  const compactCardLayout = visibleSlots.length <= 4;
  const gates = useMemo(
    () => visibleSlots.map(materialSlotGateState).filter((gate): gate is GateState => gate !== null),
    [visibleSlots],
  );

  const handleIssueKey = async () => {
    setIssuingKey(true);
    try {
      const { api_key } = await devicesAPI.regenerateKey(printer.id);
      setIssuedKey(api_key);
      setCollapsed(false);
      await queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
    } catch (err: any) {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    } finally {
      setIssuingKey(false);
    }
  };

  const toggleCollapsed = () => {
    if (!canCollapse) return;
    setCollapsed((current) => {
      const next = !current;
      safeStorage.set(collapseStorageKey, next ? '1' : '0');
      return next;
    });
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

  const handleConfirmSlotCount = async (slotCount: number) => {
    setSavingSlotCount(true);
    try {
      await physicalPrintersAPI.updateSystem(printer.id, system.id, { slot_count: slotCount });
      await queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
      setSlotCountDraft('');
      setEditingSlots(false);
    } catch (err: any) {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    } finally {
      setSavingSlotCount(false);
    }
  };

  const handleDeleteSystem = async () => {
    setDeleting(true);
    try {
      await physicalPrintersAPI.deleteSystem(printer.id, system.id);
      if (adapter.id === 'bambu') {
        removeBambuBridgeInPlugin(printer.id);
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['physical-printers'] }),
        queryClient.invalidateQueries({ queryKey: ['spools'] }),
        queryClient.invalidateQueries({ queryKey: ['user-spools'] }),
        queryClient.invalidateQueries({ queryKey: ['devices'] }),
      ]);
      toast.success(t('presetSlots.systemDeleted'));
    } catch (err: any) {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    } finally {
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  const handleClearAll = async () => {
    if (!window.confirm(t('presetSlots.clearAllConfirm', { name: systemLabel }))) return;
    setClearing(true);
    try {
      await physicalPrintersAPI.clearSystem(
        printer.id,
        system.id,
        system.slots.map((slot) => ({
          material_slot_id: slot.id,
          expected_revision: slot.assignment_revision,
          expected_spool_id: slot.assignment?.spool_id ?? null,
        })),
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['physical-printers'] }),
        queryClient.invalidateQueries({ queryKey: ['spools'] }),
        queryClient.invalidateQueries({ queryKey: ['user-spools'] }),
      ]);
      toast.success(t('presetSlots.cleared'));
    } catch (err: any) {
      if (err?.response?.status === 409) {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ['physical-printers'] }),
          queryClient.invalidateQueries({ queryKey: ['spools'] }),
          queryClient.invalidateQueries({ queryKey: ['user-spools'] }),
        ]);
      }
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className={`${collapsed ? '' : 'h-full'} rounded-2xl border border-white/10 bg-white/3 p-5`}>
      <div className={compactCardLayout
        ? `${collapsed ? '' : 'mb-4'} grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-3 gap-y-2`
        : `${collapsed ? '' : 'mb-4'} flex flex-wrap items-start justify-between gap-3 md:grid md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]`}>
        <div className="min-w-0 flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-purple-500/20">
            <Cpu className="h-5 w-5 text-purple-300" />
          </div>
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-white" title={printer.name}>
              {printer.name}
            </h2>
            <p className="mt-0.5 text-[11px] text-gray-400">{systemLabel}</p>
            {printerProfileName
              && !printer.name.includes(printerProfileName)
              && !printerProfileName.includes(printer.name) && (
              <p className="text-[11px] text-purple-300 mt-0.5">
                {t('presetSlots.mappedPrinter', { name: printerProfileName })}
              </p>
            )}
          </div>
        </div>

        <div className={compactCardLayout
          ? 'col-span-2 row-start-2 flex min-w-0 flex-col items-start gap-1.5'
          : 'flex min-w-0 flex-col items-start gap-1.5 md:items-center md:justify-self-center'}>
          <div className="flex flex-wrap items-center gap-1.5 md:justify-center">
            <span
              title={t(linkState === 'ready' ? 'deviceLink.onDemandTooltip' : 'deviceLink.tooltip')}
              className={[
                'flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium',
                adapter.topologyFromProvider && visibleSlots.length === 0
                  ? 'bg-amber-500/15 text-amber-300'
                  : linkState === 'active' || linkState === 'ready'
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
              ) : linkState === 'ready' ? (
                <Check className="h-3 w-3" />
              ) : linkState === 'delayed' ? (
                <AlertTriangle className="h-3 w-3" />
              ) : linkState === 'inactive' ? (
                <WifiOff className="h-3 w-3" />
              ) : (
                <Clock className="h-3 w-3" />
              )}
              {t(adapter.topologyFromProvider && visibleSlots.length === 0
                ? 'printerConnections.awaitingTopology'
                : !lastSeenAt && visibleSlots.length > 0 ? 'printerSetup.manualTracking' : `deviceLink.${linkState}`)}
            </span>
            {adapter.onboarding && visibleSlots.length > 0 ? (
              <button type="button" onClick={() => setSetupOpen(true)} title={t('printerSetup.feed.edit')}
                className="rounded-full bg-white/5 px-2 py-0.5 text-[11px] text-gray-400 hover:text-white">
                {t(adapter.slotCountSummaryKey ?? 'presetSlots.gates', { count: visibleSlots.length })}
              </button>
            ) : !adapter.topologyFromProvider && editingSlots ? (
              <span className="flex items-center gap-1">
                <input
                  type="number"
                  min={1}
                  max={256}
                  value={slotCountDraft}
                  onChange={(e) => setSlotCountDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') void handleConfirmSlotCount(Number(slotCountDraft)); }}
                  autoFocus
                  className="w-16 rounded border border-white/20 bg-black/30 px-1.5 py-0.5 text-[11px] text-white focus:border-purple-500 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => handleConfirmSlotCount(Number(slotCountDraft))}
                  disabled={savingSlotCount || !Number.isInteger(Number(slotCountDraft))
                    || Number(slotCountDraft) < 1 || Number(slotCountDraft) > 256}
                  className="text-[11px] text-purple-300 hover:text-purple-200 disabled:opacity-40"
                >
                  {savingSlotCount ? '…' : t('common.save')}
                </button>
              </span>
            ) : adapter.topologyFromProvider && visibleSlots.length > 0 ? (
              <span className="rounded-full bg-white/5 px-2 py-0.5 text-[11px] text-gray-400">
                {t(adapter.slotCountSummaryKey ?? 'presetSlots.gates', {
                  count: visibleSlots.length,
                })}
              </span>
            ) : !adapter.topologyFromProvider ? (
              <button
                type="button"
                onClick={() => {
                  setSlotCountDraft(String(visibleSlots.length));
                  setEditingSlots(true);
                }}
                title={t('presetSlots.slotCount.change')}
                className="rounded-full bg-white/5 px-2 py-0.5 text-[11px] text-gray-400 transition hover:bg-white/10 hover:text-white"
              >
                {t(adapter.slotCountSummaryKey ?? 'presetSlots.gates', {
                  count: visibleSlots.length,
                })}
              </button>
            ) : null}
            {lastSeenAt && (
              <span className="rounded-full bg-white/5 px-2 py-0.5 text-[11px] text-gray-500">
                {formatLastSeen(lastSeenAt, t, i18n.language, now)}
              </span>
            )}
          </div>

          {!adapter.link ? null : (
            <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-gray-400 md:justify-center">
              <span className="flex items-center gap-1">
                {!printer.has_api_key ? (
                  <>
                    <AlertTriangle className="h-3 w-3 text-amber-400" />
                    {t('presetSlots.link.notSet')}
                  </>
                ) : !linkConfirmed ? (
                  <>
                    <Clock className="h-3 w-3 text-gray-400" />
                    {t('presetSlots.link.waiting')}
                  </>
                ) : (
                  <>
                    <Check className="h-3 w-3 text-emerald-400" />
                    {t('presetSlots.link.label')}
                  </>
                )}
              </span>
              {adapter.renderSettings?.({ printer, system, gates, spools, linkConfirmed })}
              <button
                type="button"
                onClick={handleIssueKey}
                disabled={issuingKey}
                className="flex items-center gap-1 rounded px-1 py-0.5 text-gray-400 transition hover:bg-white/10 hover:text-white disabled:opacity-40"
              >
                {issuingKey ? <Loader2 className="h-3 w-3 animate-spin" /> : <KeyRound className="h-3 w-3" />}
                {t(printer.has_api_key ? 'presetSlots.link.reissue' : 'presetSlots.link.issue')}
              </button>
            </div>
          )}
          {!adapter.link && adapter.renderSettings?.({ printer, system, gates, spools, linkConfirmed })}
        </div>

        <div className={compactCardLayout
          ? 'col-start-2 row-start-1 flex flex-wrap items-center gap-2 justify-self-end'
          : 'flex flex-wrap items-center gap-2 md:justify-self-end'}>
          {canCollapse && (
            <button
              type="button"
              onClick={toggleCollapsed}
              aria-expanded={!collapsed}
              title={t(collapsed ? 'presetSlots.expandSystem' : 'presetSlots.collapseSystem')}
              className="rounded-lg border border-white/10 bg-white/5 p-1.5 text-gray-400 transition hover:bg-white/10 hover:text-white"
            >
              <ChevronDown className={`h-3.5 w-3.5 transition-transform ${collapsed ? '' : 'rotate-180'}`} />
            </button>
          )}
          {adapter.renderActions?.({ printer, system, gates, spools, linkConfirmed })}
          <button type="button" onClick={() => setSetupOpen(true)}
            aria-label={t('printerSetup.connectionSettings')}
            className="rounded-lg border border-white/10 bg-white/5 p-1.5 text-gray-400 hover:text-white">
            <Settings2 className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={handleClearAll}
            disabled={clearing || gates.every((g) => !g.preset_id && !g.spool_id)}
            title={t('presetSlots.clearAll')}
            className="rounded-lg border border-white/10 bg-white/5 p-1.5 text-gray-400 transition hover:bg-white/10 hover:text-red-300 disabled:opacity-40"
          >
            {clearing ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Eraser className="h-3.5 w-3.5" />
            )}
          </button>
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            disabled={deleting}
            title={t('presetSlots.deleteSystem')}
            className="rounded-lg border border-white/10 bg-white/5 p-1.5 text-gray-400 transition hover:bg-white/10 hover:text-red-300 disabled:opacity-40"
          >
            {deleting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Trash2 className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>

      <ConfirmDeleteModal
        isOpen={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        onConfirm={handleDeleteSystem}
        isLoading={deleting}
        title={t('presetSlots.deleteSystem')}
        confirmText={t('presetSlots.deleteSystem')}
        message={t('presetSlots.deleteSystemConfirm', { name: systemLabel })}
      />
      {setupOpen && <PrinterSetupWizard physicalPrinter={printer} onClose={() => setSetupOpen(false)} />}

      {!collapsed && adapter.renderSetup?.({ printer, system, gates, spools, linkConfirmed })}

      {!collapsed && issuedKey && adapter.link && !linkConfirmed && (
        <div className="mb-4 rounded-xl border border-white/10 bg-white/5 p-4">
          <LinkInstructions
            link={adapter.link}
            baseUrl={spoolCompatBaseUrl}
            apiKey={issuedKey}
            onClose={() => setIssuedKey(null)}
          />
        </div>
      )}

      {!collapsed && !adapter.topologyFromProvider && !adapter.onboarding
        && system.declared_slot_count == null
        && visibleSlots.length > 0 && (
        <div className="mb-4 rounded-xl border border-white/10 bg-white/5 p-4">
          <p className="text-sm text-white">
            {t('presetSlots.slotCount.question', { count: visibleSlots.length })}
          </p>
          <p className="mt-1 text-xs text-gray-400">{t('presetSlots.slotCount.hint')}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => handleConfirmSlotCount(visibleSlots.length)}
              disabled={savingSlotCount}
              className="inline-flex items-center gap-1.5 rounded-lg bg-purple-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-purple-500 disabled:opacity-50"
            >
              {savingSlotCount && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {t('presetSlots.slotCount.confirm')}
            </button>
            <input
              type="number"
              min={1}
              max={256}
              value={slotCountDraft}
              onChange={(e) => setSlotCountDraft(e.target.value)}
              placeholder={t('presetSlots.slotCount.placeholder')}
              className="w-28 rounded-lg border border-white/15 bg-black/30 px-2 py-1.5 text-xs text-white placeholder-gray-600 focus:border-purple-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => handleConfirmSlotCount(Number(slotCountDraft))}
              disabled={
                savingSlotCount
                || !Number.isInteger(Number(slotCountDraft))
                || Number(slotCountDraft) < 1
                || Number(slotCountDraft) > 256
              }
              className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-gray-200 transition hover:bg-white/10 disabled:opacity-40"
            >
              {t('presetSlots.slotCount.save')}
            </button>
          </div>
        </div>
      )}

      {!collapsed && (
        <GateMapGrid
          slots={visibleSlots}
          gates={gates}
          presets={effectivePresetsMap}
          spools={spools}
          nozzleHrc={nozzleHrc}
          onGateClick={(gate, slot) => onGateClick(gate, slot, printer, system)}
        />
      )}
    </div>
  );
}

interface PresetSlotsPanelProps {
  compact?: boolean;
  spools?: UserSpool[];
  printerProfiles?: Array<{ id: number; name: string }>;
}

export function shouldPollForAdapterContact(printers: PhysicalPrinter[]): boolean {
  return printers.some(
    (printer) => printer.has_api_key
      && printer.material_systems.some((system) => system.active)
      && !printer.reports_feed,
  );
}

const ADAPTER_CONTACT_POLL_WINDOW_MS = 60_000;
const ADAPTER_CONTACT_POLL_INTERVAL_MIN_MS = 15_000;
const ADAPTER_CONTACT_POLL_INTERVAL_RANGE_MS = 10_000;

export function adapterContactPollIntervalMs(randomValue = Math.random()): number {
  const boundedRandomValue = Math.min(Math.max(randomValue, 0), 1);
  return ADAPTER_CONTACT_POLL_INTERVAL_MIN_MS
    + Math.floor(boundedRandomValue * ADAPTER_CONTACT_POLL_INTERVAL_RANGE_MS);
}

export function shouldContinueAdapterContactPolling(
  printers: PhysicalPrinter[],
  pollingUntilMs: number,
  nowMs = Date.now(),
): boolean {
  return nowMs < pollingUntilMs && shouldPollForAdapterContact(printers);
}

export function PresetSlotsPanel({
  compact = false,
  spools: externalSpools,
  printerProfiles,
}: PresetSlotsPanelProps) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const [modalState, setModalState] = useState<{
    open: boolean;
    gate: GateState | null;
    slot: MaterialSlot | null;
    printer: PhysicalPrinter | null;
    system: MaterialSystem | null;
  }>({ open: false, gate: null, slot: null, printer: null, system: null });
  const [addingSystem, setAddingSystem] = useState(false);
  const [adapterContactPollingUntil, setAdapterContactPollingUntil] = useState(
    () => Date.now() + ADAPTER_CONTACT_POLL_WINDOW_MS,
  );
  const [adapterContactPollInterval] = useState(
    () => adapterContactPollIntervalMs(),
  );

  const { data: physicalPrinters = [], isLoading: loadingPrinters } = useQuery({
    queryKey: ['physical-printers'],
    queryFn: physicalPrintersAPI.list,
    staleTime: 10_000,
    refetchOnWindowFocus: true,
    // Someone who just pasted the key sits and waits for the printer to answer;
    // they have no reason to guess that the page needs reloading.
    refetchInterval: (query) => {
      const printers = query.state.data ?? [];
      return shouldContinueAdapterContactPolling(
        printers,
        adapterContactPollingUntil,
      ) ? adapterContactPollInterval : false;
    },
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

  const { data: ownedProfiles } = useQuery({
    queryKey: ['printer-profiles', 'all-owned', user?.id],
    queryFn: () => printerProfilesAPI.listAllOwned(user!.id),
    enabled: !!user && physicalPrinters.length > 0,
  });

  const nozzleHrcByPrinterId = useMemo(() => {
    const settingsByProfileId = new Map<number, Record<string, unknown>>();
    for (const profile of ownedProfiles ?? []) {
      settingsByProfileId.set(profile.id, profile.orcaslicer_settings ?? {});
    }

    const map = new Map<number, number | null>();
    for (const printer of physicalPrinters) {
      const known = printer.printer_profile_ids
        .map((profileId) => configuredNozzleHrc(settingsByProfileId.get(profileId)))
        .filter((hrc): hrc is number => hrc != null);
      map.set(printer.id, known.length > 0 ? Math.max(...known) : null);
    }
    return map;
  }, [ownedProfiles, physicalPrinters]);

  const printerProfileNameById = useMemo(() => {
    const map = new Map<number, string>();
    for (const profile of ownedProfiles ?? []) {
      map.set(profile.id, profile.name);
    }
    for (const profile of printerProfiles ?? []) {
      map.set(profile.id, profile.name);
    }
    return map;
  }, [ownedProfiles, printerProfiles]);

  const materialSections = useMemo(
    () => physicalPrinters.flatMap((printer) =>
      printer.material_systems
        .filter((system) => system.active)
        .map((system) => ({ printer, system })),
    ),
    [physicalPrinters],
  );

  const presetsMap: Record<number, Pick<Preset, 'id' | 'name' | 'extruder_temp' | 'bed_temp'>> = {};
  (presetsPage?.items ?? []).forEach((preset) => {
    presetsMap[preset.id] = preset;
  });

  const spoolCompatBaseUrl = useMemo(() => {
    if (typeof window === 'undefined' || !window.location?.origin) {
      return 'https://filamenthub.ru/api/v1/spool_compat';
    }
    return `${window.location.origin}/api/v1/spool_compat`;
  }, []);

  const handleSystemAdded = () => {
    setAddingSystem(false);
    setAdapterContactPollingUntil(Date.now() + ADAPTER_CONTACT_POLL_WINDOW_MS);
    void queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
    void queryClient.invalidateQueries({ queryKey: ['devices'] });
  };

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

  const addButton = (
    <button
      type="button"
      onClick={() => setAddingSystem(true)}
      disabled={addingSystem}
      className="inline-flex items-center gap-1.5 rounded-xl bg-purple-600 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-purple-500 disabled:opacity-50"
    >
      <Plus className="h-4 w-4" />
      {t('printerSetup.title')}
    </button>
  );

  if (materialSections.length === 0 && !addingSystem) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 py-12 text-center">
        <Layers className="mb-4 h-12 w-12 text-gray-600" />
        <h2 className="mb-2 text-lg font-semibold text-white">{t('presetSlots.noSystems')}</h2>
        <p className="mb-4 max-w-sm text-sm text-gray-500">{t('presetSlots.noSystemsDesc')}</p>
        {addButton}
      </div>
    );
  }

  return (
    <>
      <div className={compact ? 'space-y-4' : 'space-y-6'}>
        <div className="flex justify-end">{addButton}</div>
        {addingSystem && (
          <AddPhysicalPrinterModal isOpen onClose={handleSystemAdded}
            printerProfiles={Array.from(printerProfileNameById, ([id, name]) => ({ id, name }))} />
        )}
        <div className="grid gap-4 xl:grid-cols-2">
          {materialSections.map(({ printer, system }) => {
            const activeSlotCount = system.slots.filter((slot) => slot.active).length;
            return (
              <div
                key={system.id}
                className={activeSlotCount > 4 ? 'xl:col-span-2' : undefined}
              >
                <MaterialSystemSection
                  printer={printer}
                  system={system}
                  presetsSeedMap={presetsMap}
                  spools={spools}
                  spoolCompatBaseUrl={spoolCompatBaseUrl}
                  printerProfileName={printer.printer_profile_ids
                    .map((profileId) => printerProfileNameById.get(profileId))
                    .filter((name): name is string => name != null)
                    .join(', ') || null}
                  nozzleHrc={nozzleHrcByPrinterId.get(printer.id) ?? null}
                  onGateClick={handleGateClick}
                />
              </div>
            );
          })}
        </div>
      </div>

      {modalState.printer && modalState.system && modalState.slot && (
        <PresetAssignModal
          isOpen={modalState.open}
          gateIndex={modalState.slot.provider_index}
          gate={modalState.gate}
          slotKind={modalState.slot.kind}
          slotLabel={modalState.slot.label}
          slotObservation={modalState.slot.observation}
          physicalPrinterId={modalState.printer.id}
          materialSlotId={modalState.slot.id}
          assignmentRevision={modalState.slot.assignment_revision}
          expectedSpoolId={modalState.slot.assignment?.spool_id
            ?? modalState.slot.legacy_projection?.spool_id
            ?? null}
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
