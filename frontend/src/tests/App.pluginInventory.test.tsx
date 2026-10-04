import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  pluginEmbed: false,
  user: null as null | { role: string; legal_onboarding_required: boolean },
}));

vi.mock('../contexts/AuthContext', () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => ({
    user: state.user,
    isMaintenanceMode: false,
    maintenanceMessage: '',
    clearMaintenanceMode: vi.fn(),
  }),
}));

vi.mock('../utils/pluginBridge', () => ({
  isPluginEmbed: () => state.pluginEmbed,
  preserveDirectPluginBridgeBinding: vi.fn(),
  subscribeToPluginNavigation: () => vi.fn(),
  subscribeToPluginNotice: () => vi.fn(),
  subscribeToPluginSyncResult: () => vi.fn(),
  subscribeToPluginRecoverList: () => vi.fn(),
  subscribeToPluginSliceReports: () => vi.fn(),
  watchPendingPluginSliceReports: () => vi.fn(),
  sendPluginSliceReportResult: vi.fn(),
  sendRecoverImport: vi.fn(),
  isDirectPluginHost: () => state.pluginEmbed,
}));

vi.mock('../api/client', () => ({ orcaSlicesAPI: { report: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('../components/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
}));
vi.mock('../components/ProtectedRoute', () => ({
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('../pages/CatalogPage', () => ({ CatalogPage: () => <div data-testid="catalog-page" /> }));
vi.mock('../pages/ProfilePage', () => ({ ProfilePage: () => <div data-testid="profile-page" /> }));
vi.mock('../components/Toast', () => ({ ToastContainer: () => null, toast: { show: vi.fn() } }));
vi.mock('../hooks/useCurrencyCatalogue', () => ({ useCurrencyCatalogue: () => undefined }));
vi.mock('../hooks/useTokenRefresh', () => ({ useTokenRefresh: () => undefined }));
vi.mock('../hooks/usePluginDeveloperMode', () => ({ usePluginDeveloperMode: () => false }));
vi.mock('../utils/problemReport', () => ({
  openProblemReport: vi.fn(),
  subscribeToProblemReport: () => vi.fn(),
}));

import App from '../App';

function renderApp(initialEntry = '/') {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('App inventory landing', () => {
  beforeEach(() => {
    state.pluginEmbed = false;
    state.user = { role: 'user', legal_onboarding_required: false };
  });

  it('opens the inventory page at the dedicated plugin landing route', async () => {
    state.pluginEmbed = true;

    renderApp('/embed#fh_bridge=plugin-session');

    expect(await screen.findByTestId('profile-page')).toBeInTheDocument();
    expect(screen.queryByTestId('catalog-page')).not.toBeInTheDocument();
  });

  it('keeps the ordinary website root on the catalog', () => {
    renderApp();

    expect(screen.getByTestId('catalog-page')).toBeInTheDocument();
    expect(screen.queryByTestId('profile-page')).not.toBeInTheDocument();
  });

  it('keeps the catalog available through its existing plugin route', () => {
    state.pluginEmbed = true;

    renderApp('/embed/catalog?lng=ru#fh_bridge=plugin-session');

    expect(screen.getByTestId('catalog-page')).toBeInTheDocument();
    expect(screen.queryByTestId('profile-page')).not.toBeInTheDocument();
  });
});
