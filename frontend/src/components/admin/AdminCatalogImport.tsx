import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  KeyRound,
  Loader2,
  RotateCcw,
  Save,
  ScanSearch,
  ShieldCheck,
  Upload,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { AxiosError } from 'axios';

import { adminCatalogCurationAPI, adminCatalogImportAPI } from '../../api/client';
import type {
  CatalogCurationEvidence,
  CatalogCurationInput,
  CatalogCurationPreview,
  CatalogCurationProposal,
  CatalogCurationSourceFact,
  CatalogCurationUnmappedFact,
  CatalogImportDraft,
  CatalogImportPlanRow,
  CatalogImportPreview,
  CatalogImportSheet,
  CatalogQuoteCheckItem,
} from '../../types/api';
import { translateApiError } from '../../utils/translateApiError';
import { countryName } from '../../utils/countries';
import {
  PROPOSAL_SHEETS as SHEETS,
  appendRow,
  applyCellEdits,
  cellText,
  editsCollideKeys,
  fieldSpread,
  groupFilamentMarkets,
  MARKET_CHILD,
  marketIndicesFor,
  previewOutcome,
  removeRowAt,
  rowKey,
  sheetBackendName,
  factCoverageNeedsAttention,
  type CellEdit,
  type ProposalRow,
} from '../../utils/catalogProposalEdit';
import { toast } from '../Toast';
import { ConfirmModal } from '../ConfirmModal';
import { AdminPager } from './AdminPager';
import { CatalogServiceAccounts } from './CatalogServiceAccounts';
import { MARKET_DEFAULT_FIELDS, fieldSpec, type BulkFieldDef } from './catalogProposal/fieldSpecs';
import { Dropdown } from '../Dropdown';
import { BulkEditBar, MarketDefaultsPanel } from './catalogProposal/ProposalBulkTools';
import { ProposalRecordList } from './catalogProposal/ProposalRecordList';
import type { EvidenceApi, FactsApi } from './catalogProposal/VariantEditor';
import { VariantEditor } from './catalogProposal/VariantEditor';

const PROPOSAL_TABS: CatalogImportSheet[] = ['brands', 'filaments', 'presets'];
const PAGE_SIZE = 40;
const PROPOSAL_PAGE_SIZE = 20;
const PROPOSAL_ROW_PAGE_SIZE = 50;

function sortedProposalRows(rows: ProposalRow[], sheet: CatalogImportSheet) {
  const filamentSort = (row: ProposalRow) => [row.brand_key, row.material_type, row.line, row.color_name, row.name]
    .map(cellText).join('\u0000');
  return rows.map((row, index) => ({ row, index })).sort((left, right) => sheet === 'filaments'
    ? filamentSort(left.row).localeCompare(filamentSort(right.row))
    : left.index - right.index);
}

function matchesProposalSearch(row: ProposalRow, sheet: CatalogImportSheet, search: string) {
  const term = search.trim().toLocaleLowerCase();
  return !term || [row.name, row.line, row.material_type, row.color_name, row.color_type, row.finish, row.effects, row.filler,
    row.country, row.availability, row.market_color_name, rowKey(sheet, row)]
    .some((value) => cellText(value).toLocaleLowerCase().includes(term));
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

const barButton = 'inline-flex h-9 items-center justify-center gap-1.5 rounded-lg px-2.5 text-sm font-semibold transition disabled:opacity-40 sm:px-3';

export function AdminCatalogImport() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<CatalogImportPreview | null>(null);
  const [draft, setDraft] = useState<CatalogImportDraft | null>(null);
  const [activeSheet, setActiveSheet] = useState<CatalogImportSheet>('brands');
  const [page, setPage] = useState(1);
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [onlyDiffering, setOnlyDiffering] = useState(false);
  const [marketCountry, setMarketCountry] = useState('all');
  const [defaultsOpen, setDefaultsOpen] = useState(false);
  const [rowSearch, setRowSearch] = useState('');
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proposal, setProposal] = useState<CatalogCurationProposal | null>(null);
  const [title, setTitle] = useState('');
  const [coverageNote, setCoverageNote] = useState('');
  const [showServiceAccounts, setShowServiceAccounts] = useState(false);
  const [evidence, setEvidence] = useState<CatalogCurationEvidence[]>([]);
  const [unmappedFacts, setUnmappedFacts] = useState<CatalogCurationUnmappedFact[]>([]);
  const [sourceFacts, setSourceFacts] = useState<CatalogCurationSourceFact[]>([]);
  const [proposalPage, setProposalPage] = useState(0);
  const [jsonLoading, setJsonLoading] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const readonly = proposal?.status === 'applied';

  const quoteChecksQuery = useQuery({
    queryKey: ['admin-catalog-quote-checks', proposal?.id],
    queryFn: () => adminCatalogCurationAPI.quoteChecks(proposal!.id),
    enabled: proposal !== null,
    // Polls only while a check is queued or running; an idle proposal costs nothing.
    // The interval grows with every update, so a long retry schedule is not hammered.
    refetchInterval: (query) => (query.state.data?.job_pending
      ? Math.min(60_000, 4000 * 1.5 ** Math.max(0, query.state.dataUpdateCount - 1)) : false),
  });
  const quoteSummary = quoteChecksQuery.data?.summary;

  const proposalsQuery = useQuery({
    queryKey: ['admin-catalog-curation', proposalPage],
    queryFn: () => adminCatalogCurationAPI.list(proposalPage * PROPOSAL_PAGE_SIZE, PROPOSAL_PAGE_SIZE),
  });

  const requestError = (value: AxiosError<{ detail: unknown }>) => {
    setError(translateApiError(t, value.response?.data?.detail, t('adminCatalogImport.curation.requestError')));
  };

  const resetNavigation = (sheet: CatalogImportSheet) => {
    setActiveSheet(sheet);
    setPage(1);
    setOpenIndex(null);
    setSelected(new Set());
    setOnlyDiffering(false);
    setMarketCountry('all');
    setDefaultsOpen(false);
    setRowSearch('');
  };

  const loadProposal = (value: CatalogCurationProposal, preserveNavigation = false) => {
    setProposal(value);
    setTitle(value.title);
    setCoverageNote(value.coverage_note);
    setEvidence(value.evidence);
    setUnmappedFacts(value.unmapped_facts ?? []);
    setSourceFacts(value.source_facts ?? []);
    setDraft(value.draft);
    setPreview(null);
    setDirty(false);
    setError(null);
    if (!preserveNavigation) {
      resetNavigation(PROPOSAL_TABS.find((id) => value.draft[id].length > 0) ?? 'brands');
    }
  };

  const openMutation = useMutation({
    mutationFn: adminCatalogCurationAPI.get,
    onSuccess: (value) => loadProposal(value),
    onError: requestError,
  });

  const saveProposal = async (): Promise<CatalogCurationProposal> => {
    if (!draft || !proposal) throw new Error('Missing proposal');
    const sourceUrls = (urls: string[]) => urls.map((url) => url.trim()).filter(Boolean);
    const value = {
      title, draft,
      evidence: evidence.map((item) => ({ ...item, source_urls: sourceUrls(item.source_urls) })),
      unmapped_facts: unmappedFacts.map((item) => ({
        ...item,
        public_action: item.public_action ?? 'none',
        source_urls: sourceUrls(item.source_urls),
      })),
      source_facts: sourceFacts.map((item) => ({ ...item, source_urls: sourceUrls(item.source_urls) })),
      coverage_note: coverageNote,
    };
    return adminCatalogCurationAPI.update(proposal.id, proposal.revision, value);
  };

  const verifySourcesMutation = useMutation({
    mutationFn: () => {
      if (!proposal) throw new Error('Missing proposal');
      return adminCatalogCurationAPI.verifySources(proposal.id);
    },
    onSuccess: (report) => {
      queryClient.setQueryData(['admin-catalog-quote-checks', proposal?.id], report);
      setError(null);
    },
    onError: requestError,
  });

  const saveMutation = useMutation({
    mutationFn: saveProposal,
    onSuccess: (value) => {
      loadProposal(value, true);
      queryClient.invalidateQueries({ queryKey: ['admin-catalog-curation'] });
      queryClient.invalidateQueries({ queryKey: ['admin-catalog-quote-checks'] });
      toast.success(t('adminCatalogImport.curation.saved'));
    },
    onError: requestError,
  });

  const proposalPreviewMutation = useMutation({
    mutationFn: async () => {
      setPreview(null);
      if (!proposal) throw new Error('Missing proposal');
      const saved = dirty ? await saveProposal() : proposal;
      setProposal(saved);
      setDirty(false);
      queryClient.invalidateQueries({ queryKey: ['admin-catalog-curation'] });
      return adminCatalogCurationAPI.preview(saved.id, saved.revision);
    },
    onSuccess: (value) => {
      setDraft(value.draft);
      setPreview(value);
      setError(null);
    },
    onError: requestError,
  });

  const historyQuery = useQuery({
    queryKey: ['admin-catalog-import-history'],
    queryFn: adminCatalogImportAPI.history,
  });

  const templateMutation = useMutation({
    mutationFn: adminCatalogImportAPI.downloadTemplate,
    onSuccess: (blob) => downloadBlob(blob, 'filamenthub-catalog-import.xlsx'),
    onError: () => toast.error(t('adminCatalogImport.templateError')),
  });

  const uploadMutation = useMutation({
    mutationFn: adminCatalogImportAPI.previewWorkbook,
    onSuccess: (result) => {
      setProposal(null);
      setEvidence([]);
      setUnmappedFacts([]);
      setSourceFacts([]);
      setTitle(result.draft.filename);
      setCoverageNote('');
      setPreview(result);
      setDraft(result.draft);
      setDirty(false);
      setError(null);
      resetNavigation(SHEETS.find((sheet) => result.draft[sheet.id].length > 0)?.id ?? 'brands');
    },
    onError: (requestError: AxiosError<{ detail: unknown }>) => {
      setError(
        translateApiError(
          t,
          requestError.response?.data?.detail,
          t('adminCatalogImport.previewError'),
        ),
      );
    },
  });

  const revalidateMutation = useMutation({
    mutationFn: adminCatalogImportAPI.previewDraft,
    onSuccess: (result) => {
      setPreview(result);
      setDraft(result.draft);
      setDirty(false);
      setError(null);
    },
    onError: (requestError: AxiosError<{ detail: unknown }>) => {
      setError(
        translateApiError(
          t,
          requestError.response?.data?.detail,
          t('adminCatalogImport.previewError'),
        ),
      );
    },
  });

  const applyMutation = useMutation({
    mutationFn: ({ value, token }: { value: CatalogImportDraft; token: string }) =>
      proposal ? adminCatalogCurationAPI.apply(proposal.id, proposal.revision, token)
        : adminCatalogImportAPI.apply(value, token),
    onSuccess: (result) => {
      toast.success(t('adminCatalogImport.applied', { id: result.batch_id }));
      setPreview(null);
      setDraft(null);
      setDirty(false);
      setError(null);
      setProposal(null);
      setEvidence([]);
      queryClient.invalidateQueries({ queryKey: ['admin-catalog-curation'] });
      queryClient.invalidateQueries({ queryKey: ['admin-catalog-import-history'] });
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] });
      queryClient.invalidateQueries({ queryKey: ['admin-brands'] });
      queryClient.invalidateQueries({ queryKey: ['admin-filaments'] });
      queryClient.invalidateQueries({ queryKey: ['admin-presets'] });
    },
    onError: (requestError: AxiosError<{ detail: unknown }>) => {
      setError(
        translateApiError(
          t,
          requestError.response?.data?.detail,
          t('adminCatalogImport.applyError'),
        ),
      );
    },
  });

  const busy = openMutation.isPending || saveMutation.isPending || proposalPreviewMutation.isPending
    || uploadMutation.isPending || revalidateMutation.isPending || applyMutation.isPending || jsonLoading;

  const importJson = async (file: File) => {
    setJsonLoading(true);
    try {
      if (file.size > 5 * 1024 * 1024) throw new Error('Invalid proposal file');
      const value: CatalogCurationInput = JSON.parse(await file.text());
      if (!value || typeof value.title !== 'string' || !value.draft
        || typeof value.draft !== 'object' || Array.isArray(value.draft)
        || !SHEETS.every((sheet) => value.draft[sheet.id] === undefined || Array.isArray(value.draft[sheet.id]))
        || !Array.isArray(value.evidence)
        || (value.unmapped_facts !== undefined && !Array.isArray(value.unmapped_facts))
        || (value.source_facts !== undefined && !Array.isArray(value.source_facts))
        || typeof value.coverage_note !== 'string') {
        throw new Error('Invalid proposal file');
      }
      const normalizedDraft = { ...value.draft };
      for (const sheet of SHEETS) normalizedDraft[sheet.id] ??= [];
      const created = await adminCatalogCurationAPI.create({
        title: value.title, draft: normalizedDraft, evidence: value.evidence,
        unmapped_facts: value.unmapped_facts ?? [], source_facts: value.source_facts ?? [],
        coverage_note: value.coverage_note,
      });
      loadProposal(created);
      queryClient.invalidateQueries({ queryKey: ['admin-catalog-curation'] });
    } catch (value) {
      const axiosError = value as AxiosError<{ detail: unknown }>;
      setError(translateApiError(t, axiosError.response?.data?.detail, t('adminCatalogImport.curation.jsonError')));
    } finally {
      setJsonLoading(false);
    }
  };

  const activeDefinition = SHEETS.find((sheet) => sheet.id === activeSheet) ?? SHEETS[0];
  const activeRows = draft?.[activeSheet] ?? [];
  const columns = useMemo(() => {
    const ordered: string[] = [];
    for (const row of activeRows) {
      for (const key of Object.keys(row)) {
        if (key !== '_row' && !ordered.includes(key)) ordered.push(key);
      }
    }
    if (!ordered.includes('enabled')) ordered.unshift('enabled');
    return ordered;
  }, [activeRows]);
  const totalPages = Math.max(1, Math.ceil(activeRows.length / PAGE_SIZE));
  const visibleRows = activeRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const language = i18n?.language ?? 'en';
  const childDef = MARKET_CHILD[activeSheet];
  const childRows = childDef && draft ? draft[childDef.sheet] : [];
  /** Countries present in the market rows, most rows first. */
  const marketCountries = useMemo(() => {
    const counts = new Map<string, number>();
    for (const row of childRows) {
      const code = cellText(row.country).trim().toUpperCase();
      if (code) counts.set(code, (counts.get(code) ?? 0) + 1);
    }
    return [...counts.entries()]
      .map(([code, total]) => ({ code, total, name: countryName(code, language) }))
      .sort((left, right) => right.total - left.total || left.name.localeCompare(right.name, language));
  }, [childRows, language]);
  const shownCountry = marketCountry !== 'all' && marketCountries.some((item) => item.code === marketCountry) ? marketCountry : 'all';
  const marketGroups = useMemo(
    () => (draft && activeSheet === 'filaments'
      ? groupFilamentMarkets(draft).filter((group) => shownCountry === 'all' || group.country === shownCountry) : []),
    [draft, activeSheet, shownCountry],
  );
  const marketExceptions = useMemo(() => {
    const result = new Set<number>();
    if (!draft) return result;
    for (const group of marketGroups) {
      for (const field of MARKET_DEFAULT_FIELDS) {
        for (const index of fieldSpread(draft.filament_markets, group.indices, field).exceptions) result.add(index);
      }
    }
    return result;
  }, [draft, marketGroups]);
  /** Filaments that have a market row differing from its country's shared value. */
  const differs = useMemo(() => {
    const result = new Set<number>();
    if (!draft || activeSheet !== 'filaments') return result;
    draft.filaments.forEach((row, index) => {
      if (marketIndicesFor(draft, 'filaments', rowKey('filaments', row)).some((marketIndex) => marketExceptions.has(marketIndex))) result.add(index);
    });
    return result;
  }, [draft, activeSheet, marketExceptions]);
  const marketCells = (row: ProposalRow) => {
    if (!draft || !childDef) return [];
    const spec = fieldSpec(childDef.sheet, 'availability');
    return marketIndicesFor(draft, activeSheet, rowKey(activeSheet, row))
      .map((marketIndex) => draft[childDef.sheet][marketIndex])
      .filter((market) => shownCountry === 'all' || cellText(market.country).toUpperCase() === shownCountry)
      .map((market) => {
        const code = cellText(market.availability);
        return {
          country: cellText(market.country).toUpperCase(),
          text: code && activeSheet === 'filaments' ? t(`${spec.optionsKey}${code}`, { defaultValue: code }) : '',
        };
      });
  };
  const proposalRows = useMemo(
    () => sortedProposalRows(activeRows, activeSheet)
      .filter(({ row }) => matchesProposalSearch(row, activeSheet, rowSearch))
      .filter(({ index }) => !onlyDiffering || differs.has(index)),
    [activeRows, activeSheet, rowSearch, onlyDiffering, differs],
  );
  // Only what the current search, country and filter still list counts as selected.
  const selectedVisible = useMemo(() => {
    const listed = new Set(proposalRows.map(({ index }) => index));
    return new Set([...selected].filter((index) => listed.has(index)));
  }, [selected, proposalRows]);
  useEffect(() => {
    if (selectedVisible.size !== selected.size) setSelected(selectedVisible);
  }, [selected, selectedVisible]);
  // A filter that matches nothing any more would leave an empty list with no way back.
  useEffect(() => {
    if (onlyDiffering && differs.size === 0) setOnlyDiffering(false);
  }, [onlyDiffering, differs]);
  const singleBrand = Boolean(proposal) && activeSheet === 'brands' && activeRows.length === 1;
  const currentIndex = singleBrand ? 0 : openIndex;
  const openRow = currentIndex !== null ? activeRows[currentIndex] : undefined;
  const openKey = openRow ? rowKey(activeSheet, openRow) : '';
  const planByRow = useMemo(() => {
    const map = new Map<number, CatalogImportPlanRow>();
    for (const row of preview?.rows ?? []) {
      if (row.sheet === activeDefinition.backendName) map.set(row.row, row);
    }
    if (proposal && childDef) {
      // A market error is shown on the record that owns the market.
      const childBackend = sheetBackendName(childDef.sheet);
      const ownerIndex = new Map(activeRows.map((row, index) => [rowKey(activeSheet, row), index] as const));
      for (const row of preview?.rows ?? []) {
        if (row.sheet !== childBackend || row.status !== 'error' || !row.key) continue;
        const index = ownerIndex.get(row.key.slice(0, row.key.lastIndexOf(':')));
        if (index === undefined) continue;
        const rowNumber = Number(activeRows[index]._row ?? index + 2);
        if (map.get(rowNumber)?.status === 'error') continue;
        map.set(rowNumber, {
          sheet: activeDefinition.backendName, row: rowNumber, key: rowKey(activeSheet, activeRows[index]),
          status: 'error', message: `${row.key}: ${row.message ?? ''}`, changes: {},
        });
      }
    }
    return map;
  }, [activeDefinition.backendName, activeRows, activeSheet, childDef, preview?.rows, proposal]);
  const errorRows = useMemo(() => (preview?.rows ?? []).filter((row) => row.status === 'error'), [preview?.rows]);
  const marketErrors = useMemo(
    () => (childDef ? errorRows.filter((row) => row.sheet === sheetBackendName(childDef.sheet)) : []),
    [childDef, errorRows],
  );
  const errorsOnTab = (sheetId: CatalogImportSheet) => {
    const backendName = sheetBackendName(sheetId);
    return errorRows.filter((row) => row.sheet === backendName
      || (proposal !== null && ((backendName === 'Filaments' && row.sheet === 'FilamentMarkets')
        || (backendName === 'Brands' && row.sheet === 'BrandMarkets')))).length;
  };
  const evidenceByField = useMemo(() => {
    const map = new Map<string, Array<{ item: CatalogCurationEvidence; index: number }>>();
    evidence.forEach((item, index) => {
      const key = JSON.stringify([item.sheet, item.key, item.field]);
      const entries = map.get(key) ?? [];
      entries.push({ item, index });
      map.set(key, entries);
    });
    return map;
  }, [evidence]);
  const factCoverageByFilament = useMemo(() => {
    const result = new Map<string, { total: number; mapped: number; unsupported: number; unresolved: number }>();
    for (const fact of sourceFacts) {
      const entry = result.get(fact.filament_key) ?? { total: 0, mapped: 0, unsupported: 0, unresolved: 0 };
      entry.total += 1;
      if (fact.disposition === 'mapped') entry.mapped += 1;
      if (fact.disposition === 'unsupported' && unmappedFacts.some((note) =>
        note.filament_key === fact.filament_key
        && note.property_name.trim().toLocaleLowerCase() === fact.property_name.trim().toLocaleLowerCase()
        && note.value_summary.trim().toLocaleLowerCase() === fact.value_summary.trim().toLocaleLowerCase()
      )) entry.unsupported += 1;
      if (fact.disposition === 'unresolved') entry.unresolved += 1;
      result.set(fact.filament_key, entry);
    }
    return result;
  }, [sourceFacts, unmappedFacts]);
  const reviewedFactsByFilament = useMemo(() => new Map(
    (preview && !dirty && 'source_facts_review' in preview
      ? (preview as CatalogCurationPreview).source_facts_review : [])
      .map((item) => [item.filament_key, item] as const),
  ), [preview, dirty]);
  const coverageOf = (key: string) => reviewedFactsByFilament.get(key) ?? factCoverageByFilament.get(key);

  /** The single write path for field edits: single, bulk and market defaults all come through here. */
  const editRows = (sheet: CatalogImportSheet, edits: CellEdit[]) => {
    if (!draft) return;
    applyState(applyCellEdits({ draft, evidence, sourceFacts, unmappedFacts }, sheet, edits));
  };

  const applyState = (next: ReturnType<typeof applyCellEdits>) => {
    if (!draft || next.draft === draft) return;
    setDraft(next.draft);
    setEvidence(next.evidence);
    setSourceFacts(next.sourceFacts);
    setUnmappedFacts(next.unmappedFacts);
    setDirty(true);
  };
  const addMarketRow = (sheet: CatalogImportSheet, row: ProposalRow) => {
    if (draft) applyState(appendRow({ draft, evidence, sourceFacts, unmappedFacts }, sheet, row));
  };
  const removeMarketRow = (sheet: CatalogImportSheet, index: number) => {
    if (draft) applyState(removeRowAt({ draft, evidence, sourceFacts, unmappedFacts }, sheet, index));
  };

  const bulkEdits = (def: BulkFieldDef, value: unknown, countries: string[] | null): { sheet: CatalogImportSheet; edits: CellEdit[] } => {
    if (def.market && childDef && draft) {
      const allowed = new Set(countries ?? []);
      return {
        sheet: childDef.sheet,
        edits: [...selectedVisible].flatMap((index) => marketIndicesFor(draft, activeSheet, rowKey(activeSheet, activeRows[index]))
          .filter((marketIndex) => allowed.has(cellText(draft[childDef.sheet][marketIndex].country).trim().toUpperCase()))
          .map((marketIndex) => ({ index: marketIndex, field: def.field, value }))),
      };
    }
    return { sheet: activeSheet, edits: [...selectedVisible].map((index) => ({ index, field: def.field, value })) };
  };

  const bulkApply = (def: BulkFieldDef, value: unknown, countries: string[] | null) => {
    if (!draft) return;
    const { sheet, edits } = bulkEdits(def, value, countries);
    if (edits.length === 0) {
      toast.warning(t('adminCatalogImport.curation.bulkNothingChanged'));
      return;
    }
    if (editsCollideKeys(draft[sheet], sheet, edits)) {
      setError(t('adminCatalogImport.curation.bulkCollision'));
      return;
    }
    setError(null);
    editRows(sheet, edits);
    toast.success(t('adminCatalogImport.curation.bulkApplied', { count: edits.length }));
  };

  const bulkTargetCount = (def: BulkFieldDef, countries: string[] | null) => bulkEdits(def, '', countries).edits.length;

  const updateSelection = (indices: number[], checked: boolean) => setSelected((current) => {
    const next = new Set(current);
    for (const index of indices) {
      if (checked) next.add(index);
      else next.delete(index);
    }
    return next;
  });

  const confirmImageMutation = useMutation({
    mutationFn: (claim: { sheet: string; key: string; field: string; confirmed: boolean }) => {
      if (!proposal) throw new Error('Missing proposal');
      return adminCatalogCurationAPI.confirmImageClaim(proposal.id, { scope: 'evidence', ...claim });
    },
    onSuccess: (report) => {
      queryClient.setQueryData(['admin-catalog-quote-checks', proposal?.id], report);
      // The confirmation changes what may be applied, so the earlier preview is stale.
      setPreview(null);
      setError(null);
    },
    onError: requestError,
  });

  const quoteCheckByField = useMemo(() => {
    const map = new Map<string, CatalogQuoteCheckItem>();
    for (const item of quoteChecksQuery.data?.items ?? []) {
      if (item.scope === 'evidence') map.set(JSON.stringify([item.sheet, item.key, item.field]), item);
    }
    return map;
  }, [quoteChecksQuery.data]);

  const evidenceApi: EvidenceApi = {
    checkFor: (sheet, key, field) => {
      const id = JSON.stringify([sheetBackendName(sheet), key, field]);
      const listed = quoteCheckByField.get(id);
      if (!quoteChecksQuery.data) return listed;
      const cited = evidenceByField.get(id)?.[0]?.item;
      const saved = proposal?.evidence.find((item) => item.sheet === sheetBackendName(sheet) && item.key === key && item.field === field);
      // The server judged the saved quote; an edited or unsaved one has no verdict yet.
      const quoteChanged = (cited?.quote ?? null) !== (saved?.quote ?? null);
      const pending: CatalogQuoteCheckItem = {
        scope: 'evidence', sheet: sheetBackendName(sheet), key, field, status: 'pending',
        reason: null, url: null, checked_at: null, confirmed: false, gating: true,
      };
      if (listed) return quoteChanged ? pending : listed;
      // Verified claims are not listed: a cited quote with no entry has been verified.
      return cited?.quote ? { ...pending, status: dirty || quoteChanged ? 'pending' : 'verified' } : undefined;
    },
    confirmImage: (sheet, key, field, confirmed) => confirmImageMutation.mutate({ sheet: sheetBackendName(sheet), key, field, confirmed }),
    forField: (sheet, key, field) => evidenceByField.get(JSON.stringify([sheetBackendName(sheet), key, field])) ?? [],
    add: (sheet, key, field) => {
      // The server accepts one entry per field.
      setEvidence((items) => items.some((item) => item.sheet === sheetBackendName(sheet) && item.key === key && item.field === field)
        ? items : [...items, { sheet: sheetBackendName(sheet), key, field, kind: 'direct', source_urls: [] }]);
      setDirty(true);
    },
    update: (index, changes) => {
      setEvidence((rows) => rows.map((row, i) => i === index ? { ...row, ...changes } : row));
      setDirty(true);
    },
    remove: (index) => {
      setEvidence((items) => items.filter((_, i) => i !== index));
      setDirty(true);
    },
  };

  const factsApi: FactsApi | null = activeSheet === 'filaments' ? {
    facts: sourceFacts.map((item, index) => ({ item, index })).filter(({ item }) => item.filament_key === openKey),
    unmapped: unmappedFacts.map((item, index) => ({ item, index })).filter(({ item }) => item.filament_key === openKey),
    onUpdateSourceFact: (index, changes) => {
      setSourceFacts((rows) => rows.map((row, i) => i === index ? { ...row, ...changes } : row));
      setDirty(true);
    },
    onRemoveSourceFact: (index) => {
      setSourceFacts((rows) => rows.filter((_, i) => i !== index));
      setDirty(true);
    },
    onAddSourceFact: () => {
      setSourceFacts((rows) => [...rows, {
        filament_key: openKey, property_name: '', value_summary: '', source_urls: [], disposition: 'unresolved', mapped_fields: [],
      }]);
      setDirty(true);
    },
    onUpdateUnmappedFact: (index, changes) => {
      setUnmappedFacts((rows) => rows.map((row, i) => i === index ? { ...row, ...changes } : row));
      setDirty(true);
    },
    onRemoveUnmappedFact: (index) => {
      setUnmappedFacts((rows) => rows.filter((_, i) => i !== index));
      setDirty(true);
    },
    onAddUnmappedFact: () => {
      setUnmappedFacts((rows) => [...rows, {
        filament_key: openKey, property_name: '', value_summary: '', source_urls: [], explanation: '',
      }]);
      setDirty(true);
    },
  } : null;

  const cancel = () => {
    setPreview(null);
    setDraft(null);
    setDirty(false);
    setError(null);
    setPage(1);
    setOpenIndex(null);
    setSelected(new Set());
    setProposal(null);
    setEvidence([]);
    setUnmappedFacts([]);
    setSourceFacts([]);
    setTitle('');
    setCoverageNote('');
  };

  const requestClose = () => {
    if (proposal && dirty) { setConfirmDiscard(true); return; }
    cancel();
  };

  const checked = preview && !dirty ? preview : null;
  const outcome = previewOutcome(checked);
  const applyReady = Boolean(checked?.confirmation_token) && (checked?.summary.error ?? 0) === 0;
  const applyLabel = (() => {
    if (!outcome) return t('adminCatalogImport.apply');
    const list = (kind: 'create' | 'update') => (['brands', 'filaments', 'presets'] as const)
      .filter((name) => outcome[name][kind] > 0)
      .map((name) => name === 'brands' && outcome[name][kind] === 1
        ? t('adminCatalogImport.curation.outcome.brandOne')
        : t(`adminCatalogImport.curation.outcome.${name}`, { count: outcome[name][kind] }));
    const inCountries = outcome.countries > 1 ? ` ${t('adminCatalogImport.curation.outcome.countries', { count: outcome.countries })}` : '';
    const join = (items: string[]) => typeof Intl.ListFormat === 'function'
      ? new Intl.ListFormat(i18n?.language ?? 'en', { style: 'long', type: 'conjunction' }).format(items) : items.join(', ');
    const created = list('create');
    const updated = list('update');
    if (created.length && updated.length) {
      return t('adminCatalogImport.curation.outcome.both', { created: join(created), updated: join(updated) }) + inCountries;
    }
    if (created.length) return t('adminCatalogImport.curation.outcome.create', { list: join(created) }) + inCountries;
    if (updated.length) return t('adminCatalogImport.curation.outcome.update', { list: join(updated) }) + inCountries;
    return t('adminCatalogImport.apply');
  })();

  const editorCoverage = (() => {
    if (activeSheet !== 'filaments') return null;
    const factCoverage = coverageOf(openKey);
    return <p className={`mt-2 rounded-lg px-2.5 py-1.5 text-xs ${factCoverageNeedsAttention(factCoverage) || !factCoverage?.total ? 'bg-amber-500/10 text-amber-200' : 'bg-white/5 text-gray-300'}`}>
      {factCoverage?.total ? t('adminCatalogImport.curation.sourceFactCoverage', {
        captured: factCoverage.mapped + factCoverage.unsupported, mapped: factCoverage.mapped,
        unsupported: factCoverage.unsupported, unresolved: factCoverage.unresolved, total: factCoverage.total,
        percent: Math.floor(((factCoverage.mapped + factCoverage.unsupported) / factCoverage.total) * 100),
      }) : t('adminCatalogImport.curation.sourceFactMissing')}
    </p>;
  })();

  return (
    <div className={proposal ? 'space-y-3' : 'space-y-6'}>
      {!proposal && <header>
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-indigo-300">
          <FileSpreadsheet className="h-4 w-4" />
          {t('adminCatalogImport.eyebrow')}
        </div>
        <h2 className="text-2xl font-bold text-white">{t('adminCatalogImport.title')}</h2>
        {!draft && <p className="mt-1 max-w-3xl text-sm leading-6 text-gray-400">{t('adminCatalogImport.description')}</p>}
      </header>}

      {!draft && (
        <section className="space-y-3 rounded-2xl border border-white/10 bg-black/15 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="font-semibold text-white">{t('adminCatalogImport.curation.title')}</h3>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => setShowServiceAccounts(true)}
                className="inline-flex items-center gap-2 rounded-lg border border-white/20 px-3 py-2 text-sm text-gray-200 hover:bg-white/10">
                <KeyRound className="h-4 w-4" />
                {t('adminCatalogImport.serviceAccounts.title')}
              </button>
              <label className={`inline-flex items-center gap-2 rounded-lg bg-indigo-500 px-3 py-2 text-sm text-white ${busy ? 'pointer-events-none opacity-40' : 'cursor-pointer'}`}>
                <Upload className="h-4 w-4" />
                {t('adminCatalogImport.curation.importJson')}
                <input type="file" accept=".json,application/json" className="sr-only" disabled={busy}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void importJson(file);
                    event.target.value = '';
                  }} />
              </label>
            </div>
          </div>
          <p className="text-xs leading-5 text-gray-400">{t('adminCatalogImport.curation.hint')}</p>
          {proposalsQuery.isLoading && <Loader2 className="h-4 w-4 animate-spin text-gray-400" />}
          {proposalsQuery.isError && (
            <button type="button" onClick={() => void proposalsQuery.refetch()} className="text-sm text-red-300">
              {t('adminCatalogImport.curation.listError')}
            </button>
          )}
          {(proposalsQuery.data?.items.length ?? 0) > 0 && <div className="divide-y divide-white/5 overflow-hidden rounded-xl border border-white/10">
            {proposalsQuery.data?.items.map((item) => (
              <button key={item.id} type="button" disabled={busy} onClick={() => openMutation.mutate(item.id)}
                className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-0.5 px-3 py-2 text-left transition hover:bg-white/5 disabled:opacity-40 sm:grid-cols-[minmax(0,1fr)_8rem_9rem_8rem]">
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-white">{item.brand_name || item.title}</span>
                  <span className="block truncate text-xs text-gray-500">#{item.id} · {item.title}</span>
                </span>
                <span className="text-xs text-gray-300 sm:text-sm">
                  {t('adminCatalogImport.curation.filamentsCount', { count: item.filament_count ?? 0 })}
                </span>
                <span className="hidden truncate text-xs text-gray-400 sm:block">
                  {item.author_name ?? t('adminCatalogImport.curation.authorAdmin')}
                </span>
                <span className="hidden text-right text-xs text-gray-500 sm:block">
                  {t(`adminCatalogImport.curation.status.${item.status}`)} · {t('adminCatalogImport.curation.revision', { revision: item.revision })}
                </span>
              </button>
            ))}
          </div>}
          <div className="flex justify-end">
            <AdminPager page={proposalPage + 1} totalPages={Math.ceil((proposalsQuery.data?.total ?? 0) / PROPOSAL_PAGE_SIZE)}
              onPageChange={(value) => setProposalPage(value - 1)} disabled={busy}
              label={t('adminCatalogImport.curation.title')}
              previousLabel={t('adminCatalogImport.curation.previous')} nextLabel={t('adminCatalogImport.curation.next')} />
          </div>
        </section>
      )}

      {!draft && showServiceAccounts && <CatalogServiceAccounts onClose={() => setShowServiceAccounts(false)} />}

      {!draft && (
        <section className="grid gap-4 md:grid-cols-2">
          <button
            type="button"
            onClick={() => templateMutation.mutate()}
            disabled={templateMutation.isPending}
            className="flex items-center gap-3 rounded-2xl border border-indigo-400/20 bg-indigo-500/10 p-5 text-left transition hover:bg-indigo-500/15 disabled:opacity-50"
          >
            <Download className="h-6 w-6 text-indigo-300" />
            <span>
              <span className="block font-semibold text-white">{t('adminCatalogImport.downloadTemplate')}</span>
              <span className="mt-1 block text-xs text-gray-400">{t('adminCatalogImport.templateHint')}</span>
            </span>
          </button>
          <label className="flex cursor-pointer items-center gap-3 rounded-2xl border border-cyan-400/20 bg-cyan-500/10 p-5 transition hover:bg-cyan-500/15">
            {uploadMutation.isPending ? (
              <Loader2 className="h-6 w-6 animate-spin text-cyan-300" />
            ) : (
              <Upload className="h-6 w-6 text-cyan-300" />
            )}
            <span>
              <span className="block font-semibold text-white">{t('adminCatalogImport.upload')}</span>
              <span className="mt-1 block text-xs text-gray-400">{t('adminCatalogImport.uploadHint')}</span>
            </span>
            <input
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              className="sr-only"
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) uploadMutation.mutate(file);
                event.target.value = '';
              }}
            />
          </label>
        </section>
      )}

      {draft && proposal && (
        <div className="sticky top-2 z-30 flex min-h-14 items-center gap-2 rounded-xl border border-white/15 bg-white/10 px-2.5 py-1.5 shadow-lg shadow-black/20 backdrop-blur-md sm:gap-3 sm:px-3">
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-sm font-bold text-white sm:text-base" title={title}>{title}</h2>
            <div className="flex min-w-0 items-center gap-2">
              <p className="hidden truncate text-xs text-indigo-200 sm:block">
                #{proposal.id} · {t(`adminCatalogImport.curation.status.${proposal.status}`)} · {t('adminCatalogImport.curation.revision', { revision: proposal.revision })}
              </p>
              <span className={`truncate rounded-full px-2 py-0.5 text-[11px] font-semibold ${!dirty && errorRows.length > 0 ? '' : 'hidden sm:inline'} ${dirty ? 'bg-amber-500/15 text-amber-200' : errorRows.length > 0 ? 'bg-red-500/15 text-red-200' : preview?.confirmation_token ? 'bg-emerald-500/15 text-emerald-200' : 'bg-white/10 text-gray-300'}`}>
                {dirty ? t('adminCatalogImport.curation.unsaved') : errorRows.length > 0 ? t('adminCatalogImport.curation.errorsCount', { count: errorRows.length }) : preview?.confirmation_token ? t('adminCatalogImport.curation.readyToApply') : t('adminCatalogImport.curation.previewNeeded')}
              </span>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <button type="button" disabled={busy} onClick={requestClose} aria-label={t('adminCatalogImport.curation.close')} title={t('adminCatalogImport.curation.close')}
              className={`${barButton} border border-white/15 text-gray-300 hover:bg-white/10`}>
              <X className="h-4 w-4" />
            </button>
            <button type="button" disabled={busy || readonly || !title.trim() || !coverageNote.trim() || !dirty}
              onClick={() => saveMutation.mutate()} aria-label={t('adminCatalogImport.curation.saveShort')} title={t('adminCatalogImport.curation.saveShort')}
              className={`${barButton} border border-indigo-400/40 text-indigo-200 hover:bg-indigo-500/10`}>
              {saveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              <span className="hidden xl:inline">{t('adminCatalogImport.curation.saveShort')}</span>
            </button>
            {quoteSummary && quoteSummary.total > 0 && <button type="button" aria-label={t('adminCatalogImport.curation.verifySources')}
              title={t('adminCatalogImport.curation.verifySourcesHint')}
              disabled={busy || readonly || dirty || verifySourcesMutation.isPending || quoteChecksQuery.data?.job_pending === true}
              onClick={() => verifySourcesMutation.mutate()}
              className={`${barButton} border border-cyan-400/40 text-cyan-200 hover:bg-cyan-500/10`}>
              {verifySourcesMutation.isPending || quoteChecksQuery.data?.job_pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
              <span className="hidden xl:inline">{t('adminCatalogImport.curation.verifySources')}</span>
              <span className="rounded-full bg-white/10 px-1.5 py-0.5 text-[11px] font-semibold text-gray-100">
                {t('adminCatalogImport.curation.verifySourcesSummary', { verified: quoteSummary.verified, total: quoteSummary.total })}
              </span>
            </button>}
            <button type="button" aria-label={t('adminCatalogImport.curation.previewAction')} title={t('adminCatalogImport.curation.previewAction')}
              disabled={busy || readonly} onClick={() => proposalPreviewMutation.mutate()}
              className={`${barButton} bg-blue-500 text-white hover:bg-blue-400`}>
              {proposalPreviewMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanSearch className="h-4 w-4" />}
              <span className="hidden lg:inline">{t('adminCatalogImport.curation.previewAction')}</span>
            </button>
            <button type="button" disabled={busy || readonly || !applyReady} aria-label={applyLabel} title={applyLabel}
              onClick={() => { if (draft && preview?.confirmation_token) applyMutation.mutate({ value: draft, token: preview.confirmation_token }); }}
              className={`${barButton} bg-emerald-500 text-slate-950 hover:bg-emerald-400`}>
              {applyMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
              <span className="hidden max-w-[20rem] truncate xl:inline">{applyLabel}</span>
              <span className="hidden sm:inline xl:hidden">{t('adminCatalogImport.apply')}</span>
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {draft && (
        <>
          {proposal && errorRows.length > 0 && <details className="rounded-xl border border-red-400/20 bg-red-500/[0.07] px-3 py-2">
            <summary className="cursor-pointer text-sm font-semibold text-red-200">
              {t('adminCatalogImport.curation.errorsCount', { count: errorRows.length })}
            </summary>
            <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-xs text-red-200">
              {errorRows.map((row) => <li key={`${row.sheet}-${row.row}-${row.key ?? ''}`}>
                {t(`adminCatalogImport.sheets.${(SHEETS.find((sheet) => sheet.backendName === row.sheet) ?? SHEETS[0]).labelKey}`)}
                {' · '}{row.key || `#${row.row}`}{row.message ? `: ${row.message}` : ''}
              </li>)}
            </ul>
          </details>}
          {proposal && <details className="rounded-xl border border-amber-400/20 bg-amber-500/[0.07] px-3 py-2">
            <summary className="cursor-pointer truncate text-sm font-semibold text-amber-100">
              {t('adminCatalogImport.curation.brandResearchNote')}
              <span className="ml-2 hidden font-normal text-gray-300 sm:inline">{coverageNote.length > 110 ? `${coverageNote.slice(0, 110)}…` : coverageNote}</span>
            </summary>
            <fieldset disabled={busy || readonly} className="min-w-0 disabled:opacity-70">
              <label className="mt-3 block text-sm text-gray-300">
                {t('adminCatalogImport.curation.name')}
                <input value={title} maxLength={255} onChange={(event) => { setTitle(event.target.value); setDirty(true); }} className="mt-1 block w-full max-w-2xl rounded-lg border border-white/15 bg-black/20 p-2 text-white" />
              </label>
              <label className="mt-3 block text-sm text-gray-300">
                {t('adminCatalogImport.curation.coverage')}
                <textarea value={coverageNote} maxLength={10000} rows={4} onChange={(event) => { setCoverageNote(event.target.value); setDirty(true); }} className="mt-1 block w-full rounded-lg border border-white/15 bg-black/20 p-2 text-white" />
              </label>
            </fieldset>
          </details>}
          {!proposal && <section className="rounded-2xl border border-white/10 bg-black/15 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="font-semibold text-white">{draft.filename}</div>
                <div className="mt-1 text-xs text-gray-400">{t('adminCatalogImport.noWriteBeforeApply')}</div>
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                {preview && (['create', 'update', 'noop', 'skipped', 'error'] as const).map((status) => (
                  <span
                    key={status}
                    className={`rounded-full px-2.5 py-1 font-semibold ${
                      status === 'error'
                        ? 'bg-red-500/15 text-red-300'
                        : status === 'create'
                          ? 'bg-emerald-500/15 text-emerald-300'
                          : status === 'update'
                            ? 'bg-blue-500/15 text-blue-300'
                            : 'bg-white/10 text-gray-300'
                    }`}
                  >
                    {t(`adminCatalogImport.status.${status}`)}: {preview.summary[status]}
                  </span>
                ))}
              </div>
            </div>
          </section>}

          <nav className="flex gap-2 overflow-x-auto pb-1">
            {SHEETS.filter((sheet) => !proposal || (PROPOSAL_TABS.includes(sheet.id) && draft[sheet.id].length > 0)).map((sheet) => (
              <button
                key={sheet.id}
                type="button"
                onClick={() => resetNavigation(sheet.id)}
                className={`shrink-0 rounded-lg px-3 py-2 text-xs font-semibold transition ${
                  activeSheet === sheet.id
                    ? 'bg-indigo-500 text-white'
                    : 'bg-white/5 text-gray-300 hover:bg-white/10'
                }`}
              >
                {t(`adminCatalogImport.sheets.${sheet.labelKey}`)} · {draft[sheet.id].length}
                {errorsOnTab(sheet.id) > 0 && <span className="ml-1.5 rounded-full bg-red-500/20 px-1.5 py-0.5 text-[11px] text-red-200">
                  {t('adminCatalogImport.curation.errorsCount', { count: errorsOnTab(sheet.id) })}
                </span>}
              </button>
            ))}
          </nav>

          {proposal && activeRows.length > 0 && <section className={`grid min-w-0 gap-4 ${openRow && !singleBrand ? 'lg:grid-cols-[minmax(0,1fr)_minmax(380px,460px)]' : ''}`}>
            {!singleBrand && <div className={`min-w-0 space-y-3 ${openRow ? 'hidden lg:block' : ''}`}>
              {activeSheet === 'filaments' && marketCountries.length > 1 && <div className="flex flex-wrap items-center gap-2 text-sm text-gray-300">
                <span>{t('adminCatalogImport.curation.marketSwitch')}</span>
                <div className="w-56">
                  <Dropdown size="sm" clearable={false} value={shownCountry} disabled={busy}
                    options={[{ value: 'all', label: t('adminCatalogImport.curation.allCountries') },
                      ...marketCountries.map((item) => ({ value: item.code, label: `${item.name} · ${item.total}` }))]}
                    onChange={(value) => { setMarketCountry(String(value)); setPage(1); setOnlyDiffering(false); }} />
                </div>
              </div>}
              {activeSheet === 'filaments' && marketGroups.length > 0 && (shownCountry !== 'all' || marketCountries.length <= 3 || defaultsOpen
                ? <MarketDefaultsPanel groups={marketGroups} draft={draft} disabled={busy || readonly}
                  onlyDiffering={onlyDiffering} differingCount={differs.size}
                  onToggleDiffering={() => { setOnlyDiffering((value) => !value); setPage(1); }}
                  onApply={(indices, field, value) => editRows('filament_markets', indices.map((index) => ({ index, field, value })))} />
                : <button type="button" onClick={() => setDefaultsOpen(true)}
                  className="flex w-full flex-wrap items-center gap-2 rounded-xl border border-white/10 bg-black/10 px-3 py-2 text-left text-sm text-gray-200 hover:bg-white/5">
                  <span className="font-semibold text-white">{t('adminCatalogImport.curation.marketDefaults')}:</span>
                  <span className="min-w-0 truncate">{marketCountries.slice(0, 3).map((item) => item.name).join(', ')}</span>
                  <span className="text-gray-400">{t('adminCatalogImport.curation.moreCountries', { count: marketCountries.length - 3 })}</span>
                </button>)}
              <div className="rounded-2xl border border-white/10 bg-slate-950/35 p-3">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold text-white">{t('adminCatalogImport.curation.records')} · {proposalRows.length}</h3>
                  {rowSearch.trim() && proposalRows.length > 0 && <button type="button" disabled={busy || readonly}
                    onClick={() => setSelected(new Set(proposalRows.map(({ index }) => index)))}
                    className="text-xs text-indigo-200 underline underline-offset-2 disabled:opacity-40">
                    {t('adminCatalogImport.curation.selectFound', { count: proposalRows.length })}
                  </button>}
                  <input
                    type="search"
                    aria-label={t('adminCatalogImport.curation.searchRecords')}
                    placeholder={t('adminCatalogImport.curation.searchRecords')}
                    value={rowSearch}
                    onChange={(event) => { setRowSearch(event.target.value); setPage(1); }}
                    className="h-9 w-full rounded-lg border border-white/15 bg-slate-950/70 px-3 text-sm text-white placeholder:text-gray-500 focus:border-indigo-400 focus:outline-none sm:w-64"
                  />
                </div>
                {selectedVisible.size > 0 && <div className="mb-2">
                  <BulkEditBar sheet={activeSheet} count={selectedVisible.size} total={proposalRows.length} disabled={busy || readonly}
                    countries={marketCountries.map(({ code, name }) => ({ code, name }))}
                    fixedCountry={shownCountry === 'all' ? null : shownCountry}
                    onSelectAll={() => setSelected(new Set(proposalRows.map(({ index }) => index)))}
                    onClear={() => setSelected(new Set())} onApply={bulkApply} targetCount={bulkTargetCount} />
                </div>}
                <ProposalRecordList sheet={activeSheet} rows={proposalRows}
                  page={page} pageSize={PROPOSAL_ROW_PAGE_SIZE} onPageChange={setPage}
                  selected={selectedVisible} onSelect={updateSelection} openIndex={openIndex} onOpen={setOpenIndex}
                  planByRow={planByRow} coverage={coverageOf} marketCells={marketCells} differs={differs} hasDefault={marketGroups.length > 0} showBrand={draft.brands.length > 1} disabled={busy || readonly} />
              </div>
            </div>}
            {openRow && currentIndex !== null && <div className={`min-w-0 ${singleBrand ? '' : 'lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:self-start lg:overflow-y-auto lg:pr-1'}`}>
              <VariantEditor key={`${activeSheet}-${currentIndex}`} sheet={activeSheet} row={openRow} index={currentIndex}
                standalone={singleBrand}
                rowNumber={Number(openRow._row ?? currentIndex + 2)} draft={draft}
                disabled={busy} readonly={readonly} coverageLine={editorCoverage}
                evidence={evidenceApi} facts={factsApi} marketErrors={marketErrors} onEdit={editRows}
                onAddRow={addMarketRow} onRemoveRow={removeMarketRow} onClose={() => setOpenIndex(null)} />
            </div>}
          </section>}

          {!proposal && activeRows.length > 0 && (
            <section className="overflow-hidden rounded-xl border border-white/10">
              <div className="max-h-[58vh] overflow-auto">
                <table className="min-w-max border-collapse text-xs">
                  <thead className="sticky top-0 z-10 bg-gray-950">
                    <tr>
                      <th className="border-b border-r border-white/10 px-2 py-2 text-left text-gray-400">#</th>
                      <th className="border-b border-r border-white/10 px-2 py-2 text-left text-gray-400">{t('adminCatalogImport.result')}</th>
                      {columns.map((column) => (
                        <th key={column} className="border-b border-r border-white/10 px-2 py-2 text-left font-medium text-gray-300">
                          {column}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {visibleRows.map((row, visibleIndex) => {
                      const rowNumber = Number(row._row ?? (page - 1) * PAGE_SIZE + visibleIndex + 2);
                      const result = planByRow.get(rowNumber);
                      return (
                        <tr key={`${rowNumber}-${visibleIndex}`} className={result?.status === 'error' ? 'bg-red-500/5' : 'odd:bg-white/[0.02]'}>
                          <td className="border-b border-r border-white/10 px-2 py-2 font-mono text-gray-500">{rowNumber}</td>
                          <td className="max-w-64 border-b border-r border-white/10 px-2 py-2">
                            <span className={result?.status === 'error' ? 'text-red-300' : 'text-gray-300'}>
                              {result ? t(`adminCatalogImport.status.${result.status}`) : '—'}
                            </span>
                            {result?.message && <div className="mt-1 whitespace-normal text-[11px] leading-4 text-red-300">{result.message}</div>}
                          </td>
                          {columns.map((column) => {
                            const checkbox = column === 'enabled' || column === 'overwrite';
                            const absoluteIndex = (page - 1) * PAGE_SIZE + visibleIndex;
                            return (
                              <td key={column} className="border-b border-r border-white/10 p-1">
                                {checkbox ? (
                                  <input
                                    type="checkbox"
                                    aria-label={`${column} ${rowNumber}`}
                                    disabled={busy}
                                    checked={column === 'enabled' && row[column] === undefined ? true : ['true', '1', 'yes', 'да'].includes(cellText(row[column]).toLowerCase())}
                                    onChange={(event) => editRows(activeSheet, [{ index: absoluteIndex, field: column, value: event.target.checked }])}
                                    className="h-4 w-4 accent-indigo-500"
                                  />
                                ) : (
                                  <input
                                    aria-label={`${column} ${rowNumber}`}
                                    disabled={busy}
                                    value={cellText(row[column])}
                                    onChange={(event) => editRows(activeSheet, [{ index: absoluteIndex, field: column, value: event.target.value }])}
                                    className="w-40 rounded border border-transparent bg-transparent px-2 py-1.5 text-gray-200 outline-none transition focus:border-indigo-400/50 focus:bg-black/30"
                                  />
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="flex justify-center border-t border-white/10 p-3">
                <AdminPager page={page} totalPages={totalPages} onPageChange={setPage}
                  label={t('adminCatalogImport.result')}
                  previousLabel={t('adminCatalogImport.curation.previous')} nextLabel={t('adminCatalogImport.curation.next')} />
              </div>
            </section>
          )}

          {!proposal && <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-white/10 bg-black/15 p-4">
            <button type="button" disabled={busy} onClick={requestClose}
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-white/15 px-3 py-2 text-sm text-gray-300 transition hover:bg-white/5 disabled:opacity-40">
              <RotateCcw className="h-4 w-4" />
              {t('adminCatalogImport.cancel')}
            </button>
            <button
              type="button"
              aria-label={t('adminCatalogImport.revalidate')}
              disabled={busy || !dirty}
              onClick={() => revalidateMutation.mutate(draft)}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-500 px-3 py-2 text-sm font-semibold text-white disabled:opacity-40"
            >
              {revalidateMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              {t('adminCatalogImport.revalidate')}
            </button>
            <button
              type="button"
              disabled={busy || dirty || !preview?.confirmation_token || (preview?.summary.error ?? 0) > 0}
              onClick={() => {
                if (preview?.confirmation_token) applyMutation.mutate({ value: draft, token: preview.confirmation_token });
              }}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-bold text-slate-950 disabled:opacity-40"
            >
              {applyMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
              {t('adminCatalogImport.apply')}
            </button>
          </div>}
        </>
      )}

      <ConfirmModal isOpen={confirmDiscard} onClose={() => setConfirmDiscard(false)} onConfirm={() => { setConfirmDiscard(false); cancel(); }}
        title={t('adminCatalogImport.curation.discardTitle')} message={t('adminCatalogImport.curation.discardChanges')}
        confirmText={t('adminCatalogImport.curation.discardConfirm')} variant="warning" />

      {(historyQuery.data?.items.length ?? 0) > 0 && <section>
        <h3 className="mb-3 text-sm font-semibold text-white">{t('adminCatalogImport.history')}</h3>
        <div className="space-y-2">
          {(historyQuery.data?.items ?? []).map((batch) => (
            <div key={batch.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-xs">
              <div>
                <span className="font-semibold text-gray-200">#{batch.id} · {batch.filename}</span>
                <span className="ml-2 text-gray-500">{new Date(batch.applied_at).toLocaleString()}</span>
              </div>
              <div className="text-gray-400">
                +{batch.summary.create ?? 0} · Δ{batch.summary.update ?? 0}
              </div>
            </div>
          ))}
        </div>
      </section>}
    </div>
  );
}
