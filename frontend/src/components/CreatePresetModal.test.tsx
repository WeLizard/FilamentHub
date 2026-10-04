import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Preset, PresetDraftAnalysis, Printer } from '../types/api';
import { loadFilamentPresetSchema } from '../utils/orcaPresetSchema';
import { CreatePresetModal } from './CreatePresetModal';

const {
  createPresetMock,
  getDraftAnalysisMock,
  getFilamentMock,
  listFilamentsMock,
  notifyProfileChangedMock,
  siteLanguage,
  updatePresetMock,
} = vi.hoisted(() => ({
  createPresetMock: vi.fn(),
  getDraftAnalysisMock: vi.fn(),
  getFilamentMock: vi.fn(),
  listFilamentsMock: vi.fn(),
  notifyProfileChangedMock: vi.fn(),
  siteLanguage: { current: 'en' },
  updatePresetMock: vi.fn(),
}));

vi.mock('../utils/pluginBridge', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../utils/pluginBridge')>()),
  notifyProfileChanged: notifyProfileChangedMock,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: siteLanguage.current } }),
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, role: 'user', active_organization_id: null },
  }),
}));

vi.mock('../api/client', () => ({
  achievementsAPI: {
    getMine: vi.fn().mockResolvedValue({ earned: [], newly_earned: [] }),
    evaluateMine: vi.fn().mockResolvedValue({ earned: [], newly_earned: [] }),
  },
  presetsAPI: {
    create: (...args: unknown[]) => createPresetMock(...args),
    update: (...args: unknown[]) => updatePresetMock(...args),
    getDraftAnalysis: (...args: unknown[]) => getDraftAnalysisMock(...args),
    recordDraftEvent: vi.fn().mockResolvedValue(undefined),
  },
  filamentsAPI: {
    list: (...args: unknown[]) => listFilamentsMock(...args),
    get: (...args: unknown[]) => getFilamentMock(...args),
  },
  brandsAPI: {
    list: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 20, pages: 0 }),
    get: vi.fn().mockResolvedValue({ id: 7, verified: false }),
    myTerritories: vi.fn().mockResolvedValue({ territories: [] }),
  },
  printersAPI: {
    list: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 50, pages: 0 }),
  },
}));

vi.mock('./ModalOverlay', () => ({
  ModalOverlay: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useModalPortalRef: (ref?: { current: HTMLElement | null }) => (element: HTMLElement | null) => {
    if (ref) ref.current = element;
  },
}));

vi.mock('./MaterialTypeSelect', () => ({
  MaterialTypeSelect: ({ value }: { value: string }) => (
    <input aria-label="material-type" readOnly value={value} />
  ),
}));

vi.mock('./ColorMaterialSection', () => ({
  ColorMaterialSection: ({ colorHex }: { colorHex: string }) => (
    <output data-testid="material-color">{colorHex}</output>
  ),
}));

vi.mock('./FilamentHandlingEditor', () => ({
  FilamentHandlingEditor: () => null,
  isHandlingGuidanceComplete: () => true,
  normalizeChemicalGuidance: () => [],
  parseBedAdhesives: () => [],
}));

vi.mock('./RecommendedTempsField', () => ({
  EMPTY_RECOMMENDED_TEMPS: {
    nozzleMin: '', nozzleMax: '', bedMin: '', bedMax: '',
  },
  RecommendedTempsField: () => null,
}));

vi.mock('./NozzleHardnessField', () => ({
  NozzleHardnessField: ({ value }: { value: number | null }) => (
    <div data-testid="nozzle-hrc">{value ?? 'none'}</div>
  ),
}));
vi.mock('./DensityField', () => ({ DensityField: () => null }));
vi.mock('./FilamentFeaturesEditor', () => ({ FilamentFeaturesEditor: () => null }));
vi.mock('./FloatingHSLColorPicker', () => ({ FloatingHSLColorPicker: () => null }));
vi.mock('./EditGCodeModal', () => ({ EditGCodeModal: () => null }));
vi.mock('./FilamentSummaryCard', () => ({ FilamentSummaryCard: () => null }));
vi.mock('./InfoHint', () => ({ InfoHint: ({ text }: { text: string }) => <i data-hint={text} /> }));
vi.mock('./ConfirmModal', () => ({ ConfirmModal: () => null }));
vi.mock('./Toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const preset = (id: number, name: string): Preset => ({
  id,
  filament_id: null,
  name,
  description: null,
  is_official: false,
  is_weighted: false,
  extruder_temp: 210,
  bed_temp: 60,
  flow_rate: 100,
  fan_speed: 100,
  retraction_length: 5,
  retraction_speed: 45,
  orcaslicer_settings: {},
  rating: null,
  success_rate: null,
  usage_count: 0,
  active: false,
  moderation_status: 'not_required',
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
});

const analysis = (
  presetId: number,
  evidenceKind: 'orca_capture' | 'stored_snapshot',
  direct: boolean,
): PresetDraftAnalysis => ({
  preset_id: presetId,
  evidence_kind: evidenceKind,
  suggestions: {
    brand_name: {
      value: evidenceKind === 'orca_capture' ? 'Bambu Lab' : 'Legacy Vendor',
      source: evidenceKind === 'orca_capture' ? 'orca' : 'stored_snapshot',
      confidence: direct ? 'high' : 'suggested',
      direct,
    },
    filament_name: {
      value: evidenceKind === 'orca_capture' ? 'Fresh material' : 'Legacy material',
      source: 'profile_name',
      confidence: 'medium',
      direct: false,
    },
    material_type: {
      value: evidenceKind === 'orca_capture' ? 'PLA' : 'PETG',
      source: evidenceKind === 'orca_capture' ? 'orca' : 'stored_snapshot',
      confidence: direct ? 'high' : 'suggested',
      direct,
    },
    color_hex: {
      value: evidenceKind === 'orca_capture' ? '#8000FF' : '#00FF00',
      source: evidenceKind === 'orca_capture' ? 'orca' : 'stored_snapshot',
      confidence: direct ? 'high' : 'suggested',
      direct,
    },
    diameter: {
      value: 1.75,
      source: evidenceKind === 'orca_capture' ? 'orca' : 'stored_snapshot',
      confidence: direct ? 'high' : 'suggested',
      direct,
    },
  },
  brand_match: null,
  filament_matches: evidenceKind === 'stored_snapshot'
    ? [{
        id: 77,
        name: 'Legacy material',
        brand_id: 7,
        material_type: 'PETG',
        color_name: 'Green',
        confidence: 'exact',
        reasons: ['product_name'],
      }]
    : [],
  confirmed_fields: direct ? ['brand_name', 'color_hex', 'material_type'] : [],
  suggested_fields: direct ? ['filament_name'] : [
    'brand_name', 'color_hex', 'filament_name', 'material_type',
  ],
  preset_readiness_percent: 70,
  catalog_readiness_percent: direct ? 55 : 30,
  technical_settings_count: 4,
  preset_decisions: [],
  catalog_decisions: direct ? ['choose_or_create_filament'] : [
    'confirm_new_brand', 'confirm_material_type', 'choose_catalog_filament',
  ],
  review_state: 'needs_decision',
  generic_source: false,
  similar_import_users: 0,
});

describe('CreatePresetModal imported draft review', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updatePresetMock.mockResolvedValue({ id: 3, filament_id: 77 });
    listFilamentsMock.mockResolvedValue({
      items: [], total: 0, page: 1, size: 100, pages: 0,
    });
    getDraftAnalysisMock.mockImplementation(async (id: number) => (
      id === 1 ? analysis(1, 'orca_capture', true) : analysis(2, 'stored_snapshot', false)
    ));
  });

  it('prefills review fields from source evidence without auto-linking a legacy filament', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const view = render(
      <QueryClientProvider client={queryClient}>
        <CreatePresetModal isOpen onClose={vi.fn()} preset={preset(1, 'Fresh profile')} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByLabelText('material-type')).toHaveValue('PLA');
      expect(screen.getByTestId('material-color')).toHaveTextContent('#8000FF');
    });

    view.rerender(
      <QueryClientProvider client={queryClient}>
        <CreatePresetModal isOpen onClose={vi.fn()} preset={preset(2, 'Legacy profile')} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText(/Legacy Vendor/)).toBeInTheDocument();
      expect(screen.getByDisplayValue('Legacy Vendor')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Legacy material')).toBeInTheDocument();
      expect(screen.getByLabelText('material-type')).toHaveValue('PETG');
      expect(screen.getByTestId('material-color')).toHaveTextContent('#00FF00');
      expect(screen.getByTestId('draft-color-swatch')).toHaveStyle({ backgroundColor: '#00FF00' });
      expect(screen.queryByText(/presetModal\.review\.diameter/)).not.toBeInTheDocument();
    });
    expect(getFilamentMock).not.toHaveBeenCalled();
  });

  it('does not expose official publication in personal draft review', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const officialDraft = { ...preset(1, 'Brand draft'), is_official: true };

    render(
      <QueryClientProvider client={queryClient}>
        <CreatePresetModal
          isOpen
          onClose={vi.fn()}
          preset={officialDraft}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(getDraftAnalysisMock).toHaveBeenCalled());
    expect(screen.queryByRole('checkbox', { name: 'presetModal.officialPreset' })).not.toBeInTheDocument();
    expect(screen.queryByText('presetModal.officialPresetInfo')).not.toBeInTheDocument();
  });

  it('saves tested-on links without reinjecting legacy printer restrictions', async () => {
    const sourceSettings = {
      compatible_printers: ['Voron 2.4 350 0.4 nozzle'],
      compatible_printers_condition: 'printer_model=="Voron 2.4 350"',
      future_filament_option: ['kept'],
    };
    const original = structuredClone(sourceSettings);
    const published = {
      ...preset(3, 'Community PLA'),
      active: true,
      filament_id: 77,
      orcaslicer_settings: sourceSettings,
      printers: [
        { id: 1, name: 'Bambu Lab P2S', manufacturer: 'Bambu Lab', model: 'P2S' },
        { id: 2, name: 'Voron 2.4 350', manufacturer: 'Voron', model: '2.4 350' },
      ] as Printer[],
    };
    getFilamentMock.mockResolvedValue({
      id: 77, name: 'PLA', material_type: 'PLA', brand_id: 7, diameter: 1.75,
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <CreatePresetModal isOpen onClose={vi.fn()} preset={published} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Bambu Lab P2S')).toBeInTheDocument();
    expect(screen.getByText('Voron 2.4 350')).toBeInTheDocument();
    const save = screen.getByRole('button', { name: 'presetModal.save' });
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.click(save);

    await waitFor(() => expect(updatePresetMock).toHaveBeenCalledOnce());
    const [id, payload] = updatePresetMock.mock.calls[0];
    expect(id).toBe(3);
    expect(payload.printer_ids).toEqual([1, 2]);
    expect(payload.orcaslicer_settings).not.toHaveProperty('compatible_printers');
    expect(payload.orcaslicer_settings).not.toHaveProperty('compatible_printers_condition');
    expect(payload.orcaslicer_settings.future_filament_option).toEqual(['kept']);
    expect(sourceSettings).toEqual(original);
    await waitFor(() => expect(notifyProfileChangedMock).toHaveBeenCalledOnce());
  });
});

describe('CreatePresetModal bed temperature per plate', () => {
  const plateSettings = () => ({
    nozzle_temperature: ['210'],
    nozzle_temperature_initial_layer: ['210'],
    filament_flow_ratio: ['1'],
    filament_retraction_length: ['5'],
    filament_retraction_speed: ['45'],
    fan_min_speed: ['100'],
    bed_temperature: ['95'],
    bed_temperature_initial_layer: ['nil'],
    textured_plate_temp: ['55'],
    textured_plate_temp_initial_layer: ['55'],
    hot_plate_temp: ['85'],
    hot_plate_temp_initial_layer: ['85'],
    cool_plate_temp: ['35'],
    cool_plate_temp_initial_layer: ['35'],
    eng_plate_temp: ['0'],
    eng_plate_temp_initial_layer: ['0'],
    future_filament_option: ['kept'],
  });

  const ALL_PLATE_KEYS = [
    'supertack_plate_temp_initial_layer',
    'supertack_plate_temp',
    'cool_plate_temp_initial_layer',
    'cool_plate_temp',
    'textured_cool_plate_temp_initial_layer',
    'textured_cool_plate_temp',
    'eng_plate_temp_initial_layer',
    'eng_plate_temp',
    'hot_plate_temp_initial_layer',
    'hot_plate_temp',
    'textured_plate_temp_initial_layer',
    'textured_plate_temp',
  ];
  const HIDDEN_KEYS = [
    'bed_temperature',
    'customized_plate_temp',
    'customized_plate_temp_initial_layer',
    'epoxy_resin_plate_temp',
    'epoxy_resin_plate_temp_initial_layer',
  ];
  const TEXTURED_OTHER = 'Textured PEI Plate Other layers';

  const renderModal = (props: Partial<React.ComponentProps<typeof CreatePresetModal>>) => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <CreatePresetModal isOpen onClose={vi.fn()} {...props} />
      </QueryClientProvider>,
    );
  };

  const renderEditor = (settings: Record<string, unknown>) => renderModal({
    preset: {
      ...preset(5, 'Bed plates PLA'),
      active: true,
      filament_id: 77,
      bed_temp: 95,
      orcaslicer_settings: settings,
    },
  });

  const saveEdit = async () => {
    const save = screen.getByRole('button', { name: 'presetModal.save' });
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.click(save);
    await waitFor(() => expect(updatePresetMock).toHaveBeenCalledOnce());
    return updatePresetMock.mock.calls[0][1];
  };

  const chooseFilament = async (name: RegExp) => {
    fireEvent.focus(screen.getByPlaceholderText('presetModal.filamentSearchPlaceholder'));
    fireEvent.click(await screen.findByRole('button', { name }));
  };

  beforeEach(() => {
    vi.clearAllMocks();
    siteLanguage.current = 'en';
    updatePresetMock.mockResolvedValue({ id: 5, filament_id: 77 });
    createPresetMock.mockResolvedValue({ id: 6, filament_id: 77 });
    getFilamentMock.mockResolvedValue({
      id: 77, name: 'PLA', material_type: 'PLA', brand_id: 7, diameter: 1.75,
    });
    listFilamentsMock.mockResolvedValue({
      items: [
        {
          id: 77, name: 'Plain', material_type: 'PETG', brand_name: 'Acme', color_name: null,
        },
        {
          id: 78,
          name: 'Vendor',
          material_type: 'PETG',
          brand_name: 'Acme',
          color_name: null,
          recommended_bed_temp_min: 66,
          recommended_bed_temp_max: 74,
        },
      ],
      total: 2, page: 1, size: 100, pages: 1,
    });
    getDraftAnalysisMock.mockResolvedValue(analysis(5, 'orca_capture', true));
  });

  it('shows every plate with its own first-layer and other-layers value', async () => {
    renderEditor(plateSettings());

    expect(await screen.findByLabelText(TEXTURED_OTHER)).toHaveValue(55);
    expect(screen.getByLabelText('Smooth PEI Plate / High Temp Plate First layer')).toHaveValue(85);
    expect(screen.getByLabelText('Cool Plate First layer')).toHaveValue(35);
    expect(screen.getByLabelText('Engineering Plate Other layers')).toHaveValue(0);
    expect(screen.getByLabelText('Textured Cool Plate First layer')).toHaveValue(95);
  });

  it('saves an untouched form without changing the plate values or sending bed_temp', async () => {
    const source = plateSettings();
    const original = structuredClone(source);
    renderEditor(source);
    await screen.findByLabelText(TEXTURED_OTHER);

    const payload = await saveEdit();

    expect(payload.orcaslicer_settings).toEqual(original);
    expect(payload).not.toHaveProperty('bed_temp');
  });

  it('changes only the edited plate when a single cell is edited', async () => {
    const source = plateSettings();
    const original = structuredClone(source);
    renderEditor(source);
    fireEvent.change(await screen.findByLabelText(TEXTURED_OTHER), { target: { value: '60' } });

    const payload = await saveEdit();

    expect(payload.orcaslicer_settings).toEqual({ ...original, textured_plate_temp: ['60'] });
    expect(payload).not.toHaveProperty('bed_temp');
  });

  it('applies the top bed field to every plate and to the keys the table hides', async () => {
    renderEditor(plateSettings());
    const textured = await screen.findByLabelText(TEXTURED_OTHER);

    const topBed = screen.getAllByDisplayValue('95').find((input) => !input.hasAttribute('aria-label'));
    fireEvent.change(topBed!, { target: { value: '70' } });

    expect(textured).toHaveValue(70);
    expect(screen.getByLabelText('Engineering Plate First layer')).toHaveValue(70);
    expect(screen.getByLabelText('Textured Cool Plate Other layers')).toHaveValue(70);

    const payload = await saveEdit();
    const saved = payload.orcaslicer_settings;
    [...ALL_PLATE_KEYS, ...HIDDEN_KEYS].forEach((key) => expect(saved[key]).toEqual(['70']));
    expect(saved).not.toHaveProperty('bed_temperature_initial_layer');
    expect(saved.future_filament_option).toEqual(['kept']);
    expect(payload).not.toHaveProperty('bed_temp');
  });

  it('shows the material default in the plate cells of a new preset and follows a later recommendation', async () => {
    renderModal({});
    await screen.findByLabelText(TEXTURED_OTHER);

    await chooseFilament(/Plain/);

    await waitFor(() => expect(screen.getByLabelText(TEXTURED_OTHER)).toHaveValue(80));
    expect(screen.getByLabelText('Engineering Plate First layer')).toHaveValue(80);

    await chooseFilament(/Vendor/);

    await waitFor(() => expect(screen.getByLabelText(TEXTURED_OTHER)).toHaveValue(70));
    expect(screen.getByLabelText('Engineering Plate First layer')).toHaveValue(70);

    fireEvent.change(screen.getByPlaceholderText('presetModal.presetNamePlaceholder'), {
      target: { value: 'My PETG' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'presetModal.create' }));

    await waitFor(() => expect(createPresetMock).toHaveBeenCalledOnce());
    const payload = createPresetMock.mock.calls[0][0];
    expect(payload.bed_temp).toBe(70);
    ALL_PLATE_KEYS.forEach((key) => expect(payload.orcaslicer_settings[key]).toEqual(['70']));
  });

  it('keeps a plate cell a person typed when a recommendation later changes the top field', async () => {
    renderModal({});
    await screen.findByLabelText(TEXTURED_OTHER);
    await chooseFilament(/Plain/);
    await waitFor(() => expect(screen.getByLabelText(TEXTURED_OTHER)).toHaveValue(80));

    fireEvent.change(screen.getByLabelText(TEXTURED_OTHER), { target: { value: '55' } });
    await chooseFilament(/Vendor/);

    await waitFor(() => expect(screen.getByLabelText('Engineering Plate First layer')).toHaveValue(70));
    expect(screen.getByLabelText(TEXTURED_OTHER)).toHaveValue(55);

    fireEvent.change(screen.getByPlaceholderText('presetModal.presetNamePlaceholder'), {
      target: { value: 'My PETG' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'presetModal.create' }));

    await waitFor(() => expect(createPresetMock).toHaveBeenCalledOnce());
    const saved = createPresetMock.mock.calls[0][0].orcaslicer_settings;
    expect(saved.textured_plate_temp).toEqual(['55']);
    expect(saved.textured_plate_temp_initial_layer).toEqual(['70']);
    expect(saved.eng_plate_temp).toEqual(['70']);
  });

  describe('Orca settings the form used to leave out', () => {
    const fullSettings = () => ({
      ...plateSettings(),
      filament_diameter: ['1.75'],
      filament_density: ['1.26'],
      required_nozzle_HRC: ['3'],
      filament_cost: ['24.99'],
      adaptive_pressure_advance_model: ['"0,0,0\\n0,0,0"'],
      filament_ironing_flow: ['nil,nil'],
      filament_ironing_spacing: ['nil,nil'],
      filament_ironing_inset: ['nil,nil'],
      filament_ironing_speed: ['nil,nil'],
      filament_tower_interface_pre_extrusion_dist: ['10'],
      filament_tower_interface_pre_extrusion_length: ['0'],
      filament_tower_ironing_area: ['4'],
      filament_tower_interface_purge_volume: ['20'],
      filament_tower_interface_print_temp: ['-1'],
      filament_ramming_parameters: ['"120 100 6.6 6.8|0.05 6.6 0.45 6.8"'],
    });

    const TAB_NAMES: Record<string, string> = {
      override: 'Setting Overrides',
      cooling: 'Cooling',
      extruder: 'Multimaterial',
    };
    const openTab = async (name: string) => fireEvent.click(await screen.findByRole('button', { name: TAB_NAMES[name] }));
    const chooseMode = (mode: string) => fireEvent.click(screen.getByRole('button', { name: `presetModal.settingMode.${mode}` }));

    beforeEach(() => {
      localStorage.removeItem('fh_preset_setting_mode');
    });

    it('shows every added setting with the stored value and saves an untouched form unchanged', async () => {
      const source = fullSettings();
      const original = structuredClone(source);
      renderEditor(source);
      chooseMode('expert');

      expect(await screen.findByLabelText('Density')).toHaveValue(1.26);
      expect(screen.getByLabelText('Diameter')).toHaveValue('1.75 mm');
      expect(screen.getByTestId('nozzle-hrc')).toHaveTextContent('3');
      expect(screen.queryByLabelText('Price')).not.toBeInTheDocument();

      await openTab('override');
      expect(screen.getByLabelText('Ironing flow')).toHaveValue(null);
      expect(screen.getByLabelText('Ironing speed')).toHaveValue(null);

      await openTab('extruder');
      expect(screen.getByLabelText('Interface layer pre-extrusion distance')).toHaveValue(10);
      expect(screen.getByLabelText('Interface layer print temperature')).toHaveValue(-1);
      expect(screen.getByLabelText('Ramming parameters')).toHaveValue('"120 100 6.6 6.8|0.05 6.6 0.45 6.8"');

      const payload = await saveEdit();

      expect(payload.orcaslicer_settings).toEqual(original);
    });

    it('writes an edited ironing flow as a percent and leaves every other setting alone', async () => {
      const source = fullSettings();
      const original = structuredClone(source);
      renderEditor(source);
      await openTab('override');

      fireEvent.change(await screen.findByLabelText('Ironing flow'), { target: { value: '15' } });

      const payload = await saveEdit();

      expect(payload.orcaslicer_settings).toEqual({ ...original, filament_ironing_flow: ['15%'] });
    });

    it('writes an edited density as the typed number', async () => {
      const source = fullSettings();
      const original = structuredClone(source);
      renderEditor(source);

      fireEvent.change(await screen.findByLabelText('Density'), { target: { value: '1.24' } });

      const payload = await saveEdit();

      expect(payload.orcaslicer_settings).toEqual({ ...original, filament_density: ['1.24'] });
    });

    it('shows an expert-level setting only in Expert mode', async () => {
      renderEditor(fullSettings());
      await screen.findByLabelText(TEXTURED_OTHER);

      expect(screen.getByLabelText('Density')).toBeInTheDocument();
      expect(screen.queryByTestId('nozzle-hrc')).not.toBeInTheDocument();

      chooseMode('expert');

      expect(screen.getByTestId('nozzle-hrc')).toBeInTheDocument();
    });

    it('locks a density the filament card holds until it is explicitly set by hand', async () => {
      getFilamentMock.mockResolvedValue({
        id: 77, name: 'PLA', material_type: 'PLA', brand_id: 7, diameter: 1.75, density: 1.27,
      });
      renderEditor({ filament_density: ['1.26'] });
      chooseMode('expert');

      const density = await screen.findByLabelText('Density');
      await waitFor(() => expect(density).toHaveValue(1.27));
      expect(density).toBeDisabled();

      fireEvent.click(screen.getByLabelText('presetModal.setManually'));
      expect(density).toBeEnabled();
      fireEvent.change(density, { target: { value: '1.3' } });

      const payload = await saveEdit();
      expect(payload.orcaslicer_settings.filament_density).toEqual(['1.3']);
      expect(payload.orcaslicer_settings.fhub_manual_overrides).toEqual(['filament_density']);
    });

    describe('adaptive pressure advance model', () => {
      const VOLUMETRIC = ['0 0 0 0 0 0', '0 0 0 0 0 0'];
      const withModel = (model: string) => ({
        ...plateSettings(),
        adaptive_pressure_advance: ['1'],
        adaptive_pressure_advance_model: [model],
        volumetric_speed_coefficients: [...VOLUMETRIC],
      });
      const modelField = async () => {
        const label = await screen.findByText('Adaptive pressure advance measurements (beta)');
        return label.closest('div')!.querySelector('textarea')!;
      };

      it.each([
        ['raw text', '0,0,0\n0,0,0'],
        ['Orca-serialised text', '"0,0,0\\n0,0,0"'],
      ])('shows %s decoded and saves an untouched form unchanged', async (_, model) => {
        const source = withModel(model);
        const original = structuredClone(source);
        renderEditor(source);

        expect((await modelField()).value).toBe('0,0,0\n0,0,0');

        const payload = await saveEdit();

        expect(payload.orcaslicer_settings).toEqual(original);
      });

      it('writes an edited raw value as one raw element and keeps the volumetric coefficients', async () => {
        const source = withModel('0,0,0\n0,0,0');
        const original = structuredClone(source);
        renderEditor(source);

        fireEvent.change(await modelField(), { target: { value: '0.1,0.2,0.3\n0.4,0.5,0.6' } });

        const payload = await saveEdit();

        expect(payload.orcaslicer_settings).toEqual({
          ...original,
          adaptive_pressure_advance_model: ['0.1,0.2,0.3\n0.4,0.5,0.6'],
        });
      });

      it('encodes an edited Orca-serialised value back into quotes', async () => {
        const source = withModel('"0,0,0\\n0,0,0"');
        const original = structuredClone(source);
        renderEditor(source);

        fireEvent.change(await modelField(), { target: { value: 'x"y\nz\\w' } });

        const payload = await saveEdit();

        expect(payload.orcaslicer_settings).toEqual({
          ...original,
          adaptive_pressure_advance_model: ['"x\\"y\\nz\\\\w"'],
        });
      });
    });

    it('takes the level of existing fields from the Orca schema', async () => {
      renderEditor(fullSettings());
      await screen.findByLabelText(TEXTURED_OTHER);
      chooseMode('simple');
      await openTab('cooling');

      expect(screen.getByText('Force cooling for overhangs and bridges').closest('.hidden')).toBeNull();
      expect(screen.getByText('Ironing fan speed').closest('.hidden')).not.toBeNull();
    });

    it.each([
      'filament_retraction_length',
      'filament_retraction_speed',
    ])('labels %s and hints it with the Russian text Orca ships', async (key) => {
      siteLanguage.current = 'ru';
      const schema = await loadFilamentPresetSchema();
      const russian = schema.options[key].tr?.ru;
      const overridesTab = schema.pages.find((page) => page.title === 'Setting Overrides')?.tr?.ru;
      renderEditor(fullSettings());

      fireEvent.click(await screen.findByRole('button', { name: overridesTab }));

      expect(await screen.findByText(russian?.label ?? '')).toBeInTheDocument();
      const hints = Array.from(document.querySelectorAll('[data-hint]')).map((el) => el.getAttribute('data-hint'));
      expect(hints).toContain(russian?.tooltip);
    });
  });
});
