import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Preset, PresetDraftAnalysis } from '../types/api';
import { CreatePresetModal } from './CreatePresetModal';

const {
  getDraftAnalysisMock,
  getFilamentMock,
  listFilamentsMock,
} = vi.hoisted(() => ({
  getDraftAnalysisMock: vi.fn(),
  getFilamentMock: vi.fn(),
  listFilamentsMock: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
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

vi.mock('./NozzleHardnessField', () => ({ NozzleHardnessField: () => null }));
vi.mock('./DensityField', () => ({ DensityField: () => null }));
vi.mock('./FilamentFeaturesEditor', () => ({ FilamentFeaturesEditor: () => null }));
vi.mock('./FloatingHSLColorPicker', () => ({ FloatingHSLColorPicker: () => null }));
vi.mock('./EditGCodeModal', () => ({ EditGCodeModal: () => null }));
vi.mock('./FilamentSummaryCard', () => ({ FilamentSummaryCard: () => null }));
vi.mock('./InfoHint', () => ({ InfoHint: () => null }));
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

  it('does not mark an imported draft as official by default', async () => {
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
          allowOfficial
        />
      </QueryClientProvider>,
    );

    const checkbox = await screen.findByRole('checkbox', { name: 'presetModal.officialPreset' });
    expect(checkbox).not.toBeChecked();
    expect(screen.queryByText('presetModal.officialPresetInfo')).not.toBeInTheDocument();
  });
});
