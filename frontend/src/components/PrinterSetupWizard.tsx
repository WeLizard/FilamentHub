/** One explicit physical device, optional local transport, and resumable setup. */
import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Check, ChevronRight, Loader2, Plus, RefreshCw, X } from 'lucide-react';
import type { AxiosError } from 'axios';
import { devicesAPI, physicalPrintersAPI, printersAPI } from '../api/client';
import type { MaterialSystem, PhysicalPrinter } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useDebounce } from '../hooks/useDebounce';
import { ModalOverlay } from './ModalOverlay';
import { ConfirmModal } from './ConfirmModal';
import { Dropdown } from './Dropdown';
import { adapterForConnection, connectionAdapterFor, feedAdapterFor, setupAdaptersFor, setupTopologiesFor, supportsEdgeSetup } from './presetSlots/adapters';
import { LayeredPrinterIcon } from './icons/LayeredPrinterIcon';
import { TopologyEditor } from './presetSlots/TopologyEditor';
import { initialTopology, topologyFromSystem, topologyPayload } from './presetSlots/adapters/topology';
import type { TopologySelection } from './presetSlots/adapters/topology';
import type { Printer as CatalogPrinter } from '../types/api';
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
  const [provider, setProvider] = useState(pending?.payload.material_system_update?.provider ?? pending?.payload.material_system?.provider ?? physicalPrinter?.material_systems[0]?.provider ?? 'manual');
  const [topology, setTopology] = useState(() => initialTopology(
    setupTopologiesFor(provider, false)[0],
  ));
  const [selectedModel, setSelectedModel] = useState<CatalogPrinter>();
  const [otherConnection, setOtherConnection] = useState(false);
  const [manualSettings, setManualSettings] = useState(false);
  const customized = useRef(false);
  const [topologyDeclared, setTopologyDeclared] = useState(false);
  const autoPrepared = useRef<number | null>(null);
  const autoProbes = useRef(new Set<string>());
  const [editTopology, setEditTopology] = useState(false);
  const [topologyBase, setTopologyBase] = useState<MaterialSystem | null>(null);
  const [connectionChosen, setConnectionChosen] = useState(Boolean(
    pending?.route && pending.route !== 'manual' || physicalPrinter?.material_systems[0]?.provider !== undefined
      && physicalPrinter.material_systems[0].provider !== 'manual',
  ));
  const [search, setSearch] = useState('');
  const [pluginReady, setPluginReady] = useState(false);
  const [candidates, setCandidates] = useState<PrinterSetupCandidate[] | null>(null);
  const [loadingConnections, setLoadingConnections] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const scanBusy = useRef(false);
  const [probe, setProbe] = useState<PrinterSetupResult | null>(pending?.probe ?? null);
  const [saved, setSaved] = useState<PhysicalPrinter | null>(null);
  const [activated, setActivated] = useState(false);
  const [observed, setObserved] = useState(false);
  const [inventoryLinked, setInventoryLinked] = useState(false);
  const [finishInventory, setFinishInventory] = useState(false);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const alive = useRef(true);
  const [error, setError] = useState<string | null>(null);
  const [issuedKey, setIssuedKey] = useState<string | null>(null);
  const [confirmKey, setConfirmKey] = useState(false);
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
  const existingSystem = selected?.material_systems[0];
  const modelLookupId = targetId ? selected?.printer_id ?? 0 : modelId;
  const { data: modelDetail } = useQuery({
    queryKey: ['printers', 'setup-model', modelLookupId], queryFn: () => printersAPI.get(modelLookupId),
    enabled: modelLookupId > 0 && selectedModel?.id !== modelLookupId && !pending && !saved,
  });
  useEffect(() => {
    if (!modelDetail || modelDetail.id !== modelLookupId || selectedModel?.id === modelLookupId) return;
    setSelectedModel(modelDetail);
    // An explicit connection choice wins over catalog suggestions arriving late.
    if (!customized.current && !connectionChosen && !existingSystem) {
      const suggested = setupAdaptersFor(modelDetail).find((item) => item.onboarding?.matchesModel?.(modelDetail));
      if (suggested) {
        setProvider(suggested.id); setConnectionChosen(true);
        if (!manualSettings) setMode(suggested.onboarding?.methods[0] ?? 'manual');
        setTopology(initialTopology(setupTopologiesFor(suggested.id, false)[0]));
      }
    }
  }, [modelDetail, modelLookupId, selectedModel?.id, connectionChosen, existingSystem, manualSettings]);
  const adapter = feedAdapterFor(provider);
  const connectionAdapter = connectionAdapterFor(provider);
  const system = current?.material_systems[0];
  const savedAdapter = feedAdapterFor(system?.provider ?? provider);
  const topologies = setupTopologiesFor(provider, !probe && (!existingSystem || existingSystem.provider === 'manual'));
  const manualTopology = topologyPayload(topologies, topology);
  const setupAdapters = setupAdaptersFor(selectedModel, otherConnection);
  const methods = connectionChosen || probe ? adapter.onboarding?.methods ?? [] : [];
  const edgeAvailable = supportsEdgeSetup(existingSystem && !editTopology ? existingSystem.provider : provider,
    existingSystem && !editTopology ? existingSystem.kind : manualTopology?.kind);
  const valid = Boolean(targetId || name.trim()) && Boolean(probe || existingSystem && !editTopology || manualTopology)
    && (mode !== 'orca' || Boolean(probe?.ok) || adapter.onboarding?.orcaProbe !== true)
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
  const knownCandidates = (candidates ?? []).filter((candidate) => targetId > 0 && candidate.physicalPrinterId === targetId);
  useEffect(() => {
    if (!targetId || !selected || pending || saved || customized.current || autoPrepared.current === targetId) return;
    const existingAdapter = existingSystem && existingSystem.provider !== 'manual' ? feedAdapterFor(existingSystem.provider) : undefined;
    const named = existingAdapter?.id === existingSystem?.provider ? existingAdapter : undefined;
    const choices = new Set(bindings.filter((binding) => binding.physical_printer_id === targetId && binding.status !== 'conflict')
      .map((binding) => adapterForConnection(binding.provider)?.id).filter(Boolean));
    const found = named ?? (choices.size === 1 ? feedAdapterFor([...choices][0]!) : undefined);
    if (!found) return;
    autoPrepared.current = targetId;
    setProvider(found.id); setConnectionChosen(true);
    setTopology(topologyFromSystem(setupTopologiesFor(found.id, false), existingSystem));
    setMode(found.onboarding?.orcaProbe ? (isPluginEmbed() ? 'orca' : found.onboarding.methods.includes('native') ? 'native' : 'manual')
      : found.onboarding?.methods[0] ?? 'manual');
  }, [targetId, selected, bindings, existingSystem, pending, saved, manualSettings]);

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
    if ((step === 'choose' || mode === 'orca' || targetId > 0) && pluginReady && candidates === null && !pending) void scan();
    // One bounded inventory read on entering this path; retries are explicit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, mode, pluginReady, targetId]);

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
    autoPrepared.current = candidate?.physicalPrinterId ?? targetId;
    setTopology(topologyFromSystem(setupTopologiesFor(result.provider ?? 'manual', false), existingSystem));
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
    setObserved(result.observed === true);
    setInventoryLinked(result.inventoryLinked === true);
    await invalidate();
  };
  const save = () => run(async () => {
    if (saved) { await activate(saved, probe); return; }
    if (!user) return;
    if (!pending && mode === 'edge' && !edgeAvailable) {
      setError(t('printerSetup.edgeUnsupported')); return;
    }
    const changingTopology = existingSystem && editTopology;
    const baseSystem = topologyBase ?? existingSystem;
    const feedName = t(provider === 'manual'
      ? (topologies.find((item) => item.id === topology.choice)?.labelKey ?? adapter.labelKey)
      : adapter.labelKey);
    const oldAdapter = feedAdapterFor(baseSystem?.provider ?? provider);
    const generatedNames = [oldAdapter.labelKey, ...(oldAdapter.onboarding?.topologies.map((item) => item.labelKey) ?? [])].map((key) => t(key));
    const intent: PendingPrinterSetup = pending ?? {
      targetId, probe, route: mode,
      payload: {
        request_id: crypto.randomUUID(), name: name.trim() || selected?.name || 'Printer',
        printer_id: modelId || null, printer_profile_ids: profileIds,
        ...(probe?.connection ? { connection: probe.connection } : {}),
        ...(changingTopology ? {
          material_system_id: existingSystem.id,
          material_system_update: { ...manualTopology!, provider,
            ...(baseSystem && generatedNames.includes(baseSystem.name) ? { name: feedName } : {}),
            expected_slots: baseSystem!.slots.map((slot) => ({ material_slot_id: slot.id,
              expected_revision: slot.assignment_revision,
              expected_spool_id: slot.assignment?.spool_id ?? slot.legacy_projection?.spool_id ?? null })) },
        } : {}),
        ...(selected?.material_systems.length ? {} : { material_system: {
          name: feedName, provider: adapter.id,
          capabilities: adapter.capabilities,
          ...((probe || !topologyDeclared && mode !== 'manual') && adapter.topologyFromProvider ? { kind: 'mmu' }
            : { ...manualTopology!, ...(manualTopology?.slots.length === 1 && manualTopology.slots[0].provider_index === 0
              ? { slot_count: 1 } : {}) }),
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
    if (!current) return;
    const result = await devicesAPI.regenerateKey(current.id);
    setIssuedKey(result.api_key);
    setInventoryLinked(false); setConfirmKey(false);
    await invalidate();
  });
  const close = () => { if (!busyRef.current) onClose(); };
  const choose = (printer?: PhysicalPrinter) => {
    setManualSettings(false); autoPrepared.current = null; customized.current = false; setTopologyDeclared(false);
    setTargetId(printer?.id ?? 0); setName(printer?.name ?? '');
    setModelId(0); setProfileIds([]); setSearch('');
    changeProvider(printer?.material_systems[0]?.provider ?? 'manual');
    setTopology(topologyFromSystem(setupTopologiesFor(printer?.material_systems[0]?.provider ?? 'manual', false), printer?.material_systems[0]));
    setSelectedModel(undefined); setOtherConnection(false); setEditTopology(false); setTopologyBase(null);
    setConnectionChosen(Boolean(printer?.material_systems[0]?.provider && printer.material_systems[0].provider !== 'manual'));
    setProbe(null); setMode('manual'); setError(null); setStep('setup');
  };
  const changeProvider = (value: string) => {
    setProvider(value); setProbe(null); setError(null);
    setTopology(topologyFromSystem(setupTopologiesFor(value, false), existingSystem));
  };
  const changeTopology = (value: TopologySelection) => {
    customized.current = true; setTopologyDeclared(true);
    const choice = topologies.find((item) => item.id === value.choice)!;
    const nextProvider = choice.provider!;
    setTopology(value); setProvider(nextProvider); setError(null);
    if (nextProvider !== provider) {
      setConnectionChosen(true);
    }
    if (mode !== 'manual' && (!feedAdapterFor(nextProvider).onboarding?.methods.includes(mode)
      || mode === 'edge' && !supportsEdgeSetup(nextProvider, choice.kind))) setMode('manual');
  };
  const chooseModel = (model?: CatalogPrinter) => {
    setSelectedModel(model); setModelId(model?.id ?? 0); setProfileIds(initialProfileIds);
    setOtherConnection(false); setMode('manual');
    const suggested = setupAdaptersFor(model).find((item) => item.onboarding?.matchesModel?.(model!));
    changeProvider(suggested?.id ?? 'manual');
    if (suggested && !manualSettings) setMode(suggested.onboarding?.methods[0] ?? 'manual');
    setConnectionChosen(Boolean(suggested));
    if (model && (!name.trim() || name === selectedModel?.name)) setName(model.name);
  };
  const chooseCandidate = (candidate: PrinterSetupCandidate) => {
    choose(printers.find((item) => item.id === candidate.physicalPrinterId));
    // A known binding still names the same printer if its probe fails.
    setTargetId(candidate.physicalPrinterId ?? 0);
    setName(printers.find((item) => item.id === candidate.physicalPrinterId)?.name ?? candidate.label);
    setMode('orca');
    setConnectionChosen(true);
    void inspect(candidate);
  };
  useEffect(() => {
    if (step !== 'setup' || customized.current || pending || saved || probe || !pluginReady || busyRef.current || knownCandidates.length !== 1
      || existingSystem && connectionAdapterFor(existingSystem.provider).id !== 'manual') return;
    const candidate = knownCandidates[0];
    if (!candidate) return;
    const key = `${targetId}:${candidate.connectionRef}`;
    if (autoProbes.current.has(key)) return;
    autoProbes.current.add(key);
    setMode('orca'); setConnectionChosen(true);
    void inspect(candidate);
    // One read for the selected, already-bound device; no polling or name matching.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, targetId, candidates, pluginReady, manualSettings, pending, saved]);
  const checkInventory = () => run(async () => {
    if (!current || !probe?.connection) return;
    const checked = await requestPrinterSetup('probe', { connectionRef: probe.connection.connection_ref });
    if (!checked.ok || !checked.probeId || !checked.connection) { setError(t('printerSetup.errors.' + checked.code, { defaultValue: t('printerSetup.failed') })); return; }
    setProbe(checked);
    await activate(current, checked);
  });
  const back = () => {
    if (busyRef.current || pending) return;
    setTargetId(0); setProbe(null); setError(null); setStep('choose');
  };
  const submitLabel = pending ? 'printerSetup.resumeButton' : targetId ? 'printerSetup.connect' : 'printerSetup.save';

  return <ModalOverlay onClose={close} closeOnOverlayClick={!busy && !confirmKey} closeOnEscape={!busy && !confirmKey}>
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
            <p className="text-sm text-gray-300">{t(observed ? 'printerSetup.observed' : activated ? 'printerSetup.connectionReady' : 'printerSetup.saved')}</p>
            {probe && !activated && <button type="button" className={button} disabled={busy} onClick={() => void save()}>{t('printerSetup.retryConnection')}</button>}
            {system && mode === 'edge'
              ? supportsEdgeSetup(system.provider, system.kind)
                ? <EdgeConnectionSetup printer={current} system={system} />
                : <p role="alert" className="text-sm text-amber-200">{t('printerSetup.edgeUnsupported')}</p>
              : system && mode !== 'manual' && !savedAdapter.link && savedAdapter.renderSetup?.({ printer: current, system, gates: [], spools: [], linkConfirmed: current.reports_feed })}
            {savedAdapter.link && mode !== 'manual' && <div className="space-y-3 rounded-lg border border-white/10 p-3">
              <p className="text-sm">{t(inventoryLinked ? 'printerSetup.inventoryReady' : 'printerSetup.inventoryIncomplete')}</p>
              {!inventoryLinked && !finishInventory && mode !== 'native' && <button type="button" className={button}
                onClick={() => setFinishInventory(true)}>{t('printerSetup.finishInventory')}</button>}
              {!inventoryLinked && (finishInventory || mode === 'native') && <>
              <p className="text-xs text-gray-400">{t('printerSetup.inventorySafety')}</p>
              {savedAdapter.renderCreateHelp?.()}
              {issuedKey ? <LinkInstructions link={savedAdapter.link}
                baseUrl={window.location.origin + '/api/v1/spool_compat'} apiKey={issuedKey} />
                : current.has_api_key ? <><p className="mt-2 text-xs text-gray-400">{t('printerSetup.keyExists')}</p>
                  <button type="button" className={button} disabled={busy} onClick={() => setConfirmKey(true)}>{t('printerSetup.replaceKey')}</button></>
                  : <button type="button" className={button + ' mt-3'} disabled={busy} onClick={() => void issueKey()}>{t('printerSetup.issueKey')}</button>}
              </>}
              {pluginReady && probe?.connection && <button type="button" className={button} disabled={busy}
                onClick={() => void checkInventory()}>{t('printerSetup.checkInventory')}</button>}
            </div>}
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
                <LayeredPrinterIcon className="h-5 w-5 shrink-0 text-purple-300" />
                <span className="min-w-0 flex-1 truncate font-medium" title={printer.name}>{printer.name}</span>
                <span className="max-w-[45%] truncate text-xs text-gray-400" title={detail}>
                  {detail || t('printerSetup.printerNumber', { id: printer.id })}
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
                <LayeredPrinterIcon className="h-5 w-5 shrink-0 text-purple-300" />
                <span className="min-w-0 flex-1 truncate" title={candidate.label}>{candidate.label}</span>
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
                  const model = models?.items.find((item) => item.id === Number(value));
                  chooseModel(model);
                }} options={[...(selectedModel && !models?.items.some((item) => item.id === selectedModel.id) ? [selectedModel] : []),
                  ...(models?.items ?? [])].map((item) => ({ value: item.id, label: item.name }))}
                  placeholder={t('addPrinter.modelPlaceholder')} filterable filterValue={search} onFilterChange={setSearch} />
                <p className="text-xs text-gray-400">{t('printerSetup.modelHint')}</p>
                {(installed ?? []).length > 0 && <details>
                  <summary className="cursor-pointer text-xs text-gray-400">{t('printerSetup.savedModels')}</summary>
                  <p className="my-2 text-xs text-gray-400">{t('printerSetup.savedModelsHint')}</p>
                  <div className="flex flex-wrap gap-2">{(installed ?? []).map((item) => <button key={item.model}
                    type="button" className={button} onClick={() => { chooseModel(models?.items.find((model) => model.id === item.printer_id)); setModelId(item.printer_id ?? 0);
                      setName(item.model); setProfileIds(item.printer_profile_id ? [item.printer_profile_id] : []); }}>{item.model}</button>)}</div>
                </details>}
              </div>}
              {!targetId && <label className="block text-sm">{t('printerSetup.name')}
                <input className={control + ' mt-1'} value={name} maxLength={200} required
                  onChange={(event) => setName(event.target.value)} placeholder={t('printerSetup.namePlaceholder')} />
              </label>}
              {targetId > 0 && <p className="break-words text-sm text-purple-200">{t('printerSetup.keepExisting', { name: selected?.name ?? name })}</p>}
              {!manualSettings && <div className="space-y-3">
                {probe?.ok ? <div role="status" className="rounded-lg bg-emerald-500/10 p-3 text-sm text-emerald-200">
                  {t(probe.provider === 'happy_hare' ? 'printerSetup.detectedHappyHare' : 'printerSetup.probeConnected', { count: probe.gateCount ?? 0 })}
                  {probe.provider === 'happy_hare' && <p className="mt-1 text-xs text-gray-300">{t('printerSetup.inventoryNext')}</p>}
                </div> : <>
                  {connectionChosen && connectionAdapter.onboarding && <p className="text-sm text-gray-300">{t(connectionAdapter.onboarding.connectionHintKey)}</p>}
                  {loadingConnections && <p role="status" className="text-xs text-gray-400">{t('printerSetup.loadingConnections')}</p>}
                  {pluginReady && knownCandidates.length > 1 && knownCandidates.map((candidate) => <button key={candidate.connectionRef}
                    type="button" className={button + ' w-full truncate text-left'} title={candidate.label}
                    onClick={() => { setMode('orca'); setConnectionChosen(true); void inspect(candidate); }}>{candidate.label}</button>)}
                  {pluginReady && knownCandidates.length < 2 && (adapter.onboarding?.orcaProbe || !connectionChosen) && <button type="button" className={button} disabled={busy}
                    onClick={() => { setMode('orca'); setConnectionChosen(true); void inspect(knownCandidates[0]); }}>
                    {t(knownCandidates.length ? 'printerSetup.checkKnown' : 'printerSetup.enterAddress')}
                  </button>}
                  {!pluginReady && connectionChosen && adapter.onboarding?.orcaProbe && <p className="text-xs text-gray-400">{t('printerSetup.withoutLocalAccess')}</p>}
                  {!connectionChosen && <p className="text-xs text-gray-400">{t('printerSetup.manualStart')}</p>}
                </>}
              </div>}
              <details className="rounded-lg border border-white/10 p-3" open={manualSettings}
                onToggle={(event) => setManualSettings(event.currentTarget.open)}>
                <summary className="cursor-pointer text-sm font-medium">{t('printerSetup.connectionOptional')}</summary>
                <div className="mt-3 space-y-3">
                  {(!existingSystem || existingSystem.provider === 'manual') && !probe && <>
                    <Dropdown label={t('printerSetup.connectionType')} value={connectionChosen ? connectionAdapter.id : ''} clearable={false}
                      options={setupAdapters.map((item) => ({ value: item.id, label: t(item.onboarding!.connectionLabelKey) }))}
                      onChange={(value) => {
                        customized.current = true;
                        const keepFeed = String(value) === connectionAdapter.id;
                        if (!keepFeed) changeProvider(String(value));
                        setConnectionChosen(true);
                        if (!keepFeed && existingSystem && value !== existingSystem.provider) { setEditTopology(true); setTopologyBase(existingSystem); }
                        if (!keepFeed || !connectionChosen) setMode(feedAdapterFor(keepFeed ? provider : String(value)).onboarding?.methods[0] ?? 'manual'); }} />
                    {selectedModel && !otherConnection && <button type="button" className="text-xs text-gray-400 underline"
                      onClick={() => setOtherConnection(true)}>{t('printerSetup.otherConnection')}</button>}
                  </>}
                  {connectionChosen && connectionAdapter.onboarding && <p className="text-xs text-gray-400">{t(connectionAdapter.onboarding.connectionHintKey)}</p>}
                  <p className="mb-2 text-sm font-medium">{t('printerSetup.route')}</p>
                  <div className="flex flex-wrap gap-2" role="group" aria-label={t('printerSetup.route')}>
                    {(['manual', ...methods] as const).map((route) => <button key={route} type="button"
                      disabled={route === 'edge' && !edgeAvailable}
                      aria-pressed={mode === route} className={button + (mode === route ? ' border-purple-400 bg-purple-500/20' : '')}
                      onClick={() => { customized.current = true; setMode(route); setProbe(null); setError(null); }}>{t('printerSetup.routes.' + route)}</button>)}
                  </div>
                  {mode === 'manual' && <p className="text-xs text-gray-400">{t('printerSetup.manualHint')}</p>}
                  {mode === 'edge' && <p className="text-xs text-gray-400">{t('printerSetup.edgeHint')}</p>}
                  {mode === 'native' && <p className="text-xs text-gray-400">{t('printerSetup.nativeHint')}</p>}
                  {mode === 'orca' && adapter.onboarding?.orcaProbe && <div className="space-y-2 rounded-lg border border-white/10 p-3">
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
                    {probe?.ok && manualSettings && <div role="status" className="text-sm text-emerald-300">
                      {t(probe.gateCount ? 'printerSetup.probeGates' : 'printerSetup.probeConnected', { count: probe.gateCount ?? undefined })}
                      <p className="mt-1 text-xs text-gray-400">{t('printerSetup.readOnly')}</p>
                    </div>}
                  </div>}
                </div>
              </details>
              {existingSystem && (!probe || probe.provider === 'manual') && !editTopology && <button type="button" className={button} onClick={() => {
                setTopology(topologyFromSystem(topologies, existingSystem)); setEditTopology(true); setTopologyBase(existingSystem);
              }}>{t('printerSetup.feed.edit')}</button>}
              {(!existingSystem || editTopology || provider !== existingSystem.provider) && (!probe || probe.provider === 'manual') && <details className="rounded-lg border border-white/10 p-3"
                open={manualSettings && adapter.topologyFromProvider === true}>
                <summary className="cursor-pointer text-sm font-medium">{t('printerSetup.feed.configure')}</summary>
                <div className="mt-3 space-y-3"><TopologyEditor choices={topologies} value={topology} onChange={changeTopology} />
                  {adapter.onboarding?.connectionProvider && <p className="text-xs text-gray-400">{t(adapter.onboarding.connectionHintKey)}</p>}
                  <p className="text-xs text-gray-400">{t('printerSetup.feed.manualHint')}</p>
                </div>
              </details>}
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
    <ConfirmModal isOpen={confirmKey} onClose={() => { if (!busy) setConfirmKey(false); }}
      onConfirm={() => void issueKey()} isLoading={busy} title={t('printerSetup.replaceKey')}
      message={t('printerSetup.replaceKeyConfirm')} confirmText={t('printerSetup.replaceKey')} />
  </ModalOverlay>;
}
