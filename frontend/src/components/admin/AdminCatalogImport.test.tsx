import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AdminCatalogImport } from './AdminCatalogImport';
import type { CatalogCurationProposal, CatalogImportPreview } from '../../types/api';

const mocks = vi.hoisted(() => ({
  list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), preview: vi.fn(), apply: vi.fn(),
  previewWorkbook: vi.fn(), applyWorkbook: vi.fn(), quoteChecks: vi.fn(), verifySources: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));
vi.mock('../../api/client', () => ({
  adminCatalogCurationAPI: mocks,
  adminCatalogImportAPI: {
    history: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    previewWorkbook: mocks.previewWorkbook,
    apply: mocks.applyWorkbook,
  },
}));
vi.mock('../Toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const filament = (key: string, extra: Record<string, unknown> = {}) => ({
  enabled: true, filament_key: key, brand_key: 'maker', mode: 'create', name: key.toUpperCase(), line: 'Std',
  material_type: 'PLA', color_name: 'Red', color_hex: '#ff0000', color_group: 'red', color_group_source: 'manual',
  diameter: 1.75, recommended_nozzle_temp_min: 200, availability: 'available', active: true,
  color_type: 'single', colors: ['#ff0000'], finish: 'matte', filler: 'none', effects: [], transparency: false,
  ...extra,
});
const market = (key: string, country: string, extra: Record<string, unknown> = {}) => ({
  enabled: true, filament_key: key, country, availability: 'available', published: true,
  product_url: `https://example.com/${key}`, purchase_links: [{ platform: 'official', url: `https://example.com/${key}` }],
  ...extra,
});

const proposal: CatalogCurationProposal = {
  id: 7, title: 'Reviewed catalog', status: 'draft', revision: 1,
  draft: {
    filename: 'proposal.json',
    brands: [{ brand_key: 'maker', name: 'Maker', enabled: true, social_media_urls: ['https://t.me/maker'] }],
    filaments: [filament('a'), filament('b'), filament('c')],
    brand_markets: [{ enabled: true, brand_key: 'maker', country: 'RU', published: true, shop_links: [{ platform: 'official', url: 'https://shop.example' }] }],
    filament_markets: [market('a', 'RU'), market('b', 'RU'), market('c', 'RU'), market('a', 'KZ', { availability: 'unknown' })],
    presets: [],
  },
  evidence: [
    { sheet: 'Filaments', key: 'a', field: 'name', kind: 'direct', source_urls: ['https://example.com/a'] },
    { sheet: 'FilamentMarkets', key: 'a:RU', field: 'availability', kind: 'direct', source_urls: [] },
  ],
  unmapped_facts: [], source_facts: [],
  coverage_note: 'Manufacturer catalog only', created_by_user_id: 1,
  created_at: '2026-10-18T12:00:00Z', updated_at: '2026-10-18T12:00:00Z', applied_batch_id: null,
};
const preview: CatalogImportPreview = {
  draft: proposal.draft,
  rows: [
    { sheet: 'Brands', row: 2, key: 'maker', status: 'create', message: null, changes: {} },
    ...['a', 'b', 'c'].map((key, i) => ({ sheet: 'Filaments' as const, row: i + 2, key, status: 'create' as const, message: null, changes: {} })),
  ],
  summary: { create: 4, update: 0, noop: 0, skipped: 0, error: 0 },
  confirmation_token: 'first-token', confirmation_expires_at: '2026-10-18T13:00:00Z',
};

const emptyReport = {
  items: [], job_pending: false,
  summary: {
    total: 0, verified: 0, quote_not_found: 0, value_not_in_quote: 0, source_unavailable: 0,
    image_only: 0, not_official_domain: 0, pending: 0, verified_percent: 0,
  },
};

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><AdminCatalogImport /></QueryClientProvider>);
}

function jsonFile(contents: string) {
  const file = new File([contents], 'proposal.json', { type: 'application/json' });
  Object.defineProperty(file, 'text', { value: () => Promise.resolve(contents) });
  return file;
}

async function openProposal() {
  mount();
  fireEvent.click(await screen.findByRole('button', { name: /Reviewed catalog/ }));
  await screen.findByRole('button', { name: 'adminCatalogImport.curation.previewAction' });
}
const openFilaments = async () => {
  await openProposal();
  fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.sheets.filaments · 3' }));
};
const openRecord = (title: string) => {
  const row = screen.getByRole('checkbox', { name: `adminCatalogImport.curation.selectRecord ${title}` }).parentElement!;
  fireEvent.click(within(row).getByRole('button'));
};
const applyButton = () => screen.getAllByRole('button')
  .find((button) => /curation\.outcome|^adminCatalogImport\.apply$/.test(button.getAttribute('aria-label') ?? ''))!;
const savedDraft = () => mocks.update.mock.calls[0][2].draft;

describe('catalog proposal review', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.list.mockResolvedValue({ items: [proposal], total: 1 });
    mocks.get.mockResolvedValue(proposal);
    mocks.update.mockResolvedValue({ ...proposal, revision: 2 });
    mocks.preview.mockResolvedValue({ ...preview, proposal_id: 7, revision: 1 });
    mocks.apply.mockResolvedValue({ batch_id: 12, summary: { create: 1 } });
    mocks.quoteChecks.mockResolvedValue(emptyReport);
    mocks.verifySources.mockResolvedValue(emptyReport);
  });

  it('shows only brand, filament and non-empty preset tabs; markets live inside the records', async () => {
    await openProposal();
    expect(screen.getByRole('button', { name: 'adminCatalogImport.sheets.brands · 1' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'adminCatalogImport.sheets.filaments · 3' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /sheets\.(brandMarkets|filamentMarkets|presets)/ })).not.toBeInTheDocument();
  });

  it('groups by material type then line, puts one-record lines together, and a header selects only its rows', async () => {
    const draft = {
      ...proposal.draft,
      filaments: [
        filament('a', { material_type: 'TPU', line: 'D60' }), filament('b', { material_type: 'TPU', line: 'D60' }),
        filament('c', { material_type: 'TPU', line: 'D70' }), filament('d', { material_type: 'PETG', line: 'Solo' }),
      ],
      filament_markets: [],
    };
    mocks.get.mockResolvedValue({ ...proposal, draft });
    await openProposal();
    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.sheets.filaments · 4' }));
    expect(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectGroup TPU' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectGroup D60' })).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: 'adminCatalogImport.curation.selectGroup D70' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('checkbox', { name: 'adminCatalogImport.curation.selectGroup adminCatalogImport.curation.singleItems' })).toHaveLength(1);
    expect(screen.queryByRole('checkbox', { name: 'adminCatalogImport.curation.selectGroup Solo' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectGroup D60' }));
    expect(screen.getByText('adminCatalogImport.curation.selectedCount')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectRecord A' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectRecord B' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectRecord C' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectRecord D' })).not.toBeChecked();
    fireEvent.click(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectGroup TPU' }));
    expect(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectRecord C' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectRecord D' })).not.toBeChecked();
  });

  it('queues a server check of the quotes and shows how many were confirmed', async () => {
    const report = {
      ...emptyReport, summary: { ...emptyReport.summary, total: 130, verified: 112, pending: 18, verified_percent: 86 },
      items: [{ scope: 'evidence', sheet: 'Filaments', key: 'a', field: 'name', status: 'verified', reason: null, url: null, checked_at: null, gating: true }],
    };
    mocks.quoteChecks.mockResolvedValue(report);
    await openProposal();
    const verify = await screen.findByRole('button', { name: 'adminCatalogImport.curation.verifySources' });
    await waitFor(() => expect(verify).toBeEnabled());
    expect(within(verify).getByText('adminCatalogImport.curation.verifySourcesSummary')).toBeInTheDocument();
    fireEvent.click(verify);
    await waitFor(() => expect(mocks.verifySources).toHaveBeenCalledWith(7));
  });

  it('shows no source check when the proposal cites no quotes', async () => {
    await openProposal();
    await screen.findByRole('button', { name: 'adminCatalogImport.curation.previewAction' });
    expect(screen.queryByRole('button', { name: 'adminCatalogImport.curation.verifySources' })).not.toBeInTheDocument();
  });

  it('opens the only brand directly, without a list', async () => {
    await openProposal();
    expect(screen.getByRole('textbox', { name: /fieldNames\.name \d/ })).toHaveValue('Maker');
    expect(screen.queryByRole('checkbox', { name: /selectRecord/ })).not.toBeInTheDocument();
  });

  it('saves an unedited draft byte-for-byte, including hidden fields and number types', async () => {
    await openFilaments();
    openRecord('A');
    fireEvent.click(screen.getByText('adminCatalogImport.curation.brandResearchNote'));
    fireEvent.change(screen.getByLabelText('adminCatalogImport.curation.name'), { target: { value: 'Renamed' } });
    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.saveShort' }));
    await waitFor(() => expect(mocks.update).toHaveBeenCalled());
    expect(JSON.stringify(savedDraft())).toBe(JSON.stringify(proposal.draft));
    expect(savedDraft().filaments[0].color_group_source).toBe('manual');
    expect(savedDraft().filaments[0].diameter).toBe(1.75);
    expect(mocks.update.mock.calls[0][2].evidence).toEqual(proposal.evidence);
  });

  it('bulk edit changes only the selected records', async () => {
    await openFilaments();
    fireEvent.click(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectRecord A' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectRecord C' }));
    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.changeField' }));
    fireEvent.change(screen.getByLabelText('adminCatalogImport.curation.bulkField'), { target: { value: 'recommended_nozzle_temp_min' } });
    fireEvent.change(screen.getByRole('textbox', { name: /bulkValue/ }), { target: { value: '215' } });
    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.bulkApply' }));
    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.saveShort' }));
    await waitFor(() => expect(mocks.update).toHaveBeenCalled());
    const rows = savedDraft().filaments;
    expect(rows.map((row: Record<string, unknown>) => row.recommended_nozzle_temp_min)).toEqual([215, 200, 215]);
    expect(rows[1]).toEqual(proposal.draft.filaments[1]);
    expect(savedDraft().filament_markets).toEqual(proposal.draft.filament_markets);
  });

  it('bulk market edit writes only to the chosen countries of the selected records', async () => {
    await openFilaments();
    fireEvent.click(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectRecord A' }));
    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.changeField' }));
    fireEvent.change(screen.getByLabelText('adminCatalogImport.curation.bulkField'), { target: { value: 'market:published' } });
    fireEvent.click(screen.getByRole('checkbox', { name: 'Kazakhstan' }));
    fireEvent.click(screen.getByRole('checkbox', { name: /groups\.markets: .*published.*bulkValue/ }));
    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.bulkApply' }));
    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.saveShort' }));
    await waitFor(() => expect(mocks.update).toHaveBeenCalled());
    const markets = savedDraft().filament_markets;
    expect(markets.map((row: Record<string, unknown>) => row.published)).toEqual([false, true, true, true]);
  });

  it('writes a country default into every market row of that country and no others', async () => {
    await openFilaments();
    const russia = within(screen.getByLabelText('adminCatalogImport.curation.marketDefaults'));
    fireEvent.click(russia.getByRole('checkbox', { name: /fieldNames\.published · Russia/ }));
    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.saveShort' }));
    await waitFor(() => expect(mocks.update).toHaveBeenCalled());
    const markets = savedDraft().filament_markets;
    expect(markets.map((row: Record<string, unknown>) => row.published)).toEqual([false, false, false, true]);
    expect(markets).toHaveLength(4);
  });

  it('adds and removes a market for one record only, removing just its evidence', async () => {
    await openFilaments();
    openRecord('A');
    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.removeMarket RU' }));
    fireEvent.click(screen.getAllByRole('button', { name: 'adminCatalogImport.curation.removeMarket' })[0]);
    fireEvent.change(screen.getByLabelText('adminCatalogImport.curation.addMarket'), { target: { value: 'DE' } });
    fireEvent.click(screen.getByRole('button', { name: /adminCatalogImport.curation.addMarket/ }));
    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.saveShort' }));
    await waitFor(() => expect(mocks.update).toHaveBeenCalled());
    const body = mocks.update.mock.calls[0][2];
    const keys = body.draft.filament_markets.map((row: Record<string, unknown>) => `${row.filament_key}:${row.country}`);
    expect(keys).toEqual(['b:RU', 'c:RU', 'a:KZ', 'a:DE']);
    expect(body.evidence).toEqual([proposal.evidence[0]]);
  });

  it('keeps Apply disabled after any edit that follows a preview and labels it with the outcome', async () => {
    await openFilaments();
    expect(applyButton()).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.previewAction' }));
    await waitFor(() => expect(applyButton()).toBeEnabled());
    expect(applyButton().getAttribute('aria-label')).toContain('curation.outcome');
    openRecord('A');
    fireEvent.click(screen.getByRole('checkbox', { name: /includeRecord/ }));
    expect(applyButton()).toBeDisabled();
    expect(applyButton().getAttribute('aria-label')).toBe('adminCatalogImport.apply');
    mocks.update.mockResolvedValue({ ...proposal, revision: 2 });
    mocks.preview.mockResolvedValue({ ...preview, proposal_id: 7, revision: 2, confirmation_token: 'fresh-token' });
    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.previewAction' }));
    await waitFor(() => expect(applyButton()).toBeEnabled());
    fireEvent.click(applyButton());
    await waitFor(() => expect(mocks.apply).toHaveBeenCalledWith(7, 2, 'fresh-token'));
    expect(mocks.update).toHaveBeenCalledTimes(1);
  });

  it('opens applied proposals read-only', async () => {
    mocks.get.mockResolvedValue({ ...proposal, status: 'applied', applied_batch_id: 12 });
    await openFilaments();
    openRecord('A');
    expect(screen.getByRole('checkbox', { name: /includeRecord/ })).toBeDisabled();
    expect(applyButton()).toBeDisabled();
    expect(screen.getByRole('button', { name: 'adminCatalogImport.curation.close' })).toBeEnabled();
  });

  it('asks before discarding an edited proposal', async () => {
    await openFilaments();
    openRecord('A');
    fireEvent.click(screen.getByRole('checkbox', { name: /includeRecord/ }));
    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.close' }));
    expect(screen.getByText('adminCatalogImport.curation.discardTitle')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'confirmModal.cancel' }));
    expect(screen.getByRole('checkbox', { name: /includeRecord/ })).toBeInTheDocument();
  });

  it('keeps workbook imports free of proposal controls and applies through the workbook API', async () => {
    const workbook: CatalogImportPreview = { ...preview, draft: { ...proposal.draft } };
    mocks.previewWorkbook.mockResolvedValue(workbook);
    mocks.applyWorkbook.mockResolvedValue({ batch_id: 13, summary: { create: 1 } });
    const { container } = mount();
    const input = container.querySelector<HTMLInputElement>('input[accept^=".xlsx"]');
    fireEvent.change(input!, { target: { files: [new File(['workbook'], 'catalog.xlsx')] } });
    const apply = await screen.findByRole('button', { name: 'adminCatalogImport.apply' });
    expect(screen.queryByRole('button', { name: 'adminCatalogImport.curation.saveShort' })).not.toBeInTheDocument();
    fireEvent.click(apply);
    await waitFor(() => expect(mocks.applyWorkbook).toHaveBeenCalledWith(workbook.draft, 'first-token'));
    expect(mocks.create).not.toHaveBeenCalled();
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('imports a proposal with optional sheets omitted', async () => {
    mocks.create.mockResolvedValue(proposal);
    const value = {
      title: proposal.title,
      draft: { filename: 'manufacturer.json', brands: proposal.draft.brands, filaments: proposal.draft.filaments },
      evidence: proposal.evidence, coverage_note: proposal.coverage_note,
    };
    const { container } = mount();
    fireEvent.change(container.querySelector<HTMLInputElement>('input[accept^=".json"]')!, { target: { files: [jsonFile(JSON.stringify(value))] } });
    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith({
      ...value, draft: { ...value.draft, brand_markets: [], filament_markets: [], presets: [] },
      unmapped_facts: [], source_facts: [],
    }));
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it.each([
    '{invalid json',
    JSON.stringify({ title: 'x', draft: { ...proposal.draft, presets: {} }, evidence: [], coverage_note: 'y' }),
    JSON.stringify({ title: 'x', draft: { ...proposal.draft, presets: null }, evidence: [], coverage_note: 'y' }),
  ])('rejects malformed proposal JSON before creating a proposal (%#)', async (contents) => {
    const { container } = mount();
    fireEvent.change(container.querySelector<HTMLInputElement>('input[accept^=".json"]')!, { target: { files: [jsonFile(contents)] } });
    expect(await screen.findByText('adminCatalogImport.curation.jsonError')).toBeInTheDocument();
    expect(mocks.create).not.toHaveBeenCalled();
  });

  describe('review fixes', () => {
    const withDraft = (changes: Record<string, unknown>) => mocks.get.mockResolvedValue({
      ...proposal, draft: { ...proposal.draft, ...changes },
    });
    const bulkNozzle = (value: string) => {
      fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.changeField' }));
      fireEvent.change(screen.getByLabelText('adminCatalogImport.curation.bulkField'), { target: { value: 'recommended_nozzle_temp_min' } });
      fireEvent.change(screen.getByRole('textbox', { name: /bulkValue/ }), { target: { value } });
      fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.bulkApply' }));
    };

    it('leaves the "only differing" filter when nothing differs any more instead of stranding an empty list', async () => {
      withDraft({ filament_markets: [market('a', 'RU'), market('b', 'RU'), market('c', 'RU', { published: false })] });
      await openFilaments();
      fireEvent.click(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.onlyDiffering' }));
      expect(screen.queryByRole('checkbox', { name: 'adminCatalogImport.curation.selectRecord A' })).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectRecord C' }));
      fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.changeField' }));
      fireEvent.change(screen.getByLabelText('adminCatalogImport.curation.bulkField'), { target: { value: 'market:published' } });
      fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.bulkApply' }));
      expect(await screen.findByRole('checkbox', { name: 'adminCatalogImport.curation.selectRecord A' })).toBeInTheDocument();
      expect(screen.queryByText('adminCatalogImport.curation.noRecordsFound')).not.toBeInTheDocument();
      expect(screen.queryByRole('checkbox', { name: 'adminCatalogImport.curation.onlyDiffering' })).not.toBeInTheDocument();
    });

    it('drops selected records that a search hides, so a bulk edit cannot reach them', async () => {
      await openFilaments();
      fireEvent.click(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectRecord A' }));
      fireEvent.click(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectRecord C' }));
      fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'c' } });
      expect(screen.queryByRole('checkbox', { name: 'adminCatalogImport.curation.selectRecord A' })).not.toBeInTheDocument();
      bulkNozzle('215');
      fireEvent.change(screen.getByRole('searchbox'), { target: { value: '' } });
      expect(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectRecord A' })).not.toBeChecked();
      fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.saveShort' }));
      await waitFor(() => expect(mocks.update).toHaveBeenCalled());
      expect(savedDraft().filaments.map((row: Record<string, unknown>) => row.recommended_nozzle_temp_min)).toEqual([200, 200, 215]);
    });

    it('cannot apply a market edit that reaches no market row', async () => {
      withDraft({ filaments: [...proposal.draft.filaments, filament('d')] });
      await openProposal();
      fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.sheets.filaments · 4' }));
      fireEvent.click(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectRecord D' }));
      fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.changeField' }));
      fireEvent.change(screen.getByLabelText('adminCatalogImport.curation.bulkField'), { target: { value: 'market:published' } });
      expect(screen.getByRole('button', { name: 'adminCatalogImport.curation.bulkApply' })).toBeDisabled();
      fireEvent.click(screen.getByRole('checkbox', { name: 'adminCatalogImport.curation.selectRecord A' }));
      expect(screen.getByRole('button', { name: 'adminCatalogImport.curation.bulkApply' })).toBeEnabled();
    });

    it('offers a source only for fields the row has, and one per field', async () => {
      await openFilaments();
      openRecord('A');
      const provenance = (field: string) => screen.queryByRole('button', { name: new RegExp(`curation\\.provenance: .*fieldNames\\.${field} ·`) });
      expect(provenance('effects')).toBeInTheDocument();
      expect(provenance('additives')).not.toBeInTheDocument();
      expect(provenance('property_claims')).not.toBeInTheDocument();
      fireEvent.click(provenance('name')!);
      expect(screen.queryByRole('button', { name: 'adminCatalogImport.curation.addEvidence' })).not.toBeInTheDocument();
      fireEvent.click(provenance('line')!);
      expect(screen.getByRole('button', { name: 'adminCatalogImport.curation.addEvidence' })).toBeInTheDocument();
    });

    it('does not call an unsaved or edited quote verified', async () => {
      const cited = [{ sheet: 'Filaments', key: 'a', field: 'name', kind: 'direct', source_urls: ['https://example.com/a'], quote: 'Name A' }];
      mocks.get.mockResolvedValue({ ...proposal, evidence: cited });
      await openFilaments();
      openRecord('A');
      const nameButton = () => screen.getByRole('button', { name: /curation\.provenance: .*fieldNames\.name ·/ });
      await waitFor(() => expect(nameButton().getAttribute('aria-label')).toContain('quoteStatus.verified'));
      fireEvent.click(screen.getByRole('checkbox', { name: /includeRecord/ }));
      expect(nameButton().getAttribute('aria-label')).toContain('quoteStatus.pending');
      expect(nameButton().getAttribute('aria-label')).not.toContain('quoteStatus.verified');
    });

    it('says why a preview has errors: in the bar, on the tab, in a list and beside the market row', async () => {
      mocks.preview.mockResolvedValue({
        ...preview, proposal_id: 7, revision: 1, confirmation_token: null,
        summary: { create: 2, update: 0, noop: 0, skipped: 0, error: 2 },
        rows: [
          { sheet: 'Filaments', row: 3, key: 'b', status: 'error', message: 'bad diameter', changes: {} },
          { sheet: 'FilamentMarkets', row: 2, key: 'a:RU', status: 'error', message: 'bad market link', changes: {} },
        ],
      });
      await openFilaments();
      fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.previewAction' }));
      const tab = await screen.findByRole('button', { name: /sheets\.filaments · 3.*errorsCount/ });
      expect(tab).toBeInTheDocument();
      expect(screen.getAllByText('adminCatalogImport.curation.errorsCount').length).toBeGreaterThanOrEqual(3);
      fireEvent.click(screen.getByText('adminCatalogImport.curation.errorsCount', { selector: 'summary' }));
      expect(screen.getByText(/FilamentMarkets|sheets\.filamentMarkets/, { selector: 'li' })).toHaveTextContent('a:RU: bad market link');
      openRecord('A');
      expect(screen.getAllByText('bad market link').some((node) => node.getAttribute('role') === 'alert')).toBe(true);
    });
  });
});
