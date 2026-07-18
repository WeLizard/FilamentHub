import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Search, X, Loader2, CheckCircle2, Trash2, Package, Copy, Check, AlertTriangle } from 'lucide-react';
import { physicalPrintersAPI, presetsAPI, savedPresetsAPI } from '../../api/client';
import type { GateState, UserSpool } from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';
import { toast } from '../Toast';
import { translateApiError } from '../../utils/translateApiError';
import { getSpoolCurrentLocation, getSpoolLastLocation } from '../../utils/spoolLocation';
import { ModalOverlay } from '../ModalOverlay';
import { isUnidentifiedHHFilament, markHHGateEmptyCommand } from '../../utils/hhGateState';

interface PresetAssignModalProps {
  isOpen: boolean;
  gateIndex: number;
  gate: GateState | null;
  physicalPrinterId: number;
  materialSlotId: number;
  deviceName: string;
  systemName: string;
  provider: string;
  /** User's spools from "Мои филаменты" */
  spools: UserSpool[];
  onClose: () => void;
  onAssigned: () => void;
}

export function PresetAssignModal({
  isOpen,
  gateIndex,
  gate,
  physicalPrinterId,
  materialSlotId,
  deviceName,
  systemName,
  provider,
  spools,
  onClose,
  onAssigned,
}: PresetAssignModalProps) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedPresetId, setSelectedPresetId] = useState<number | null>(null);
  const [selectedSpoolId, setSelectedSpoolId] = useState<number | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState<'preset' | 'spool'>('spool');
  const [emptyCommandCopied, setEmptyCommandCopied] = useState(false);
  // When a spool is chosen, the preset list is scoped to its filament to cut
  // the noise of the whole catalog; this opts back into the global search.
  const [showAllPresets, setShowAllPresets] = useState(false);

  const searchRef = useRef<HTMLInputElement>(null);

  // Sync state when gate/isOpen changes
  useEffect(() => {
    if (isOpen) {
      setSelectedPresetId(gate?.preset_id ?? null);
      setSelectedSpoolId(gate?.spool_id ?? null);
      setSearch('');
      setDebouncedSearch('');
      // Filament-first: start on the spool tab so the preset choice can be
      // narrowed to the loaded filament.
      setActiveTab('spool');
      setEmptyCommandCopied(false);
      setShowAllPresets(false);
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

  // Filament of the selected spool scopes the preset list. Within that scope
  // the default is the user's own library for the filament (saved + created);
  // "show all" opens the whole catalog for the same filament.
  const selectedSpool =
    selectedSpoolId != null ? spools.find((s) => s.id === selectedSpoolId) ?? null : null;
  const selectedSpoolFilamentName = selectedSpool?.filament
    ? [selectedSpool.filament.brand_name, selectedSpool.filament.name].filter(Boolean).join(' ')
    : null;
  const spoolFilamentId = selectedSpool?.filament?.id ?? null;

  // The user's saved library — reuses the app-wide cache key so no extra fetch.
  const { data: savedPresets } = useQuery({
    queryKey: ['saved-presets', user?.id],
    queryFn: () => savedPresetsAPI.list(),
    enabled: isOpen && !!user?.id,
    staleTime: 30_000,
  });

  const { data: presetsPage, isLoading: loadingPresets } = useQuery({
    queryKey: ['presets-for-assign', debouncedSearch, spoolFilamentId],
    queryFn: () =>
      presetsAPI.list({
        page: 1,
        size: 50,
        active_only: true,
        search: debouncedSearch || undefined,
        filament_id: spoolFilamentId ?? undefined,
      }),
    enabled: isOpen,
    staleTime: 30_000,
  });

  const catalogPresets = presetsPage?.items ?? [];
  // Library scope active when a filament is chosen and the user hasn't opted
  // into the full catalog. Own presets and saved-from-catalog both count.
  const libraryScoped = spoolFilamentId != null && !showAllPresets;
  const savedPresetIds = new Set((savedPresets?.items ?? []).map((s) => s.preset_id));
  const filtered = libraryScoped
    ? catalogPresets.filter((p) => savedPresetIds.has(p.id) || p.user_id === user?.id)
    : catalogPresets;

  // Shelf spools are the primary candidates to load; active ones can be
  // re-seated from another slot. Archived/empty spools cannot be assigned.
  const activeSpools = spools.filter(
    (s) => (s.state === 'active' || s.state === 'shelf') && s.remaining_weight_g > 0,
  );

  const handleAssign = async () => {
    if (selectedPresetId === null && selectedSpoolId === null) return;
    setIsSubmitting(true);
    try {
      await physicalPrintersAPI.assignSlot(physicalPrinterId, materialSlotId, {
        preset_id: selectedPresetId,
        spool_id: selectedSpoolId,
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['physical-printers'] }),
        queryClient.invalidateQueries({ queryKey: ['spools'] }),
      ]);
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
      await physicalPrintersAPI.assignSlot(physicalPrinterId, materialSlotId, {
        preset_id: null,
        spool_id: null,
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['physical-printers'] }),
        queryClient.invalidateQueries({ queryKey: ['spools'] }),
      ]);
      toast.success(t('presetSlots.modal.assigned', { gate: gateIndex }));
      onAssigned();
    } catch (err: any) {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    } finally {
      setIsSubmitting(false);
    }
  };

  const unidentifiedFilament = provider === 'happy_hare' && isUnidentifiedHHFilament(gate);
  const emptyGateCommand = markHHGateEmptyCommand(gateIndex);

  const handleCopyEmptyCommand = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(emptyGateCommand);
      } else {
        const textarea = document.createElement('textarea');
        textarea.value = emptyGateCommand;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        document.execCommand('copy');
        textarea.remove();
      }
      setEmptyCommandCopied(true);
      window.setTimeout(() => setEmptyCommandCopied(false), 1800);
    } catch {
      toast.error(t('common.error'));
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
              <p className="text-xs text-gray-500">{deviceName} · {systemName}</p>
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

        {unidentifiedFilament && (
          <div className="border-b border-amber-400/15 bg-amber-500/10 px-5 py-3">
            <div className="flex items-start gap-2.5">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold text-amber-100">
                  {t('presetSlots.unidentified.title')}
                </p>
                <p className="mt-1 text-[11px] leading-relaxed text-amber-100/70">
                  {t('presetSlots.unidentified.description')}
                </p>
                <p className="mt-2 text-[11px] text-amber-100/70">
                  {t('presetSlots.unidentified.emptyHint')}
                </p>
                <div className="mt-1.5 flex items-center gap-2">
                  <code className="min-w-0 flex-1 overflow-x-auto rounded-lg border border-white/10 bg-black/25 px-2.5 py-1.5 text-[10px] text-white">
                    {emptyGateCommand}
                  </code>
                  <button
                    type="button"
                    onClick={handleCopyEmptyCommand}
                    className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-amber-300/25 bg-white/5 px-2.5 py-1.5 text-[10px] text-amber-100 transition hover:bg-white/10"
                  >
                    {emptyCommandCopied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                    {t(emptyCommandCopied ? 'presetSlots.pairing.copied' : 'presetSlots.pairing.copy')}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tabs: Preset | Spool */}
        <div className="flex border-b border-white/10 px-5">
          {(['spool', 'preset'] as const).map((tab) => (
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
              {/* Filament scope banner */}
              {selectedSpoolFilamentName && (
                <div className="flex items-center justify-between gap-2 px-5 pt-4">
                  {libraryScoped ? (
                    <>
                      <span className="min-w-0 truncate text-xs text-purple-300/80">
                        {t('presetSlots.modal.presetsForFilament', { filament: selectedSpoolFilamentName })}
                      </span>
                      <button
                        type="button"
                        onClick={() => setShowAllPresets(true)}
                        className="shrink-0 text-xs text-gray-400 underline transition hover:text-white"
                      >
                        {t('presetSlots.modal.showAllPresets')}
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setShowAllPresets(false)}
                      className="text-xs text-purple-300 underline transition hover:text-white"
                    >
                      {t('presetSlots.modal.backToFilamentPresets', { filament: selectedSpoolFilamentName })}
                    </button>
                  )}
                </div>
              )}

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
                    {libraryScoped
                      ? t('presetSlots.modal.noPresetsForFilament')
                      : t('presetSlots.modal.noPresets')}
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
