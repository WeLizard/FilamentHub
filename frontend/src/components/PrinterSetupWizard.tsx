/** One explicit physical device, optional local transport, and resumable setup. */
import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Check, ChevronRight, Loader2, Plus, Printer, RefreshCw, X } from 'lucide-react';
import type { AxiosError } from 'axios';
import { devicesAPI, physicalPrintersAPI, printersAPI } from '../api/client';
import type { PhysicalPrinter } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useDebounce } from '../hooks/useDebounce';
import { ModalOverlay } from './ModalOverlay';
import { Dropdown } from './Dropdown';
import { FEED_ADAPTERS, feedAdapterFor, supportsEdgeSetup } from './presetSlots/adapters';
import { EdgeConnectionSetup } from './presetSlots/EdgeConnectionSetup';
import { LinkInstructions } from './presetSlots/LinkInstructions';
import { translateApiError } from '../utils/translateApiError';
import { clearPrinterSetupIntent, persistPrinterSetupIntent, readPrinterSetupIntent } from '../utils/printerSetupRecovery';
import type { PendingPrinterSetup, PrinterSetupRoute } from '../utils/printerSetupRecovery';
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

const control = 'w-full rounded-lg border border-white/20 bg-white/5 px-3 py-2 text-sm text-white';
const button = 'rounded-lg border border-white/20 px-3 py-2 text-sm text-white hover:bg-white/10 disabled:opacity-40';

export function PrinterSetupWizard({
  onClose, initialName = '', initialPrinterId = null, initialProfileIds = [], physicalPrinter,
  printerProfiles = [],
}: PrinterSetupWizardProps) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<PendingPrinterSetup | null>(() => (
    user ? readPrinterSetupIntent(user.id) : null
  ));
  const [step, setStep] = useState<'choose' | 'setup'>(
    pending || physicalPrinter || initialName || initialPrinterId || initialProfileIds.length ? 'setup' : 'choose',
  );
  const [name, setName] = useState(pending?.payload.name ?? physicalPrinter?.name ?? initialName);
  const [modelId, setModelId] = useState(pending?.payload.printer_id ?? initialPrinterId ?? 0);
  const [profileIds, setProfileIds] = useState(pending?.payload.printer_profile_ids ?? initialProfileIds);
  const [targetId, setTargetId] = useState(pending?.targetId ?? physicalPrinter?.id ?? 0);
  const [mode, setMode] = useState<PrinterSetupRoute>(pending?.route ?? (pending?.probe ? 'orca' : 'manual'));
  const [provider, setProvider] = useState(pending?.payload.material_system?.provider ?? 'manual');
  const [slotCount, setSlotCount] = useState(String(pending?.payload.material_system?.slot_count ?? 1));
  const [search, setSearch] = useState('');
  const [pluginReady, setPluginReady] = useState(false);
  const [candidates, setCandidates] = useState<PrinterSetupCandidate[] | null>(null);
  const [loadingConnections, setLoadingConnections] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const scanBusy = useRef(false);
  const [probe, setProbe] = useState<PrinterSetupResult | null>(pending?.probe ?? null);
  const [saved, setSaved] = useState<PhysicalPrinter | null>(null);
  const [activated, setActivated] = useState(false);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const alive = useRef(true);
  const [error, setError] = useState<string | null>(null);
  const [issuedKey, setIssuedKey] = useState<string | null>(null);
  const debouncedSearch = useDebounce(search, 250);
  const { data: printers = [], isPending: loadingPrinters, isError: printersFailed, refetch: reloadPrinters } = useQuery({
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
    enabled: step === 'setup' && !targetId && !saved,
  });
  const { data: installed } = useQuery({
    queryKey: ['printer-candidates'], queryFn: physicalPrintersAPI.listInstalledCandidates,
    enabled: step === 'setup' && !targetId && !saved && initialProfileIds.length === 0,
  });
  const current = printers.find((item) => item.id === saved?.id) ?? saved;
  const selected = printers.find((item) => item.id === targetId)
    ?? (physicalPrinter?.id === targetId ? physicalPrinter : undefined);
  const adapter = feedAdapterFor(provider);
  const system = current?.material_systems[0];
  const savedAdapter = feedAdapterFor(system?.provider ?? provider);
  const edgeAvailable = supportsEdgeSetup(selected?.material_systems[0]?.provider ?? provider);
  const count = probe?.gateCount ?? (adapter.topologyFromProvider ? null : Number(slotCount));
  const valid = Boolean(targetId || name.trim()) && (count == null || (
    Number.isInteger(count) && count >= 1 && count <= 256
  )) && (mode !== 'orca' || Boolean(probe?.ok) || provider === 'bambu')
    && (mode !== 'edge' || edgeAvailable);
  const printerChoices = printers.map((item) => {
    const connections = bindings.filter((binding) => binding.physical_printer_id === item.id);
    const names = printerProfiles.filter((profile) => item.printer_profile_ids.includes(profile.id))
      .map((profile) => profile.name);
    const detail = [...new Set([
      ...names, ...connections.flatMap((binding) => [binding.preset_name, binding.display_endpoint]),
    ].filter(Boolean))].join(' / ');
    return { printer: item, detail };
  });
  const newCandidates = (candidates ?? []).filter((candidate) => !printers.some((item) => item.id === candidate.physicalPrinterId));

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
  const scan = async () => {
    if (scanBusy.current) return;
    scanBusy.current = true;
    setLoadingConnections(true); setScanError(null);
    try {
      const result = await requestPrinterSetup('list');
      if (!alive.current) return;
      if (!result.ok) setScanError(t('printerSetup.errors.' + result.code, { defaultValue: t('printerSetup.failed') }));
      else setCandidates(result.candidates ?? []);
    } catch {
      if (alive.current) setScanError(t('printerSetup.failed'));
    } finally {
      scanBusy.current = false;
      if (alive.current) setLoadingConnections(false);
    }
  };
  useEffect(() => {
    if ((step === 'choose' || mode === 'orca') && pluginReady && candidates === null && !pending) void scan();
    // One bounded inventory read on entering this path; retries are explicit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, mode, pluginReady]);

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
    if (!user) return;
    if (!pending && mode === 'edge' && !edgeAvailable) {
      setError(t('printerSetup.edgeUnsupported')); return;
    }
    const intent: PendingPrinterSetup = pending ?? {
      targetId, probe, route: mode,
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
    // Persist the exact request before sending: reopening after response loss
    // must resume it, not manufacture a fresh physical printer.
    if (!persistPrinterSetupIntent(user.id, intent)) {
      setError(t('printerSetup.recoveryUnavailable')); return;
    }
    setPending(intent);
    let printer: PhysicalPrinter;
    try {
      printer = intent.targetId
        ? await physicalPrintersAPI.setupConnection(intent.targetId, intent.payload)
        : await physicalPrintersAPI.create(intent.payload);
    } catch (err) {
      const status = (err as AxiosError).response?.status;
      if (status && status >= 400 && status < 500) {
        setPending(null); clearPrinterSetupIntent(user.id, intent.payload.request_id);
      }
      throw err;
    }
    setSaved(printer); setProbe(intent.probe); setPending(null);
    clearPrinterSetupIntent(user.id, intent.payload.request_id);
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
  const choose = (printer?: PhysicalPrinter) => {
    setTargetId(printer?.id ?? 0); setName(printer?.name ?? '');
    setModelId(0); setProfileIds([]); setSearch('');
    setProvider(printer?.material_systems[0]?.provider ?? 'manual'); setSlotCount('1');
    setProbe(null); setMode('manual'); setError(null); setStep('setup');
  };
  const chooseCandidate = (candidate: PrinterSetupCandidate) => {
    choose(printers.find((item) => item.id === candidate.physicalPrinterId));
    // A known binding still names the same printer if its probe fails.
    setTargetId(candidate.physicalPrinterId ?? 0);
    setName(printers.find((item) => item.id === candidate.physicalPrinterId)?.name ?? candidate.label);
    setMode('orca');
    void inspect(candidate);
  };
  const back = () => {
    if (busyRef.current || pending) return;
    setTargetId(0); setProbe(null); setError(null); setStep('choose');
  };
  const submitLabel = pending ? 'printerSetup.resumeButton' : targetId ? 'printerSetup.connect' : 'printerSetup.save';

  return <ModalOverlay onClose={close} closeOnOverlayClick={!busy} closeOnEscape={!busy}>
    <div role="dialog" aria-modal="true" aria-labelledby="printer-setup-title"
      className="flex max-h-[calc(100dvh-2rem)] w-full max-w-xl flex-col overflow-hidden rounded-2xl border border-white/20 bg-gray-900 text-white shadow-2xl">
      <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
        <h2 id="printer-setup-title" className="text-lg font-semibold">{t(physicalPrinter ? 'printerSetup.connectionSettings' : 'printerSetup.title')}</h2>
        <button type="button" disabled={busy} onClick={close} aria-label={t('common.close')}><X className="h-5 w-5" /></button>
      </div>
      <form className="flex min-h-0 flex-col" onSubmit={(event) => { event.preventDefault(); if (step === 'setup' && (valid || pending || saved)) void save(); }}>
        <div className="space-y-4 overflow-y-auto px-6 py-5">
          {current ? <>
            <h3 className="flex items-center gap-2 font-medium"><Check className="h-5 w-5 text-emerald-400" />{current.name}</h3>
            <p className="text-sm text-gray-300">{t(activated ? 'printerSetup.observed' : 'printerSetup.saved')}</p>
            {probe && !activated && <button type="button" className={button} disabled={busy} onClick={() => void save()}>{t('printerSetup.retryConnection')}</button>}
            {system && mode === 'edge'
              ? supportsEdgeSetup(system.provider)
                ? <EdgeConnectionSetup printer={current} system={system} />
                : <p role="alert" className="text-sm text-amber-200">{t('printerSetup.edgeUnsupported')}</p>
              : system && savedAdapter.renderSetup?.({ printer: current, system, gates: [], spools: [], linkConfirmed: false })}
            {savedAdapter.link && <details className="rounded-lg border border-white/10 p-3">
              <summary className="cursor-pointer text-sm">{t('printerSetup.inventorySetup')}</summary>
              {savedAdapter.renderCreateHelp?.()}
              {issuedKey ? <LinkInstructions link={savedAdapter.link}
                baseUrl={window.location.origin + '/api/v1/spool_compat'} apiKey={issuedKey} />
                : current.has_api_key ? <p className="mt-2 text-xs text-gray-400">{t('printerSetup.keyExists')}</p>
                  : <button type="button" className={button + ' mt-3'} disabled={busy} onClick={() => void issueKey()}>{t('printerSetup.issueKey')}</button>}
            </details>}
          </> : step === 'choose' ? <fieldset disabled={busy} className="min-w-0 space-y-4">
            <div>
              <h3 className="font-medium">{t('printerSetup.target')}</h3>
              <p className="mt-1 text-sm text-gray-400">{t('printerSetup.description')}</p>
            </div>
            {loadingPrinters && <p role="status" className="text-sm text-gray-400">{t('printerSetup.loadingPrinters')}</p>}
            {printersFailed && <p role="alert" className="text-sm text-amber-200">
              {t('printerSetup.listFailed')} <button type="button" className="underline" onClick={() => void reloadPrinters()}>{t('printerSetup.retry')}</button>
            </p>}
            {printerChoices.length > 0 && <div className="space-y-2">
              <p className="text-xs font-medium text-gray-400">{t('printerSetup.yourPrinters')}</p>
              {printerChoices.map(({ printer, detail }) => <button key={printer.id} type="button"
                aria-label={printer.name + ' — ' + (detail || t('printerSetup.printerNumber', { id: printer.id }))}
                className={button + ' flex w-full items-center gap-3 text-left'} onClick={() => choose(printer)}>
                <Printer className="h-5 w-5 shrink-0 text-purple-300" />
                <span className="min-w-0 flex-1">
                  <span className="block break-words font-medium">{printer.name}</span>
                  <span className="block break-words text-xs text-gray-400">{detail || t('printerSetup.printerNumber', { id: printer.id })}</span>
                  <span className="text-xs text-purple-300">{t('printerSetup.alreadyAdded')}</span>
                </span>
                <ChevronRight className="h-4 w-4 shrink-0 text-gray-400" />
              </button>)}
            </div>}
            {pluginReady && <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-medium text-gray-400">{t('printerSetup.fromOrca')}</p>
                <button type="button" disabled={loadingConnections} className="rounded p-1 text-gray-400 hover:text-white disabled:opacity-40" onClick={() => void scan()} aria-label={t('printerSetup.refresh')}><RefreshCw className="h-4 w-4" /></button>
              </div>
              {loadingConnections && <p role="status" className="text-sm text-gray-400">{t('printerSetup.loadingConnections')}</p>}
              {scanError && <p role="alert" className="text-sm text-amber-200">{scanError}</p>}
              {newCandidates.map((candidate) => <button key={candidate.connectionRef} type="button"
                className={button + ' flex w-full items-center gap-3 text-left'} onClick={() => chooseCandidate(candidate)}>
                <Printer className="h-5 w-5 shrink-0 text-purple-300" />
                <span className="min-w-0 flex-1 break-words">{candidate.label}</span>
                <ChevronRight className="h-4 w-4 shrink-0 text-gray-400" />
              </button>)}
              {candidates !== null && newCandidates.length === 0 && <p className="text-sm text-gray-400">{t('printerSetup.noNewConnections')}</p>}
            </div>}
            {!loadingPrinters && !printersFailed && printers.length === 0 && !pluginReady && <p className="text-sm text-gray-400">{t('printerSetup.emptyPrinters')}</p>}
          </fieldset> : <>
            {pending && <p role="status" className="rounded-lg bg-amber-500/10 p-3 text-sm text-amber-200">{t('printerSetup.resume')}</p>}
            <fieldset disabled={busy || Boolean(pending)} className="min-w-0 space-y-4 disabled:opacity-70">
              {!targetId && !probe && <div className="space-y-2">
                <Dropdown label={t('printerSetup.model')} value={modelId || ''} onChange={(value) => {
                  setModelId(Number(value)); setProfileIds(initialProfileIds);
                  const model = models?.items.find((item) => item.id === Number(value));
                  if (model && !name.trim()) setName(model.name);
                }} options={(models?.items ?? []).map((item) => ({ value: item.id, label: item.name }))}
                  placeholder={t('addPrinter.modelPlaceholder')} filterable filterValue={search} onFilterChange={setSearch} />
                <p className="text-xs text-gray-400">{t('printerSetup.modelHint')}</p>
                {(installed ?? []).length > 0 && <details>
                  <summary className="cursor-pointer text-xs text-gray-400">{t('printerSetup.savedModels')}</summary>
                  <p className="my-2 text-xs text-gray-400">{t('printerSetup.savedModelsHint')}</p>
                  <div className="flex flex-wrap gap-2">{(installed ?? []).map((item) => <button key={item.model}
                    type="button" className={button} onClick={() => { setModelId(item.printer_id ?? 0);
                      setName(item.model); setProfileIds(item.printer_profile_id ? [item.printer_profile_id] : []); }}>{item.model}</button>)}</div>
                </details>}
              </div>}
              {!targetId && <label className="block text-sm">{t('printerSetup.name')}
                <input className={control + ' mt-1'} value={name} maxLength={200} required
                  onChange={(event) => setName(event.target.value)} placeholder={t('printerSetup.namePlaceholder')} />
              </label>}
              {targetId > 0 && <p className="break-words text-sm text-purple-200">{t('printerSetup.keepExisting', { name: selected?.name ?? name })}</p>}
              <details className="rounded-lg border border-white/10 p-3" open={mode !== 'manual' || targetId > 0}>
                <summary className="cursor-pointer text-sm font-medium">{t('printerSetup.connectionOptional')}</summary>
                <div className="mt-3 space-y-3">
                  <p className="mb-2 text-sm font-medium">{t('printerSetup.route')}</p>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-3" role="group" aria-label={t('printerSetup.route')}>
                    {(['manual', 'orca', 'edge'] as const).map((route) => <button key={route} type="button"
                      disabled={route === 'edge' && !edgeAvailable}
                      aria-pressed={mode === route} className={button + (mode === route ? ' border-purple-400 bg-purple-500/20' : '')}
                      onClick={() => { setMode(route); setProbe(null); setError(null); }}>{t('printerSetup.routes.' + route)}</button>)}
                  </div>
                  {!edgeAvailable && <p className="text-xs text-amber-200">{t('printerSetup.edgeUnsupported')}</p>}
                  {mode === 'manual' && <p className="text-xs text-gray-400">{t('printerSetup.manualHint')}</p>}
                  {mode === 'edge' && <p className="text-xs text-gray-400">{t('printerSetup.edgeHint')}</p>}
                  {mode === 'orca' && <div className="space-y-2 rounded-lg border border-white/10 p-3">
                    {!pluginReady ? <p className="text-sm text-amber-200">{t('printerSetup.pluginUnavailable')}</p> : <>
                      <p className="text-xs text-gray-400">{t('printerSetup.orcaHint')}</p>
                      {loadingConnections && <p role="status" className="text-xs text-gray-400">{t('printerSetup.loadingConnections')}</p>}
                      {scanError && <p role="alert" className="text-sm text-amber-200">{scanError}</p>}
                      {(candidates ?? []).map((candidate) => <button key={candidate.connectionRef} type="button"
                        className={button + ' w-full break-words text-left'} onClick={() => void inspect(candidate)}>
                        {candidate.label}{candidate.physicalPrinterId ? ' · #' + candidate.physicalPrinterId : ''}
                      </button>)}
                      {candidates?.length === 0 && <p className="text-xs text-gray-400">{t('printerSetup.noConnections')}</p>}
                      <div className="flex flex-wrap gap-2"><button type="button" className={button} onClick={() => void inspect()}>{t('printerSetup.enterAddress')}</button>
                        <button type="button" disabled={loadingConnections} className={button} onClick={() => void scan()} aria-label={t('printerSetup.refresh')}><RefreshCw className="h-4 w-4" /></button></div>
                    </>}
                    {probe?.ok && <div role="status" className="text-sm text-emerald-300">
                      {t(probe.gateCount ? 'printerSetup.probeGates' : 'printerSetup.probeConnected', { count: probe.gateCount ?? undefined })}
                      <p className="mt-1 text-xs text-gray-400">{t('printerSetup.readOnly')}</p>
                    </div>}
                  </div>}
                </div>
              </details>
              {!selected?.material_systems.length && <>
                <label className="block text-sm">{t('printerSetup.feedSystem')}
                  <Dropdown value={provider} onChange={(value) => setProvider(String(value))} clearable={false}
                    disabled={Boolean(probe)} options={FEED_ADAPTERS.filter((item) => mode !== 'edge' || supportsEdgeSetup(item.id))
                      .map((item) => ({ value: item.id, label: t(item.labelKey) }))} />
                </label>
                {!probe && <p className="text-xs text-gray-400">{t(adapter.topologyFromProvider ? 'printerSetup.slotsAfterConnection' : 'printerSetup.feedHint')}</p>}
                {count !== null && !probe?.gateCount && <label className="block text-sm">{t('presetSlots.newSystem.slotCount')}
                  <input className={control + ' mt-1'} type="number" min={1} max={256} value={slotCount}
                    onChange={(event) => setSlotCount(event.target.value)} />
                </label>}
              </>}
              {(targetId > 0 || name.trim()) && <p className="break-words rounded-lg bg-white/5 p-3 text-sm text-gray-300">{t(targetId ? 'printerSetup.confirmExisting' : 'printerSetup.confirmNew', { name: selected?.name ?? name.trim() })}</p>}
            </fieldset>
          </>}
          {busy && <p role="status" className="flex items-center gap-2 text-sm text-purple-200"><Loader2 className="h-4 w-4 animate-spin" />{t('printerSetup.working')}</p>}
          {error && <p role="alert" className="rounded-lg bg-rose-500/10 p-3 text-sm text-rose-300">{error}</p>}
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-3 border-t border-white/10 px-6 py-4">
          {!current && step === 'choose' && <button type="button" disabled={busy} className={button + ' mr-auto flex items-center justify-center gap-2 border-purple-400/50 bg-purple-500/10'} onClick={() => choose()}>
            <Plus className="h-4 w-4" />{t('printerSetup.newDevice')}
          </button>}
          {!current && step === 'setup' && !physicalPrinter && !pending && <button type="button" disabled={busy} className={button + ' mr-auto flex items-center gap-1'} onClick={back}>
            <ArrowLeft className="h-4 w-4" />{t('printerSetup.back')}
          </button>}
          {(current || step === 'choose' || physicalPrinter || pending) && <button type="button" disabled={busy} className={button} onClick={close}>{t(current ? 'presetSlots.newSystem.done' : 'common.cancel')}</button>}
          {!current && step === 'setup' && <button type="submit" disabled={busy || (!pending && !valid)} className={button + ' bg-purple-600'}>
            {t(submitLabel)}
          </button>}
        </div>
      </form>
    </div>
  </ModalOverlay>;
}
