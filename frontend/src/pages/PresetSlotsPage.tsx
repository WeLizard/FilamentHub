import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Cpu, Clock, Layers, Zap, Trash2, Loader2 } from 'lucide-react';
import { devicesAPI, presetSlotsAPI, presetsAPI, spoolsAPI } from '../api/client';
import type { GateState, UserPrinterDevice, UserSpool } from '../api/client';
import type { Preset } from '../types/api';
import { GateMapGrid } from '../components/presetSlots/GateMapGrid';
import { PresetAssignModal } from '../components/presetSlots/PresetAssignModal';
import { toast } from '../components/Toast';
import { translateApiError } from '../utils/translateApiError';
import { SEOHead } from '../components/SEOHead';

// ── helpers ────────────────────────────────────────────────────────────────

function formatLastSeen(ts: string | null, neverLabel: string): string {
  if (!ts) return neverLabel;
  const d = new Date(ts);
  const diff = Date.now() - d.getTime();
  if (diff < 60_000) return '< 1 мин';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} мин назад`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} ч назад`;
  return d.toLocaleDateString();
}

// ── Per-device section ─────────────────────────────────────────────────────

interface DeviceSectionProps {
  device: UserPrinterDevice;
  presetsMap: Record<number, Pick<Preset, 'id' | 'name' | 'extruder_temp' | 'bed_temp'>>;
  spools: UserSpool[];
  onGateClick: (gate: GateState | null, gateIndex: number, device: UserPrinterDevice) => void;
}

function DeviceSection({ device, presetsMap, spools, onGateClick }: DeviceSectionProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [clearing, setClearing] = useState(false);

  const { data: gates = [], isLoading } = useQuery({
    queryKey: ['gates', device.id],
    queryFn: () => presetSlotsAPI.list(device.id),
    staleTime: 30_000,
  });

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
      {/* Device header */}
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-500/20">
            <Cpu className="h-5 w-5 text-purple-300" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-white">{device.name}</h2>
            <p className="text-xs text-gray-500">{device.device_fingerprint}</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {device.supports_hh && (
            <span className="flex items-center gap-1 rounded-full bg-green-500/15 px-2.5 py-1 text-xs font-medium text-green-400">
              <Zap className="h-3 w-3" />
              {t('presetSlots.hhActive')}
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
            {formatLastSeen(device.last_seen_at, t('presetSlots.neverSeen'))}
          </span>
          <button
            type="button"
            onClick={handleClearAll}
            disabled={clearing || gates.every((g) => !g.preset_id)}
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

      {/* Gate grid */}
      {isLoading ? (
        <div className="flex items-center justify-center py-10">
          <Loader2 className="h-6 w-6 animate-spin text-purple-400" />
        </div>
      ) : (
        <GateMapGrid
          device={device}
          gates={gates}
          presets={presetsMap}
          spools={spools}
          onGateClick={(gate, gateIndex) => onGateClick(gate, gateIndex, device)}
        />
      )}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export function PresetSlotsPage() {
  const { t } = useTranslation();

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

  // Pre-load user's presets for the gate grid labels
  const { data: presetsPage } = useQuery({
    queryKey: ['presets', { page: 1, size: 100 }],
    queryFn: () => presetsAPI.list({ page: 1, size: 100 }),
    staleTime: 60_000,
    enabled: devices.length > 0,
  });

  // Pre-load user's spools for the assign modal
  const { data: spools = [] } = useQuery({
    queryKey: ['spools'],
    queryFn: spoolsAPI.list,
    staleTime: 60_000,
    enabled: devices.length > 0,
  });

  const presetsMap: Record<number, Pick<Preset, 'id' | 'name' | 'extruder_temp' | 'bed_temp'>> = {};
  (presetsPage?.items ?? []).forEach((p) => {
    presetsMap[p.id] = p;
  });

  const handleGateClick = (
    gate: GateState | null,
    gateIndex: number,
    device: UserPrinterDevice,
  ) => {
    setModalState({ open: true, gate, gateIndex, device });
  };

  return (
    <>
      <SEOHead title={t('presetSlots.title')} />

      <div className="relative z-10 mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
        {/* Page header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-white sm:text-3xl">{t('presetSlots.title')}</h1>
          <p className="mt-1 text-sm text-gray-400">{t('presetSlots.subtitle')}</p>
        </div>

        {/* Content */}
        {loadingDevices ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-8 w-8 animate-spin text-purple-400" />
          </div>
        ) : devices.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 py-20 text-center">
            <Cpu className="mb-4 h-12 w-12 text-gray-600" />
            <h2 className="mb-2 text-lg font-semibold text-white">{t('presetSlots.noDevices')}</h2>
            <p className="max-w-sm text-sm text-gray-500">{t('presetSlots.noDevicesDesc')}</p>
          </div>
        ) : (
          <div className="space-y-6">
            {devices.map((device) => (
              <DeviceSection
                key={device.id}
                device={device}
                presetsMap={presetsMap}
                spools={spools}
                onGateClick={handleGateClick}
              />
            ))}
          </div>
        )}
      </div>

      {/* Assign modal */}
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
