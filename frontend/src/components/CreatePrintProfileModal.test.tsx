import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PrintProfile } from '../types/api';
import { CreatePrintProfileModal, buildStructuredAdvancedSettings, buildStructuredAdvancedValues } from './CreatePrintProfileModal';

const mocks = vi.hoisted(() => ({
  update: vi.fn(),
  t: (key: string) => key,
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: mocks.t, i18n: { exists: () => false } }) }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 1 } }) }));
vi.mock('../api/client', () => ({
  filamentsAPI: { list: async () => ({ items: [] }) },
  printerProfilesAPI: { listAllOwned: async () => [] },
  printProfilesAPI: { update: (...args: unknown[]) => mocks.update(...args) },
}));

const source = {
  compatible_printers: ['Exact printer configuration'],
  wipe_inward: [false],
  wipe_inward_distance: '50.000%',
  unsupported_wall_last: 'nil',
  detect_overhang_wall: '0',
  toolchange_ordering: 'default',
  toolchange_cyclic_order: '3, 2,1,4',
  toolchange_cyclic_first_layer: 0,
  enable_prime_tower: '1',
  wipe_tower_no_sparse_layers: '1',
  wipe_tower_sparse_layers_combination: ['1'],
  future_process_option: { levels: [1, 3], note: null },
};

function renderModal() {
  const profile: PrintProfile = {
    id: 42, name: 'Round trip', slug: 'round-trip', source: 'user',
    compatible_printers: ['Exact printer configuration'], orcaslicer_settings: source,
    owner_user_id: 1, description: null, category: null, is_official: false,
    active: true, vendor: null, external_id: null, setting_id: null,
    quality_tier: null, default_nozzle: null, layer_height_mm: null,
    compatible_filaments: null, extra_metadata: null, notes: null,
    printer_links: [], filament_links: [],
    created_at: '2026-09-29T00:00:00Z', updated_at: '2026-09-29T00:00:00Z',
  };
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <CreatePrintProfileModal isOpen onClose={() => {}} profile={profile} />
    </QueryClientProvider>,
  );
}

describe('structured process field round trip', () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.update.mockResolvedValue({}); });

  it('retains native, vector, sentinel and precise strings until an actual edit', () => {
    const values = buildStructuredAdvancedValues(source);
    const settings = buildStructuredAdvancedSettings(values, source);
    for (const key of ['wipe_inward', 'wipe_inward_distance', 'unsupported_wall_last', 'toolchange_cyclic_order', 'toolchange_cyclic_first_layer', 'wipe_tower_sparse_layers_combination']) {
      expect(settings[key]).toEqual(source[key as keyof typeof source]);
    }
    const edited = buildStructuredAdvancedSettings({ ...values, wipe_inward_distance: '0.25' }, source);
    expect(edited.wipe_inward_distance).toBe('0.25');
    expect(source.wipe_inward_distance).toBe('50.000%');
    const cleared = buildStructuredAdvancedSettings({ ...values, toolchange_cyclic_order: '' }, source);
    expect(cleared).toHaveProperty('toolchange_cyclic_order', '');
    expect(buildStructuredAdvancedSettings(buildStructuredAdvancedValues({}), {})).toEqual({});
  });

  it('disables dependencies, reenables on change and saves hidden original values', async () => {
    renderModal();
    const distance = within(await screen.findByRole('group', { name: 'createPrintProfile.fieldLabels.wipe_inward_distance' })).getByRole('textbox');
    expect(distance).toBeDisabled();
    const inward = within(screen.getByRole('group', { name: 'createPrintProfile.fieldLabels.wipe_inward' })).getByRole('combobox');
    fireEvent.change(inward, { target: { value: '1' } });
    expect(distance).not.toBeDisabled();
    fireEvent.change(inward, { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: 'createPrintProfile.tabs.multimaterial' }));
    expect(within(screen.getByRole('group', { name: 'createPrintProfile.fieldLabels.toolchange_cyclic_order' })).getByRole('textbox')).toBeDisabled();
    expect(within(screen.getByRole('group', { name: 'createPrintProfile.fieldLabels.wipe_tower_sparse_layers_combination' })).getByRole('combobox')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'createPrintProfile.saveChanges' }));
    await waitFor(() => expect(mocks.update).toHaveBeenCalledOnce());
    const saved = mocks.update.mock.calls[0][1].orcaslicer_settings;
    for (const [key, value] of Object.entries(source)) expect(saved[key]).toEqual(value);
  }, 20_000);
});
