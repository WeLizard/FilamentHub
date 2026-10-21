import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { UserSpool } from '../api/client';
import { SpoolCard } from './ProfilePage';

vi.mock('react-i18next', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-i18next')>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('../hooks/useUserCurrency', () => ({ useUserCurrency: () => ({ currency: 'RUB' }) }));
vi.mock('../components/SpoolLabelButton', () => ({ SpoolLabelButton: () => null }));
vi.mock('../components/SpoolTagsButton', () => ({ SpoolTagsButton: () => null }));
vi.mock('../components/SpoolUsageModal', () => ({ SpoolUsageModal: () => null }));

const importedSpool = {
  id: 11, user_id: 1, filament: null, filament_id: null, compat_import_id: 7,
  extra: { display_name: 'Imported PLA', vendor: 'Vendor', material: 'PLA' },
  initial_weight_g: 1000, used_weight_g: 0, remaining_weight_g: 1000, remaining_pct: 100,
  price: null, currency: null, state: 'shelf', source: 'spoolman', lot_nr: null, comment: null,
  created_at: '2026-10-20T00:00:00Z', updated_at: '2026-10-20T00:00:00Z', last_used_at: null,
} satisfies UserSpool;

describe('Unlinked import card', () => {
  it.each(['grid', 'list'] as const)('opens the catalog review without a preset draft in %s view', (viewMode) => {
    const onResolveCompatImport = vi.fn();
    const onResolveImport = vi.fn();
    render(<SpoolCard spool={importedSpool} viewMode={viewMode} onResolveCompatImport={onResolveCompatImport} onResolveImport={onResolveImport} />);
    fireEvent.click(screen.getByRole('button', { name: 'profilePage.spoolImportResolve.open' }));
    expect(onResolveCompatImport).toHaveBeenCalledWith(7);
    expect(onResolveImport).not.toHaveBeenCalled();
  });

  it('keeps the existing CSV draft action for imports without a compatibility group', () => {
    const onResolveImport = vi.fn();
    render(<SpoolCard spool={{ ...importedSpool, compat_import_id: null, extra: { ...importedSpool.extra, import_draft_id: '91' } }} onResolveImport={onResolveImport} />);
    fireEvent.click(screen.getByRole('button', { name: 'profilePage.spoolManagerImport.completeImport' }));
    expect(onResolveImport).toHaveBeenCalledWith(91);
    expect(screen.queryByRole('button', { name: 'profilePage.spoolImportResolve.open' })).not.toBeInTheDocument();
  });
});
