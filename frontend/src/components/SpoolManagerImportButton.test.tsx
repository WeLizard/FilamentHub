import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SpoolImportButton } from './SpoolManagerImportButton';

const { importMock, previewMock, successMock } = vi.hoisted(() => ({
  importMock: vi.fn(),
  previewMock: vi.fn(),
  successMock: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('../api/client', () => ({
  spoolsAPI: {
    previewImport: (...args: unknown[]) => previewMock(...args),
    importFile: (...args: unknown[]) => importMock(...args),
  },
}));

vi.mock('./Toast', () => ({
  toast: {
    success: (...args: unknown[]) => successMock(...args),
  },
}));

const preview = {
  file_name: 'spools.csv',
  file_sha256: 'sha256',
  total_rows: 3,
  importable_rows: 2,
  matched_rows: 1,
  unmatched_rows: 1,
  duplicate_rows: 1,
  invalid_rows: 0,
  detected_format: 'octoprint_spoolmanager_csv',
  detected_label: 'OctoPrint SpoolManager',
  mapping_required: false,
  available_columns: [],
  sample_rows: [],
  suggested_mapping: null,
  required_fields: [],
  rows: [
    {
      row_number: 2,
      fingerprint: 'matched',
      status: 'ready',
      spool_name: 'PLA Red',
      vendor: 'Example',
      material: 'PLA',
      color_name: 'Red',
      color_hex: '#FF0000',
      serial_number: null,
      initial_weight_g: 1000,
      used_weight_g: 100,
      remaining_weight_g: 900,
      empty_spool_weight_g: 200,
      price: 20,
      currency: 'EUR',
      suggested_filament: {
        id: 11,
        name: 'PLA Red',
        brand_name: 'Example',
        material_type: 'PLA',
        color_name: 'Red',
        color_hex: '#FF0000',
        reason: 'name',
      },
      warnings: [],
    },
    {
      row_number: 3,
      fingerprint: 'unmatched',
      status: 'ready',
      spool_name: 'Unknown PETG',
      vendor: 'Unknown',
      material: 'PETG',
      color_name: null,
      color_hex: null,
      serial_number: null,
      initial_weight_g: 750,
      used_weight_g: 0,
      remaining_weight_g: 750,
      empty_spool_weight_g: null,
      price: null,
      currency: null,
      suggested_filament: null,
      warnings: ['unmatched_catalog'],
    },
    {
      row_number: 4,
      fingerprint: 'existing',
      status: 'already_imported',
      spool_name: 'Already imported',
      vendor: 'Example',
      material: 'PLA',
      color_name: null,
      color_hex: null,
      serial_number: null,
      initial_weight_g: 1000,
      used_weight_g: 500,
      remaining_weight_g: 500,
      empty_spool_weight_g: null,
      price: null,
      currency: null,
      suggested_filament: null,
      warnings: ['already_imported'],
    },
  ],
};

describe('SpoolImportButton', () => {
  beforeEach(() => {
    previewMock.mockReset();
    importMock.mockReset();
    successMock.mockReset();
    previewMock.mockResolvedValue(preview);
    importMock.mockResolvedValue({
      created: 2,
      skipped_existing: 0,
      skipped_unselected: 1,
      invalid: 0,
      created_spool_ids: [101, 102],
    });
  });

  it('previews the CSV, selects only importable rows, and imports them', async () => {
    const onImported = vi.fn();
    const { container } = render(<SpoolImportButton onImported={onImported} />);
    const file = new File(['Spool Name,Vendor,Material\nPLA Red,Example,PLA'], 'spools.csv', {
      type: 'text/csv',
    });
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();

    fireEvent.change(input!, { target: { files: [file] } });

    await waitFor(() => expect(previewMock).toHaveBeenCalledWith(file));
    expect(await screen.findByText('PLA Red')).toBeInTheDocument();
    expect(screen.getByText('Unknown PETG')).toBeInTheDocument();
    expect(screen.getByText('Already imported')).toBeInTheDocument();

    const importButton = screen.getByRole('button', {
      name: 'profilePage.spoolManagerImport.importSelected',
    });
    fireEvent.click(importButton);

    await waitFor(() =>
      expect(importMock).toHaveBeenCalledWith(
        file,
        ['matched', 'unmatched'],
        undefined,
      ),
    );
    expect(onImported).toHaveBeenCalledTimes(1);
    expect(successMock).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('PLA Red')).not.toBeInTheDocument();
  });
});
