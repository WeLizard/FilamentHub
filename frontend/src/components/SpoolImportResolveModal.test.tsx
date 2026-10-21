import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AxiosError } from 'axios';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SpoolCompatImportDetail, SpoolCompatImportPreview } from '../api/client';
import { SpoolImportResolveModal } from './SpoolImportResolveModal';

const api = vi.hoisted(() => ({
  getImport: vi.fn(),
  previewImportMatch: vi.fn(),
  resolveImport: vi.fn(),
  listFilaments: vi.fn(),
}));

vi.mock('../api/client', () => ({
  spoolsAPI: {
    getImport: api.getImport,
    previewImportMatch: api.previewImportMatch,
    resolveImport: api.resolveImport,
  },
  filamentsAPI: { list: api.listFilaments },
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('./ModalOverlay', () => ({ ModalOverlay: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock('./Dropdown', () => ({
  Dropdown: ({ label, options, onChange, value }: {
    label: string;
    options: Array<{ value: number; label: string }>;
    onChange: (value: number) => void;
    value: number | string;
  }) => <label>{label}<select aria-label={label} value={value} onChange={(event) => onChange(Number(event.target.value))}>
    <option value="">Choose</option>
    {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
  </select></label>,
}));

const detail: SpoolCompatImportDetail = {
  id: 7,
  revision: 4,
  source: 'spoolman',
  material: {
    name: 'Imported PLA', brand_name: 'Vendor', material_type: 'PLA', color_hex: '#ff0000',
    diameter: 1.75, density: 1.24, weight: 1000, spool_weight: 200,
    settings_extruder_temp: null, settings_bed_temp: null,
  },
  spools: [{ id: 11, name: 'First spool' }, { id: 12, name: 'Second spool' }],
  resolved_filament_id: null,
};
const firstPreviewToken = '4'.repeat(64);
const refreshedPreviewToken = '5'.repeat(64);
const preview: SpoolCompatImportPreview = {
  ...detail,
  preview_token: firstPreviewToken,
  target_filament: {
    id: 42, name: 'Catalog PLA', brand_name: 'Catalog brand', material_type: 'PLA',
    color_hex: '#00ff00', diameter: 1.75, density: 1.24,
  },
  differences: [{ field: 'color_hex', imported: '#ff0000', catalog: '#00ff00' }],
};

function renderModal(onResolved = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}>
    <SpoolImportResolveModal importId={7} onClose={vi.fn()} onResolved={onResolved} />
  </QueryClientProvider>);
}

async function selectCatalogMatch() {
  const selector = await screen.findByRole('combobox', { name: 'profilePage.spoolImportResolve.chooseFilament' });
  fireEvent.change(selector, { target: { value: '42' } });
  await screen.findByText('#00ff00');
}

describe('Spool import review', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getImport.mockResolvedValue(detail);
    api.previewImportMatch.mockResolvedValue(preview);
    api.resolveImport.mockResolvedValue({ id: 7, revision: 5, filament_id: 42, spool_ids: [11, 12] });
    api.listFilaments.mockResolvedValue({ items: [{ id: 42, brand_name: 'Catalog brand', name: 'Catalog PLA', material_type: 'PLA' }] });
  });

  it('shows all affected spools and differences before linking the selected catalog filament', async () => {
    api.previewImportMatch.mockResolvedValueOnce({
      ...preview,
      material: { ...preview.material, name: 'Updated PLA' },
      spools: [...preview.spools, { id: 13, name: 'Late spool' }],
    });
    const onResolved = vi.fn();
    renderModal(onResolved);
    expect(await screen.findByText(/First spool/)).toBeInTheDocument();
    expect(screen.getByText(/Second spool/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'profilePage.spoolImportResolve.confirm' })).toBeDisabled();

    await selectCatalogMatch();
    expect(api.previewImportMatch).toHaveBeenCalledWith(7, 42);
    expect(screen.getByText('#00ff00')).toBeInTheDocument();
    expect(screen.getByText(/Late spool/)).toBeInTheDocument();
    expect(screen.getAllByText(/Updated PLA/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: 'profilePage.spoolImportResolve.confirm' }));
    await waitFor(() => expect(api.resolveImport).toHaveBeenCalledWith(7, 42, 4, firstPreviewToken));
    expect(onResolved).toHaveBeenCalledOnce();
  });

  it('keeps the match after a conflict and requires another explicit confirmation with a fresh revision', async () => {
    const conflict = Object.assign(new AxiosError('conflict'), { response: { status: 409, data: { detail: { code: 'ERR_CONFLICT' } } } });
    api.resolveImport.mockRejectedValueOnce(conflict);
    api.getImport.mockResolvedValueOnce(detail).mockResolvedValueOnce({ ...detail, revision: 5 });
    api.previewImportMatch.mockResolvedValueOnce(preview).mockResolvedValueOnce({ ...preview, revision: 5, preview_token: refreshedPreviewToken });
    renderModal();
    await selectCatalogMatch();
    fireEvent.click(screen.getByRole('button', { name: 'profilePage.spoolImportResolve.confirm' }));

    await screen.findByText('profilePage.spoolImportResolve.conflict');
    await waitFor(() => expect(api.previewImportMatch).toHaveBeenCalledTimes(2));
    expect(api.resolveImport).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('combobox', { name: 'profilePage.spoolImportResolve.chooseFilament' })).toHaveValue('42');
    await waitFor(() => expect(screen.getByRole('button', { name: 'profilePage.spoolImportResolve.confirm' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'profilePage.spoolImportResolve.confirm' }));
    await waitFor(() => expect(api.resolveImport).toHaveBeenLastCalledWith(7, 42, 5, refreshedPreviewToken));
  });

  it('retains the selected match and review on a transient resolve error', async () => {
    api.resolveImport.mockRejectedValueOnce(new AxiosError('offline'));
    renderModal();
    await selectCatalogMatch();
    fireEvent.click(screen.getByRole('button', { name: 'profilePage.spoolImportResolve.confirm' }));
    expect(await screen.findByText('profilePage.spoolImportResolve.requestFailed')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'profilePage.spoolImportResolve.chooseFilament' })).toHaveValue('42');
    expect(screen.getAllByText('#ff0000').length).toBeGreaterThan(0);
    expect(api.resolveImport).toHaveBeenCalledTimes(1);
  });
});
