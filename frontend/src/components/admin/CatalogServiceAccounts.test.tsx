import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CatalogServiceAccounts, buildContributorInstructions } from './CatalogServiceAccounts';
import type { CatalogCurationServiceAccount } from '../../types/api';

const mocks = vi.hoisted(() => ({ list: vi.fn(), create: vi.fn(), revoke: vi.fn() }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));
vi.mock('../../api/client', () => ({ adminCatalogCurationServiceAccountAPI: mocks }));

const account = (overrides: Partial<CatalogCurationServiceAccount> = {}): CatalogCurationServiceAccount => ({
  id: 12, name: 'Catalog contributor', created_by_user_id: 1,
  created_at: '2026-10-18T12:00:00Z', expires_at: '2027-10-18T12:00:00Z', revoked_at: null, last_used_at: null,
  ...overrides,
});

function mount(onClose = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><CatalogServiceAccounts onClose={onClose} /></QueryClientProvider>);
  return onClose;
}

describe('catalog service accounts dialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.list.mockResolvedValue({ items: [], total: 0 });
    mocks.create.mockResolvedValue({ account: account(), token: 'fhca_one-time-secret' });
    mocks.revoke.mockResolvedValue(account({ revoked_at: '2026-10-19T12:00:00Z' }));
  });

  it('shows the key once with connection instructions, copies both, and never shows the key again', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    const onClose = mount();

    fireEvent.change(screen.getByRole('textbox'), { target: { value: '  Gemini  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.serviceAccounts.create' }));
    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith('Gemini'));

    expect(await screen.findByRole('textbox', { name: 'adminCatalogImport.serviceAccounts.token' })).toHaveValue('fhca_one-time-secret');
    const instructions = screen.getByLabelText('adminCatalogImport.serviceAccounts.connect');
    expect(instructions).toHaveTextContent(`${window.location.origin}/api/v1/service/catalog/curation/proposals`);
    expect(instructions).toHaveTextContent('Authorization: Bearer fhca_one-time-secret');
    expect(screen.queryByRole('button', { name: 'adminCatalogImport.serviceAccounts.hide' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.serviceAccounts.copyForExecutor' }));
    await waitFor(() => expect(writeText).toHaveBeenCalled());
    const copied = writeText.mock.calls[0][0] as string;
    expect(copied).toBe(buildContributorInstructions(window.location.origin, 'fhca_one-time-secret'));
    expect(copied).toContain('Authorization: Bearer fhca_one-time-secret');
    expect(copied).toContain('/api/v1/service/catalog/curation/proposals');
    expect(copied).toContain('PATCH');

    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.serviceAccounts.done' }));
    expect(onClose).toHaveBeenCalled();
  });

  it('keeps the dialog open on Escape once the one-time key is shown, and closes on Escape before that', async () => {
    const onClose = mount();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
    onClose.mockClear();
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Gemini' } });
    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.serviceAccounts.create' }));
    await screen.findByDisplayValue('fhca_one-time-secret');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByDisplayValue('fhca_one-time-secret')).toBeInTheDocument();
  });

  it('opens fresh after closing: the key of a previous dialog is gone', async () => {
    const first = render(<QueryClientProvider client={new QueryClient()}><CatalogServiceAccounts onClose={() => undefined} /></QueryClientProvider>);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Gemini' } });
    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.serviceAccounts.create' }));
    await screen.findByDisplayValue('fhca_one-time-secret');
    first.unmount();
    render(<QueryClientProvider client={new QueryClient()}><CatalogServiceAccounts onClose={() => undefined} /></QueryClientProvider>);
    expect(screen.queryByDisplayValue('fhca_one-time-secret')).not.toBeInTheDocument();
  });

  it('requires confirmation before revoking and lists executors compactly', async () => {
    const active = account();
    const revoked = account({ revoked_at: '2026-10-19T12:00:00Z' });
    mocks.list.mockResolvedValueOnce({ items: [active], total: 1 }).mockResolvedValue({ items: [revoked], total: 1 });
    mount();
    const row = await screen.findByText(active.name).then((name) => name.closest('div.flex'));
    expect(row).toHaveTextContent('#12');
    fireEvent.click(within(row as HTMLElement).getByRole('button', { name: 'adminCatalogImport.serviceAccounts.revoke' }));
    expect(mocks.revoke).not.toHaveBeenCalled();
    fireEvent.click(within(row as HTMLElement).getByRole('button', { name: 'adminCatalogImport.serviceAccounts.cancel' }));
    fireEvent.click(within(row as HTMLElement).getByRole('button', { name: 'adminCatalogImport.serviceAccounts.revoke' }));
    fireEvent.click(within(row as HTMLElement).getByRole('button', { name: 'adminCatalogImport.serviceAccounts.revoke' }));
    await waitFor(() => expect(mocks.revoke).toHaveBeenCalledWith(active.id));
    await waitFor(() => expect(screen.getByText('adminCatalogImport.serviceAccounts.revoked')).toBeVisible());
  });

  it('labels revoked and expired executors without offering revoke', async () => {
    mocks.list.mockResolvedValue({ items: [
      account({ id: 21, name: 'Revoked', revoked_at: '2026-10-19T12:00:00Z' }),
      account({ id: 22, name: 'Expired', expires_at: '2020-01-01T00:00:00Z' }),
    ], total: 2 });
    mount();
    expect(await screen.findByText('adminCatalogImport.serviceAccounts.revoked')).toBeVisible();
    expect(screen.getByText('adminCatalogImport.serviceAccounts.expired')).toBeVisible();
    expect(screen.queryAllByRole('button', { name: 'adminCatalogImport.serviceAccounts.revoke' })).toHaveLength(0);
  });
});
