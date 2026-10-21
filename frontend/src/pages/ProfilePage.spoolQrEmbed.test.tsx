import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  embed: false,
  listPresets: vi.fn(),
  listPrinters: vi.fn(),
}));

vi.mock('react-i18next', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-i18next')>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../contexts/AuthContext', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../contexts/AuthContext')>()),
  useAuth: () => ({ user: { id: 1 } }),
}));

vi.mock('../hooks/useUserCurrency', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks/useUserCurrency')>()),
  useUserCurrency: () => ({ currency: 'RUB' }),
}));

vi.mock('../utils/pluginBridge', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../utils/pluginBridge')>()),
  isPluginEmbed: () => mocks.embed,
}));

vi.mock('../api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/client')>();
  return {
    ...original,
    physicalPrintersAPI: { ...original.physicalPrintersAPI, list: mocks.listPrinters },
    presetsAPI: { ...original.presetsAPI, list: mocks.listPresets },
  };
});

import { SpoolForm } from './ProfilePage';

function renderForm() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <SpoolForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'profilePage.spoolAddModal.scanQr' }));
}

describe('SpoolForm QR camera scan', () => {
  beforeEach(() => {
    mocks.embed = false;
    mocks.listPresets.mockResolvedValue({ items: [] });
    mocks.listPrinters.mockResolvedValue([]);
  });

  it('offers camera scanning outside the plugin', () => {
    renderForm();

    expect(
      screen.getByRole('button', { name: 'profilePage.spoolAddModal.scanQrCameraStart' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('profilePage.spoolAddModal.scanQrUsePhoneHint')).not.toBeInTheDocument();
  });

  it('hides camera scanning inside the plugin but keeps manual code entry and a phone hint', () => {
    mocks.embed = true;
    renderForm();

    expect(
      screen.queryByRole('button', { name: 'profilePage.spoolAddModal.scanQrCameraStart' }),
    ).not.toBeInTheDocument();
    expect(screen.getByText('profilePage.spoolAddModal.scanQrUsePhoneHint')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('profilePage.spoolAddModal.scanQrPlaceholder')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'profilePage.spoolAddModal.scanQrApply' }),
    ).toBeInTheDocument();
  });
});
