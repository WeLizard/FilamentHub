import { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Cpu, Clock, Layers, Zap, Trash2, Loader2, Wifi, WifiOff, AlertTriangle, Settings2 } from 'lucide-react';
import { devicesAPI, presetSlotsAPI, presetsAPI, spoolsAPI } from '../../api/client';
import type { GateState, UserPrinterDevice, UserSpool } from '../../api/client';
import type { Preset } from '../../types/api';
import { GateMapGrid } from './GateMapGrid';
import { PresetAssignModal } from './PresetAssignModal';
import { toast } from '../Toast';
import { translateApiError } from '../../utils/translateApiError';
import { useAuth } from '../../contexts/AuthContext';

function formatLastSeen(
  ts: string | null,
  t: (key: string, options?: Record<string, unknown>) => string,
  locale: string,
): string {
  if (!ts) return t('presetSlots.neverSeen');
  const d = new Date(ts);
  const diff = Date.now() - d.getTime();
  if (diff < 60_000) return t('presetSlots.time.ltMinute');
  if (diff < 3_600_000) return t('presetSlots.time.minutesAgo', { count: Math.floor(diff / 60_000) });
  if (diff < 86_400_000) return t('presetSlots.time.hoursAgo', { count: Math.floor(diff / 3_600_000) });
  return d.toLocaleDateString(locale);
}

type DeviceConnectionState = 'online' | 'stale' | 'offline' | 'unknown';

function getDeviceConnectionState(ts: string | null): DeviceConnectionState {
  if (!ts) return 'unknown';
  const diff = Date.now() - new Date(ts).getTime();
  if (diff < 30_000) return 'online';
  if (diff < 180_000) return 'stale';
  return 'offline';
}

interface DeviceSectionProps {
  device: UserPrinterDevice;
  presetsSeedMap: Record<number, Pick<Preset, 'id' | 'name' | 'extruder_temp' | 'bed_temp'>>;
  spools: UserSpool[];
  printerProfileName?: string | null;
  onGateClick: (gate: GateState | null, gateIndex: number, device: UserPrinterDevice) => void;
}

function DeviceSection({ device, presetsSeedMap, spools, printerProfileName = null, onGateClick }: DeviceSectionProps) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [clearing, setClearing] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editName, setEditName] = useState(device.name);
  const [editGateCount, setEditGateCount] = useState<string>(device.gate_count?.toString() ?? '');
  const connectionState = getDeviceConnectionState(device.last_seen_at);

  const updateMutation = useMutation({
    mutationFn: (payload: { name?: string; gate_count?: number | null }) =>
      devicesAPI.update(device.id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devices'] });
      toast.success(t('presetSlots.edit.saved'));
      setEditOpen(false);
    },
    onError: (err: any) => {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    },
  });

  const handleEditSave = () => {
    const gateCountNum = editGateCount.trim() === '' ? null : parseInt(editGateCount, 10);
    updateMutation.mutate({
      name: editName.trim() || device.name,
      gate_count: gateCountNum,
    });
  };

  const { data: gates = [], isLoading } = useQuery({
    queryKey: ['gates', device.id],
    queryFn: () => presetSlotsAPI.list(device.id),
    staleTime: 30_000,
  });

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
    queryKey: ['preset-slot-missing-presets', device.id, missingPresetIds],
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
    if (!window.confirm(t('presetSlots.clearAllConfirm', { name: device.name }))) return;
    setClearing(true);
    try {
      const result = await presetSlotsAPI.clear(device.id);
      await queryClient.invalidateQueries({ queryKey: ['gates', device.id] });
      toast.success(t('presetSlots.cleared') + ` (${result.cleared})`);
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
            <h2 className="text-sm font-semibold text-white">{device.name}</h2>
            <p className="text-xs text-gray-500">{device.device_fingerprint}</p>
            {printerProfileName && (
              <p className="text-[11px] text-purple-300 mt-0.5">
                {t('presetSlots.mappedPrinter', { name: printerProfileName })}
              </p>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span
            className={[
              'flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium',
              connectionState === 'online'
                ? 'bg-emerald-500/15 text-emerald-300'
                : connectionState === 'stale'
                  ? 'bg-amber-500/15 text-amber-300'
                  : connectionState === 'offline'
                    ? 'bg-rose-500/15 text-rose-300'
                    : 'bg-white/10 text-gray-400',
            ].join(' ')}
          >
            {connectionState === 'online' ? (
              <Wifi className="h-3 w-3" />
            ) : connectionState === 'stale' ? (
              <AlertTriangle className="h-3 w-3" />
            ) : connectionState === 'offline' ? (
              <WifiOff className="h-3 w-3" />
            ) : (
              <Clock className="h-3 w-3" />
            )}
            {t(`presetSlots.connection.${connectionState}`)}
          </span>

          {device.supports_hh ? (
            <span className="flex items-center gap-1 rounded-full bg-green-500/15 px-2.5 py-1 text-xs font-medium text-green-400">
              <Zap className="h-3 w-3" />
              {t('presetSlots.hhActive')}
            </span>
          ) : (
            <span className="flex items-center gap-1 rounded-full bg-blue-500/15 px-2.5 py-1 text-xs font-medium text-blue-300">
              <Layers className="h-3 w-3" />
              {t('presetSlots.manualMode')}
            </span>
          )}
          {device.gate_count != null && (
            <span className="flex items-center gap-1 rounded-full bg-white/5 px-2.5 py-1 text-xs text-gray-400">
              <Layers className="h-3 w-3" />
              {device.gate_count} {t('presetSlots.gates')}
            </span>
          )}
          <span className="flex items-center gap-1 rounded-full bg-white/5 px-2.5 py-1 text-xs text-gray-500">
            <Clock className="h-3 w-3" />
            {formatLastSeen(device.last_seen_at, t, i18n.language)}
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

          <button
            type="button"
            onClick={() => {
              setEditName(device.name);
              setEditGateCount(device.gate_count?.toString() ?? '');
              setEditOpen((v) => !v);
            }}
            className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-gray-300 transition hover:bg-white/10"
          >
            <Settings2 className="h-3.5 w-3.5" />
            {t('presetSlots.edit.button')}
          </button>
        </div>
      </div>

      {editOpen && (
        <div className="mb-4 rounded-xl border border-white/10 bg-white/5 p-4">
          <div className="flex flex-wrap gap-3">
            <div className="flex-1 min-w-[160px]">
              <label className="mb-1 block text-xs text-gray-400">{t('presetSlots.edit.name')}</label>
              <input
                type="text"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                maxLength={200}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white placeholder-gray-600 focus:border-purple-500 focus:outline-none"
              />
            </div>
            <div className="w-36">
              <label className="mb-1 block text-xs text-gray-400">{t('presetSlots.edit.gateCount')}</label>
              <input
                type="number"
                value={editGateCount}
                onChange={(e) => setEditGateCount(e.target.value)}
                min={1}
                max={256}
                placeholder="auto"
                className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white placeholder-gray-600 focus:border-purple-500 focus:outline-none"
              />
              <p className="mt-0.5 text-[10px] text-gray-600">{t('presetSlots.edit.gateCountHint')}</p>
            </div>
          </div>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={handleEditSave}
              disabled={updateMutation.isPending}
              className="flex items-center gap-1.5 rounded-lg bg-purple-600 px-4 py-1.5 text-xs font-medium text-white transition hover:bg-purple-500 disabled:opacity-50"
            >
              {updateMutation.isPending && <Loader2 className="h-3 w-3 animate-spin" />}
              {t('presetSlots.edit.save')}
            </button>
            <button
              type="button"
              onClick={() => setEditOpen(false)}
              className="rounded-lg border border-white/10 bg-white/5 px-4 py-1.5 text-xs text-gray-400 transition hover:bg-white/10"
            >
              {t('presetSlots.edit.cancel')}
            </button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-10">
          <Loader2 className="h-6 w-6 animate-spin text-purple-400" />
        </div>
      ) : (
        <GateMapGrid
          device={device}
          gates={gates}
          presets={effectivePresetsMap}
          spools={spools}
          onGateClick={(gate, gateIndex) => onGateClick(gate, gateIndex, device)}
        />
      )}
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
    gateIndex: number;
    device: UserPrinterDevice | null;
  }>({ open: false, gate: null, gateIndex: 0, device: null });

  const { data: devices = [], isLoading: loadingDevices } = useQuery({
    queryKey: ['devices'],
    queryFn: devicesAPI.list,
    staleTime: 60_000,
  });

  const { data: presetsPage } = useQuery({
    queryKey: ['presets', { page: 1, size: 100, userId: user?.id }],
    queryFn: () => presetsAPI.list({ page: 1, size: 100, user_id: user?.id }),
    staleTime: 60_000,
    enabled: devices.length > 0 && !!user,
  });

  const shouldFetchSpools = externalSpools == null;
  const { data: fetchedSpools = [] } = useQuery({
    queryKey: ['spools'],
    queryFn: spoolsAPI.list,
    staleTime: 60_000,
    enabled: devices.length > 0 && shouldFetchSpools,
  });

  const spools = externalSpools ?? fetchedSpools;

  const printerNameById = useMemo(() => {
    const map = new Map<number, string>();
    for (const binding of printerBindings ?? []) {
      map.set(binding.id, binding.name);
    }
    return map;
  }, [printerBindings]);

  const filteredDevices = useMemo(() => {
    if (!printerBindings || printerBindings.length === 0) {
      return devices;
    }
    return devices.filter((device) => device.printer_id != null && printerNameById.has(device.printer_id));
  }, [devices, printerBindings, printerNameById]);

  const presetsMap: Record<number, Pick<Preset, 'id' | 'name' | 'extruder_temp' | 'bed_temp'>> = {};
  (presetsPage?.items ?? []).forEach((preset) => {
    presetsMap[preset.id] = preset;
  });

  const handleGateClick = (
    gate: GateState | null,
    gateIndex: number,
    device: UserPrinterDevice,
  ) => {
    setModalState({ open: true, gate, gateIndex, device });
  };

  if (loadingDevices) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader2 className="h-8 w-8 animate-spin text-purple-400" />
      </div>
    );
  }

  if (devices.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 py-12 text-center">
        <Cpu className="mb-4 h-12 w-12 text-gray-600" />
        <h2 className="mb-2 text-lg font-semibold text-white">{t('presetSlots.noDevices')}</h2>
        <p className="max-w-sm text-sm text-gray-500">{t('presetSlots.noDevicesDesc')}</p>
      </div>
    );
  }

  if (filteredDevices.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 py-12 text-center">
        <Cpu className="mb-4 h-12 w-12 text-gray-600" />
        <h2 className="mb-2 text-lg font-semibold text-white">{t('presetSlots.noMappedDevices')}</h2>
        <p className="max-w-sm text-sm text-gray-500">{t('presetSlots.noMappedDevicesDesc')}</p>
      </div>
    );
  }

  return (
    <>
      <div className={compact ? 'space-y-4' : 'space-y-6'}>
        {filteredDevices.map((device) => (
          <DeviceSection
            key={device.id}
            device={device}
            presetsSeedMap={presetsMap}
            spools={spools}
            printerProfileName={device.printer_id != null ? (printerNameById.get(device.printer_id) ?? null) : null}
            onGateClick={handleGateClick}
          />
        ))}
      </div>

      {modalState.device && (
        <PresetAssignModal
          isOpen={modalState.open}
          gateIndex={modalState.gateIndex}
          gate={modalState.gate}
          deviceId={modalState.device.id}
          deviceName={modalState.device.name}
          spools={spools}
          onClose={() => setModalState((s) => ({ ...s, open: false }))}
          onAssigned={() => setModalState((s) => ({ ...s, open: false }))}
        />
      )}
    </>
  );
}
