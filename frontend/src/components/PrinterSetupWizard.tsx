/** One explicit physical device, optional local transport, and resumable setup. */
import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Check, Loader2, RefreshCw, X } from 'lucide-react';
import type { AxiosError } from 'axios';
import { devicesAPI, physicalPrintersAPI, printersAPI } from '../api/client';
import type { PhysicalPrinter } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useDebounce } from '../hooks/useDebounce';
import { ModalOverlay } from './ModalOverlay';
import { Dropdown } from './Dropdown';
import { FEED_ADAPTERS, feedAdapterFor } from './presetSlots/adapters';
import { EdgeConnectionSetup } from './presetSlots/EdgeConnectionSetup';
import { LinkInstructions } from './presetSlots/LinkInstructions';
import { translateApiError } from '../utils/translateApiError';
import { safeStorage } from '../utils/storage';
import {
  isPluginEmbed, requestPluginCapabilities, requestPrinterSetup, subscribeToPluginCapabilities,
} from '../utils/pluginBridge';
import type { PrinterSetupCandidate, PrinterSetupResult } from '../utils/pluginBridge';

export interface PrinterSetupWizardProps {
  onClose: () => void;
  initialProfileIds?: number[];
  initialName?: string;
  initialPrinterId?: number | null;
  physicalPrinter?: PhysicalPrinter;
  printerProfiles?: Array<{ id: number; name: string }>;
}

type CreatePayload = Parameters<typeof physicalPrintersAPI.create>[0];
type PendingSetup = { payload: CreatePayload; targetId: number; probe: PrinterSetupResult | null };
const control = 'w-full rounded-lg border border-white/20 bg-white/5 px-3 py-2 text-sm text-white';
const button = 'rounded-lg border border-white/20 px-3 py-2 text-sm text-white hover:bg-white/10 disabled:opacity-40';

export function PrinterSetupWizard({
  onClose, initialName = '', initialPrinterId = null, initialProfileIds = [], physicalPrinter,
  printerProfiles = [],
}: PrinterSetupWizardProps) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const storageKey = 'fh-printer-setup-' + user?.id;
  const [pending, setPending] = useState<PendingSetup | null>(() => {
    try {
      const item = JSON.parse(safeStorage.get(storageKey) || 'null');
      return item?.payload?.request_id && typeof item.targetId === 'number' ? item : null;
    } catch { return null; }
  });
  const [name, setName] = useState(pending?.payload.name ?? physicalPrinter?.name ?? initialName);
  const [modelId, setModelId] = useState(initialPrinterId ?? 0);
  const [profileIds, setProfileIds] = useState(initialProfileIds);
  const [targetId, setTargetId] = useState(pending?.targetId ?? physicalPrinter?.id ?? 0);
  const [mode, setMode] = useState<'manual' | 'orca' | 'edge'>('manual');
  const [provider, setProvider] = useState('manual');
  const [slotCount, setSlotCount] = useState('1');
  const [search, setSearch] = useState('');
  const [pluginReady, setPluginReady] = useState(false);
  const [candidates, setCandidates] = useState<PrinterSetupCandidate[] | null>(null);
  const [probe, setProbe] = useState<PrinterSetupResult | null>(pending?.probe ?? null);
  const [saved, setSaved] = useState<PhysicalPrinter | null>(null);
  const [activated, setActivated] = useState(false);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const alive = useRef(true);
  const [error, setError] = useState<string | null>(null);
  const [issuedKey, setIssuedKey] = useState<string | null>(null);
  const debouncedSearch = useDebounce(search, 250);
  const { data: printers = [] } = useQuery({
    queryKey: ['physical-printers'], queryFn: physicalPrintersAPI.list,
  });
  const { data: bindings = [] } = useQuery({
    queryKey: ['printer-bindings'], queryFn: physicalPrintersAPI.listBindings,
    enabled: printers.length > 0,
  });
  const { data: models } = useQuery({
    queryKey: ['printers', 'add-printer-picker', debouncedSearch],
    queryFn: () => printersAPI.list({ page: 1, size: 50, active_only: true,
      search: debouncedSearch.trim() || undefined }),
    enabled: !targetId && !saved,
  });
  const { data: installed } = useQuery({
    queryKey: ['printer-candidates'], queryFn: physicalPrintersAPI.listInstalledCandidates,
    enabled: !targetId && initialProfileIds.length === 0,
  });
  const current = printers.find((item) => item.id === saved?.id) ?? saved;
  const selected = printers.find((item) => item.id === targetId) ?? physicalPrinter;
  const adapter = feedAdapterFor(provider);
  const system = current?.material_systems[0];
  const savedAdapter = feedAdapterFor(system?.provider ?? provider);
  const count = probe?.gateCount ?? (adapter.topologyFromProvider ? null : Number(slotCount));
  const valid = Boolean(targetId || name.trim()) && (count == null || (
    Number.isInteger(count) && count >= 1 && count <= 256
  )) && (mode !== 'orca' || Boolean(probe?.ok) || provider === 'bambu');
  const targetOptions = printers.map((item) => {
    const connections = bindings.filter((binding) => binding.physical_printer_id === item.id);
    const names = printerProfiles.filter((profile) => item.printer_profile_ids.includes(profile.id))
      .map((profile) => profile.name);
    const detail = [...new Set([
      ...names, ...connections.flatMap((binding) => [binding.preset_name, binding.display_endpoint]),
    ].filter(Boolean))].join(' / ');
    return { value: item.id, label: item.name + ' · #' + item.id + (detail ? ' — ' + detail : '') };
  });

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);
  useEffect(() => {
    if (!isPluginEmbed()) return;
    const unsubscribe = subscribeToPluginCapabilities((caps) => setPluginReady(caps.has('printer-setup-v1')));
    requestPluginCapabilities();
    return unsubscribe;
  }, []);

  const invalidate = async () => {
    await Promise.all(['physical-printers', 'devices', 'printer-bindings', 'printer-connections-pending']
      .map((key) => queryClient.invalidateQueries({ queryKey: [key] })));
  };
  const run = async (action: () => Promise<void>) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true); setError(null);
    try { await action(); }
    catch (err) {
      const detail = (err as AxiosError<{ detail: unknown }>).response?.data?.detail;
      if (alive.current) setError(translateApiError(t, detail, t('printerSetup.failed')));
    } finally {
      busyRef.current = false;
      if (alive.current) setBusy(false);
    }
  };
  const scan = () => run(async () => {
    const result = await requestPrinterSetup('list');
    if (!result.ok) {
      setError(t('printerSetup.errors.' + result.code, { defaultValue: t('printerSetup.failed') }));
      return;
    }
    if (alive.current) setCandidates(result.candidates ?? []);
  });
  useEffect(() => {
    if (mode === 'orca' && pluginReady && candidates === null && !pending) void scan();
    // One bounded inventory read on entering this path; retries are explicit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, pluginReady]);

  const inspect = (candidate?: PrinterSetupCandidate) => run(async () => {
    setProbe(null);
    if (candidate?.physicalPrinterId && targetId && candidate.physicalPrinterId !== targetId) {
      setError(t('printerSetup.otherCard')); return;
    }
    const result = await requestPrinterSetup(candidate ? 'probe' : 'manual', candidate
      ? { connectionRef: candidate.connectionRef }
      : { copy: { title: t('printerSetup.localTitle'), hint: t('printerSetup.localHint'),
        address: t('printerSetup.address'), apiKey: t('printerSetup.apiKey'), submit: t('printerSetup.check') } });
    if (!alive.current || result.code === 'cancelled') return;
    if (!result.ok) {
      setError(t('printerSetup.errors.' + result.code, { defaultValue: t('printerSetup.failed') }));
      return;
    }
    if (!result.probeId || !result.connection) throw new Error('probe failed');
    setProbe(result); setProvider(result.provider ?? 'manual');
    if (candidate?.physicalPrinterId) setTargetId(candidate.physicalPrinterId);
    if (!name.trim()) setName(result.printerHostname || candidate?.label || 'Moonraker');
  });
  const activate = async (printer: PhysicalPrinter, checked: PrinterSetupResult | null) => {
    if (!checked) return;
    const result = await requestPrinterSetup('activate', {
      probeId: checked.probeId, physicalPrinterId: printer.id,
    });
    if (!result.ok) { setError(t('printerSetup.savedConnectionFailed')); return; }
    setActivated(true);
    await invalidate();
  };
  const save = () => run(async () => {
    if (saved) { await activate(saved, probe); return; }
    const intent: PendingSetup = pending ?? {
      targetId, probe,
      payload: {
        request_id: crypto.randomUUID(), name: name.trim() || selected?.name || 'Printer',
        printer_id: modelId || null, printer_profile_ids: profileIds,
        ...(probe?.connection ? { connection: probe.connection } : {}),
        ...(selected?.material_systems.length ? {} : { material_system: {
          name: t(adapter.labelKey), provider: adapter.id,
          kind: adapter.topologyFromProvider || Number(count) > 1 ? 'mmu' : 'direct_feed',
          capabilities: adapter.capabilities, ...(count == null ? {} : { slot_count: count }),
        } }),
      },
    };
    setPending(intent);
    // Persist the exact request before sending: reopening after response loss
    // must resume it, not manufacture a fresh physical printer.
    safeStorage.set(storageKey, JSON.stringify(intent));
    let printer: PhysicalPrinter;
    try {
      printer = intent.targetId
        ? await physicalPrintersAPI.setupConnection(intent.targetId, intent.payload)
        : await physicalPrintersAPI.create(intent.payload);
    } catch (err) {
      const status = (err as AxiosError).response?.status;
      if (status && status >= 400 && status < 500) {
        setPending(null); safeStorage.remove(storageKey);
      }
      throw err;
    }
    setSaved(printer); setProbe(intent.probe); setPending(null);
    safeStorage.remove(storageKey);
    await invalidate();
    await activate(printer, intent.probe);
  });
  const issueKey = () => run(async () => {
    if (!current || current.has_api_key) return;
    const result = await devicesAPI.regenerateKey(current.id);
    setIssuedKey(result.api_key);
    await invalidate();
  });
  const close = () => { if (!busyRef.current) onClose(); };

  return <ModalOverlay onClose={close} closeOnOverlayClick={!busy} closeOnEscape={!busy}>
    <div role="dialog" aria-modal="true" aria-labelledby="printer-setup-title"
      className="w-full max-w-xl rounded-2xl border border-white/20 bg-gray-900 text-white shadow-2xl">
      <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
        <h2 id="printer-setup-title" className="text-lg font-semibold">{t('printerSetup.title')}</h2>
        <button type="button" disabled={busy} onClick={close} aria-label={t('common.close')}><X className="h-5 w-5" /></button>
      </div>
      <form onSubmit={(event) => { event.preventDefault(); if (valid || pending || saved) void save(); }}>
        <div className="space-y-4 px-6 py-5">
          {current ? <>
            <h3 className="flex items-center gap-2 font-medium"><Check className="h-5 w-5 text-emerald-400" />{current.name}</h3>
            <p className="text-sm text-gray-300">{t(activated ? 'printerSetup.observed' : 'printerSetup.saved')}</p>
            {probe && !activated && <button type="button" className={button} disabled={busy} onClick={() => void save()}>{t('printerSetup.retryConnection')}</button>}
            {system && mode === 'edge' && ['manual', 'legacy', 'happy_hare'].includes(system.provider)
              ? <EdgeConnectionSetup printer={current} system={system} />
              : system && savedAdapter.renderSetup?.({ printer: current, system, gates: [], spools: [], linkConfirmed: false })}
            {savedAdapter.link && <details className="rounded-lg border border-white/10 p-3">
              <summary className="cursor-pointer text-sm">{t('printerSetup.inventorySetup')}</summary>
              {savedAdapter.renderCreateHelp?.()}
              {issuedKey ? <LinkInstructions link={savedAdapter.link}
                baseUrl={window.location.origin + '/api/v1/spool_compat'} apiKey={issuedKey} />
                : current.has_api_key ? <p className="mt-2 text-xs text-gray-400">{t('printerSetup.keyExists')}</p>
                  : <button type="button" className={button + ' mt-3'} disabled={busy} onClick={() => void issueKey()}>{t('printerSetup.issueKey')}</button>}
            </details>}
          </> : <>
            {pending && <p role="status" className="rounded-lg bg-amber-500/10 p-3 text-sm text-amber-200">{t('printerSetup.resume')}</p>}
            <fieldset disabled={busy || Boolean(pending)} className="space-y-4 disabled:opacity-70">
              <p className="text-sm text-gray-400">{t('printerSetup.description')}</p>
              {!physicalPrinter && <label className="block text-sm">{t('printerSetup.target')}
                <Dropdown value={targetId} onChange={(value) => { setTargetId(Number(value)); setProbe(null); }}
                  options={[{ value: 0, label: t('printerSetup.newDevice') }, ...targetOptions]} />
              </label>}
              {!targetId && <label className="block text-sm">{t('addPrinter.name')}
                <input className={control + ' mt-1'} value={name} maxLength={200} required
                  onChange={(event) => setName(event.target.value)} placeholder={t('addPrinter.namePlaceholder')} />
              </label>}
              {targetId > 0 && <p className="text-sm text-purple-200">{t('printerSetup.keepExisting', { name: selected?.name ?? name })}</p>}
              <div className="grid grid-cols-3 gap-2" role="group" aria-label={t('printerSetup.route')}>
                {(['manual', 'orca', 'edge'] as const).map((route) => <button key={route} type="button"
                  aria-pressed={mode === route} className={button + (mode === route ? ' border-purple-400 bg-purple-500/20' : '')}
                  onClick={() => { setMode(route); setProbe(null); setError(null);
                    if (route === 'edge' && !['manual', 'happy_hare'].includes(provider)) setProvider('manual');
                  }}>{t('printerSetup.routes.' + route)}</button>)}
              </div>
              {mode === 'manual' && <p className="text-xs text-gray-400">{t('printerSetup.manualHint')}</p>}
              {mode === 'edge' && <p className="text-xs text-gray-400">{t('printerSetup.edgeHint')}</p>}
              {mode === 'orca' && <div className="space-y-2 rounded-lg border border-white/10 p-3">
                {!pluginReady ? <p className="text-sm text-amber-200">{t('printerSetup.pluginUnavailable')}</p> : <>
                  <p className="text-xs text-gray-400">{t('printerSetup.orcaHint')}</p>
                  {(candidates ?? []).map((candidate) => <button key={candidate.connectionRef} type="button"
                    className={button + ' w-full text-left'} onClick={() => void inspect(candidate)}>
                    {candidate.label}{candidate.physicalPrinterId ? ' · #' + candidate.physicalPrinterId : ''}
                  </button>)}
                  {candidates?.length === 0 && <p className="text-xs text-gray-400">{t('printerSetup.noConnections')}</p>}
                  <div className="flex flex-wrap gap-2"><button type="button" className={button} onClick={() => void inspect()}>{t('printerSetup.enterAddress')}</button>
                    <button type="button" className={button} onClick={() => void scan()} aria-label={t('printerSetup.refresh')}><RefreshCw className="h-4 w-4" /></button></div>
                </>}
                {probe?.ok && <div role="status" className="text-sm text-emerald-300">
                  {t(probe.gateCount ? 'printerSetup.probeGates' : 'printerSetup.probeConnected', { count: probe.gateCount ?? undefined })}
                  <p className="mt-1 text-xs text-gray-400">{t('printerSetup.readOnly')}</p>
                </div>}
              </div>}
              {!selected?.material_systems.length && <>
                <label className="block text-sm">{t('presetSlots.newSystem.system')}
                  <Dropdown value={provider} onChange={(value) => setProvider(String(value))}
                    disabled={Boolean(probe)} options={FEED_ADAPTERS.filter((item) => mode !== 'edge' || ['manual', 'happy_hare'].includes(item.id))
                      .map((item) => ({ value: item.id, label: t(item.labelKey) }))} />
                </label>
                {count !== null && !probe?.gateCount && <label className="block text-sm">{t('presetSlots.newSystem.slotCount')}
                  <input className={control + ' mt-1'} type="number" min={1} max={256} value={slotCount}
                    onChange={(event) => setSlotCount(event.target.value)} />
                </label>}
              </>}
              {!targetId && <details>
                <summary className="cursor-pointer text-sm text-gray-400">{t('printerSetup.modelOptional')}</summary>
                <p className="my-2 text-xs text-gray-400">{t('printerSetup.modelHint')}</p>
                <div className="mb-2 flex flex-wrap gap-2">{(installed ?? []).map((item) => <button key={item.model}
                  type="button" className={button} onClick={() => { setModelId(item.printer_id ?? 0);
                    setName(item.model); setProfileIds(item.printer_profile_id ? [item.printer_profile_id] : []); }}>{item.model}</button>)}</div>
                <Dropdown value={modelId} onChange={(value) => { setModelId(Number(value)); setProfileIds(initialProfileIds); }}
                  options={(models?.items ?? []).map((item) => ({ value: item.id, label: item.name }))}
                  placeholder={t('addPrinter.modelPlaceholder')} filterable filterValue={search} onFilterChange={setSearch} />
              </details>}
            </fieldset>
          </>}
          {busy && <p role="status" className="flex items-center gap-2 text-sm text-purple-200"><Loader2 className="h-4 w-4 animate-spin" />{t('printerSetup.working')}</p>}
          {error && <p role="alert" className="rounded-lg bg-rose-500/10 p-3 text-sm text-rose-300">{error}</p>}
        </div>
        <div className="flex justify-end gap-3 border-t border-white/10 px-6 py-4">
          <button type="button" disabled={busy} className={button} onClick={close}>{t(current ? 'presetSlots.newSystem.done' : 'common.cancel')}</button>
          {!current && <button type="submit" disabled={busy || (!pending && !valid)} className={button + ' bg-purple-600'}>
            {t(pending ? 'printerSetup.resumeButton' : 'printerSetup.save')}
          </button>}
        </div>
      </form>
    </div>
  </ModalOverlay>;
}
