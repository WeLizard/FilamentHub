import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Search, X, Loader2, CheckCircle2, Trash2, Package } from 'lucide-react';
import { presetsAPI, presetSlotsAPI } from '../../api/client';
import type { GateState, UserSpool } from '../../api/client';
import { toast } from '../Toast';
import { translateApiError } from '../../utils/translateApiError';
import { getSpoolCurrentLocation, getSpoolLastLocation } from '../../utils/spoolLocation';
import { ModalOverlay } from '../ModalOverlay';

interface PresetAssignModalProps {
  isOpen: boolean;
  gateIndex: number;
  gate: GateState | null;
  deviceId: number;
  deviceName: string;
  /** User's spools from "Мои филаменты" */
  spools: UserSpool[];
  onClose: () => void;
  onAssigned: () => void;
}

export function PresetAssignModal({
  isOpen,
  gateIndex,
  gate,
  deviceId,
  deviceName,
  spools,
  onClose,
  onAssigned,
}: PresetAssignModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedPresetId, setSelectedPresetId] = useState<number | null>(null);
  const [selectedSpoolId, setSelectedSpoolId] = useState<number | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState<'preset' | 'spool'>('preset');

  const searchRef = useRef<HTMLInputElement>(null);

  // Sync state when gate/isOpen changes
  useEffect(() => {
    if (isOpen) {
      setSelectedPresetId(gate?.preset_id ?? null);
      setSelectedSpoolId(gate?.spool_id ?? null);
      setSearch('');
      setDebouncedSearch('');
      setActiveTab('preset');
    }
  }, [gate, isOpen]);

  // Focus search on open
  useEffect(() => {
    if (isOpen) setTimeout(() => searchRef.current?.focus(), 80);
  }, [isOpen]);

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const { data: presetsPage, isLoading: loadingPresets } = useQuery({
    queryKey: ['presets-for-assign', debouncedSearch],
    queryFn: () =>
      presetsAPI.list({
        page: 1,
        size: 50,
        active_only: true,
        search: debouncedSearch || undefined,
      }),
    enabled: isOpen,
    staleTime: 30_000,
  });

  const filtered = presetsPage?.items ?? [];

  // Shelf spools are the primary candidates to load; active ones can be
  // re-seated from another slot. Archived/empty spools cannot be assigned.
  const activeSpools = spools.filter(
    (s) => (s.state === 'active' || s.state === 'shelf') && s.remaining_weight_g > 0,
  );

  const handleAssign = async () => {
    if (selectedPresetId === null && selectedSpoolId === null) return;
    setIsSubmitting(true);
    try {
      await presetSlotsAPI.assign(deviceId, gateIndex, {
        preset_id: selectedPresetId,
        spool_id: selectedSpoolId,
      });
      await queryClient.invalidateQueries({ queryKey: ['gates', deviceId] });
      toast.success(t('presetSlots.modal.assigned', { gate: gateIndex }));
      onAssigned();
    } catch (err: any) {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClear = async () => {
    setIsSubmitting(true);
    try {
      await presetSlotsAPI.assign(deviceId, gateIndex, { preset_id: null, spool_id: null });
      await queryClient.invalidateQueries({ queryKey: ['gates', deviceId] });
      toast.success(t('presetSlots.modal.assigned', { gate: gateIndex }));
      onAssigned();
    } catch (err: any) {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  const colorHex = gate?.hh_color_hex ? `#${gate.hh_color_hex.replace(/^#/, '')}` : null;
  const hasExistingAssignment = !!(gate?.preset_id || gate?.spool_id);
  const canSave = selectedPresetId !== null || selectedSpoolId !== null;

  return (
    <ModalOverlay onClose={onClose} className="!bg-black/60">
      <div className="flex w-full max-w-md flex-col rounded-2xl border border-white/10 bg-[#0e0e1b] shadow-2xl" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-purple-500/20 text-sm font-bold text-purple-300">
              {gateIndex}
            </span>
            <div>
              <h2 className="text-sm font-semibold text-white">
                {t('presetSlots.modal.title', { gate: gateIndex })}
              </h2>
              <p className="text-xs text-gray-500">{deviceName}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-gray-400 transition hover:bg-white/10 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* HH data row */}
        {(gate?.hh_material || colorHex) && (
          <div className="flex items-center gap-2 border-b border-white/5 px-5 py-2.5">
            {colorHex && (
              <span
                className="h-3.5 w-3.5 flex-shrink-0 rounded-full border border-white/20"
                style={{ backgroundColor: colorHex }}
              />
            )}
            <span className="text-xs text-gray-400">
              {t('presetSlots.modal.hhInfo', { material: gate?.hh_material ?? '' })}
            </span>
          </div>
        )}

        {/* Tabs: Preset | Spool */}
        <div className="flex border-b border-white/10 px-5">
          {(['preset', 'spool'] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={[
                'py-2.5 pr-4 text-sm font-medium transition border-b-2 -mb-px',
                activeTab === tab
                  ? 'border-purple-500 text-purple-300'
                  : 'border-transparent text-gray-500 hover:text-gray-300',
              ].join(' ')}
            >
              {tab === 'preset'
                ? t('profilePage.tabs.presets')
                : t('profilePage.tabs.spools')}
              {tab === 'preset' && selectedPresetId != null && (
                <span className="ml-1.5 inline-flex h-4 w-4 items-center justify-center rounded-full bg-purple-600 text-[10px] text-white">
                  ✓
                </span>
              )}
              {tab === 'spool' && selectedSpoolId != null && (
                <span className="ml-1.5 inline-flex h-4 w-4 items-center justify-center rounded-full bg-purple-600 text-[10px] text-white">
                  ✓
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="min-h-0 flex-1">
          {activeTab === 'preset' && (
            <>
              {/* Search */}
              <div className="px-5 pt-4">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
                  <input
                    ref={searchRef}
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder={t('presetSlots.modal.searchPreset')}
                    className="w-full rounded-xl border border-white/10 bg-white/5 py-2.5 pl-9 pr-4 text-sm text-white placeholder-gray-500 outline-none focus:border-purple-500/50 focus:ring-1 focus:ring-purple-500/30"
                  />
                  {search && (
                    <button
                      type="button"
                      onClick={() => setSearch('')}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>

              {/* Preset list */}
              <div className="my-3 max-h-56 overflow-y-auto px-5">
                {loadingPresets ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-5 w-5 animate-spin text-purple-400" />
                  </div>
                ) : filtered.length === 0 ? (
                  <p className="py-6 text-center text-sm text-gray-500">
                    {t('presetSlots.modal.noPresets')}
                  </p>
                ) : (
                  <div className="space-y-1">
                    {filtered.map((p) => (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() =>
                          setSelectedPresetId(selectedPresetId === p.id ? null : p.id)
                        }
                        className={[
                          'flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition',
                          selectedPresetId === p.id
                            ? 'bg-purple-600/25 ring-1 ring-purple-500/50'
                            : 'hover:bg-white/5',
                        ].join(' ')}
                      >
                        {selectedPresetId === p.id ? (
                          <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-purple-400" />
                        ) : (
                          <span className="h-4 w-4 flex-shrink-0 rounded-full border border-white/20" />
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-white">{p.name}</p>
                          <p className="text-xs text-gray-500">
                            {p.extruder_temp}°C / {p.bed_temp}°C
                          </p>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

          {activeTab === 'spool' && (
            <div className="my-3 max-h-64 overflow-y-auto px-5">
              {activeSpools.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-center">
                  <Package className="mb-3 h-8 w-8 text-gray-600" />
                  <p className="text-sm text-gray-500">{t('profilePage.spoolsEmpty')}</p>
                </div>
              ) : (
                <div className="space-y-1">
                  {/* None option */}
                  <button
                    type="button"
                    onClick={() => setSelectedSpoolId(null)}
                    className={[
                      'flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition',
                      selectedSpoolId === null
                        ? 'bg-purple-600/25 ring-1 ring-purple-500/50'
                        : 'hover:bg-white/5',
                    ].join(' ')}
                  >
                    {selectedSpoolId === null ? (
                      <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-purple-400" />
                    ) : (
                      <span className="h-4 w-4 flex-shrink-0 rounded-full border border-white/20" />
                    )}
                    <span className="text-sm text-gray-400">—</span>
                  </button>

                  {activeSpools.map((s) => {
                    const colorStyle = s.filament?.color_hex
                      ? { backgroundColor: `#${s.filament.color_hex.replace(/^#/, '')}` }
                      : undefined;
                    return (
                      <button
                        key={s.id}
                        type="button"
                        onClick={() =>
                          setSelectedSpoolId(selectedSpoolId === s.id ? null : s.id)
                        }
                        className={[
                          'flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition',
                          selectedSpoolId === s.id
                            ? 'bg-purple-600/25 ring-1 ring-purple-500/50'
                            : 'hover:bg-white/5',
                        ].join(' ')}
                      >
                        {selectedSpoolId === s.id ? (
                          <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-purple-400" />
                        ) : (
                          <span className="h-4 w-4 flex-shrink-0 rounded-full border border-white/20" />
                        )}
                        {colorStyle && (
                          <span
                            className="h-3.5 w-3.5 flex-shrink-0 rounded-full border border-white/20"
                            style={colorStyle}
                          />
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-white">
                            {s.filament
                              ? [s.filament.brand_name, s.filament.name]
                                  .filter(Boolean)
                                  .join(' ')
                              : t('profilePage.spoolNoFilament')}
                          </p>
                          <p className="text-xs text-gray-500">
                            {s.filament?.material_type && `${s.filament.material_type} · `}
                            {Math.round(s.remaining_weight_g)}г /{' '}
                            {Math.round(s.remaining_pct)}%
                            {s.lot_nr && ` · № ${s.lot_nr}`}
                          </p>
                          {(() => {
                            const current = getSpoolCurrentLocation(s.extra);
                            if (current) {
                              return (
                                <p className="truncate text-[11px] text-purple-400/80">
                                  {t('profilePage.spoolCurrentLocation', {
                                    printer: current.printer,
                                    gate: current.gate,
                                  })}
                                </p>
                              );
                            }
                            const last = getSpoolLastLocation(s.extra);
                            if (!last) return null;
                            return (
                              <p className="truncate text-[11px] text-gray-600">
                                {t('profilePage.spoolLastLocation', {
                                  printer: last.printer,
                                  gate: last.gate,
                                })}
                                {last.unloadedAt &&
                                  ` · ${new Date(last.unloadedAt).toLocaleDateString()}`}
                              </p>
                            );
                          })()}
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-2 border-t border-white/10 px-5 py-4">
          <div>
            {hasExistingAssignment && (
              <button
                type="button"
                onClick={handleClear}
                disabled={isSubmitting}
                className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm text-red-400 transition hover:bg-red-500/10 disabled:opacity-50"
              >
                <Trash2 className="h-4 w-4" />
                {t('presetSlots.modal.clear')}
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm text-gray-300 transition hover:bg-white/10"
            >
              {t('presetSlots.modal.cancel')}
            </button>
            <button
              type="button"
              onClick={handleAssign}
              disabled={!canSave || isSubmitting}
              className="flex items-center gap-1.5 rounded-xl bg-purple-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-purple-500 disabled:opacity-50"
            >
              {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
              {t('presetSlots.modal.assign')}
            </button>
          </div>
        </div>
      </div>
    </ModalOverlay>
  );
}
