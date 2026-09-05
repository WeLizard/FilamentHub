import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render as renderView, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';

const authApiMocks = vi.hoisted(() => ({
  login: vi.fn(),
  me: vi.fn(),
  logout: vi.fn(),
  register: vi.fn(),
  createPluginSession: vi.fn(),
  getMaintenanceStatus: vi.fn(),
}));

const authUtilsMocks = vi.hoisted(() => ({
  getRefreshToken: vi.fn(() => 'refresh-token'),
  getToken: vi.fn(() => null),
  getCsrfToken: vi.fn((): string | null => null),
  hasSessionCandidate: vi.fn(() => false),
  isCookieAuthMode: vi.fn(() => false),
  isOrcaEmbedded: vi.fn(() => false),
  removeToken: vi.fn(),
  setRefreshToken: vi.fn(),
  setToken: vi.fn(),
  setUserId: vi.fn(),
  shouldPersistTokensLocally: vi.fn(() => true),
}));

vi.mock('../api/client', () => ({
  authAPI: authApiMocks,
  beginAuthSessionTransition: vi.fn(),
  withAuthSessionLock: (operation: () => Promise<unknown>) => operation(),
}));

vi.mock('../utils/auth', () => authUtilsMocks);

const pluginBridgeMocks = vi.hoisted(() => ({
  isPluginEmbed: vi.fn(() => false),
  reportLogoutToPlugin: vi.fn(),
  reportPluginSessionToPlugin: vi.fn(),
  subscribeToPluginLogout: vi.fn(() => undefined),
  subscribeToPluginAuthRestore: vi.fn(() => undefined),
}));

vi.mock('../utils/pluginBridge', () => pluginBridgeMocks);

import { AuthProvider, useAuth } from '../contexts/AuthContext';

let queryClient: QueryClient;
let currentAuth: ReturnType<typeof useAuth>;
const render = (ui: ReactNode) => renderView(
  <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
);

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

function AuthProbe() {
  const auth = useAuth();
  currentAuth = auth;

  return (
    <div>
      <div data-testid="is-loading">{String(auth.isLoading)}</div>
      <div data-testid="is-authenticated">{String(auth.isAuthenticated)}</div>
      <div data-testid="user-email">{auth.user?.email ?? 'none'}</div>
      <div data-testid="maintenance-mode">{String(auth.isMaintenanceMode)}</div>
      <div data-testid="maintenance-message">{auth.maintenanceMessage ?? 'none'}</div>
      <button onClick={() => auth.login('user@example.com', 'secret')} type="button">
        login
      </button>
      <button onClick={() => auth.logout()} type="button">
        logout
      </button>
      <button
        onClick={() =>
          auth.register({
            email: 'user@example.com',
            username: 'user',
            password: 'secret',
          } as Parameters<typeof auth.register>[0])
        }
        type="button"
      >
        register
      </button>
    </div>
  );
}

describe('AuthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    authUtilsMocks.getToken.mockReturnValue(null);
    authUtilsMocks.isCookieAuthMode.mockReturnValue(false);
    authUtilsMocks.isOrcaEmbedded.mockReturnValue(false);
    authUtilsMocks.shouldPersistTokensLocally.mockReturnValue(true);
    authUtilsMocks.getCsrfToken.mockReturnValue(null);
    authUtilsMocks.hasSessionCandidate.mockImplementation(() => Boolean(authUtilsMocks.getToken())
      || (authUtilsMocks.isCookieAuthMode() && !authUtilsMocks.isOrcaEmbedded()
        && Boolean(authUtilsMocks.getCsrfToken())));
    pluginBridgeMocks.isPluginEmbed.mockReturnValue(false);

    authApiMocks.getMaintenanceStatus.mockResolvedValue({
      maintenance_mode: false,
      message: null,
    });
  });

  it('has unauthenticated initial state after bootstrap', async () => {
    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    );

    expect(screen.getByTestId('is-loading')).toHaveTextContent('true');

    await waitFor(() => {
      expect(screen.getByTestId('is-loading')).toHaveTextContent('false');
      expect(screen.getByTestId('is-authenticated')).toHaveTextContent('false');
      expect(screen.getByTestId('user-email')).toHaveTextContent('none');
    });
  });

  it('login sets authenticated user state', async () => {
    authApiMocks.login.mockResolvedValue({
      access_token: 'access-123',
      refresh_token: 'refresh-456',
    });
    authApiMocks.me.mockResolvedValue({
      id: 7,
      email: 'user@example.com',
      username: 'user',
    });

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('is-loading')).toHaveTextContent('false');
    });

    fireEvent.click(screen.getByRole('button', { name: 'login' }));

    await waitFor(() => {
      expect(screen.getByTestId('is-authenticated')).toHaveTextContent('true');
      expect(screen.getByTestId('user-email')).toHaveTextContent('user@example.com');
    });

    expect(authApiMocks.login).toHaveBeenCalledWith({
      email: 'user@example.com',
      password: 'secret',
    });
    expect(authUtilsMocks.setToken).toHaveBeenCalledWith('access-123');
    expect(authUtilsMocks.setRefreshToken).toHaveBeenCalledWith('refresh-456');
    expect(authUtilsMocks.setUserId).toHaveBeenCalledWith(7);
  });

  it('registration opens the session itself, without signing in again', async () => {
    authApiMocks.register.mockResolvedValue({
      access_token: 'access-123',
      refresh_token: 'refresh-456',
    });
    authApiMocks.me.mockResolvedValue({
      id: 7,
      email: 'user@example.com',
      username: 'user',
    });

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('is-loading')).toHaveTextContent('false');
    });

    fireEvent.click(screen.getByRole('button', { name: 'register' }));

    await waitFor(() => {
      expect(screen.getByTestId('is-authenticated')).toHaveTextContent('true');
    });

    expect(authApiMocks.login).not.toHaveBeenCalled();
    expect(authUtilsMocks.setToken).toHaveBeenCalledWith('access-123');
    expect(authUtilsMocks.setRefreshToken).toHaveBeenCalledWith('refresh-456');
    expect(authUtilsMocks.setUserId).toHaveBeenCalledWith(7);
  });

  it('gives the plugin its capability after registration too', async () => {
    pluginBridgeMocks.isPluginEmbed.mockReturnValue(true);
    authApiMocks.register.mockResolvedValue({
      access_token: 'access-123',
      refresh_token: 'refresh-456',
    });
    authApiMocks.me.mockResolvedValue({
      id: 7,
      email: 'user@example.com',
      username: 'user',
    });
    authApiMocks.createPluginSession.mockResolvedValue({
      plugin_token: 'scoped-plugin-token',
      expires_in: 1800,
      token_type: 'bearer',
    });

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('is-loading')).toHaveTextContent('false');
    });

    fireEvent.click(screen.getByRole('button', { name: 'register' }));

    await waitFor(() => {
      expect(pluginBridgeMocks.reportPluginSessionToPlugin).toHaveBeenCalledWith(
        'scoped-plugin-token',
      );
    });
  });

  it('logout clears user state', async () => {
    authApiMocks.login.mockResolvedValue({
      access_token: 'access-123',
      refresh_token: 'refresh-456',
    });
    authApiMocks.me.mockResolvedValue({
      id: 7,
      email: 'user@example.com',
      username: 'user',
    });
    authApiMocks.logout.mockResolvedValue(undefined);

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('is-loading')).toHaveTextContent('false');
    });

    fireEvent.click(screen.getByRole('button', { name: 'login' }));

    await waitFor(() => {
      expect(screen.getByTestId('is-authenticated')).toHaveTextContent('true');
    });

    fireEvent.click(screen.getByRole('button', { name: 'logout' }));

    await waitFor(() => {
      expect(screen.getByTestId('is-authenticated')).toHaveTextContent('false');
      expect(screen.getByTestId('user-email')).toHaveTextContent('none');
    });

    expect(authApiMocks.logout).toHaveBeenCalledWith('refresh-token');
    expect(authUtilsMocks.removeToken).toHaveBeenCalledTimes(1);
  });

  it('loads maintenance mode from /health for guest session', async () => {
    authApiMocks.getMaintenanceStatus.mockResolvedValue({
      maintenance_mode: true,
      message: 'Scheduled maintenance',
    });

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('maintenance-mode')).toHaveTextContent('true');
      expect(screen.getByTestId('maintenance-message')).toHaveTextContent('Scheduled maintenance');
    });

    expect(authApiMocks.getMaintenanceStatus).toHaveBeenCalledTimes(1);
  });

  it('mints a fresh plugin capability for an existing embedded cookie session', async () => {
    authUtilsMocks.isCookieAuthMode.mockReturnValue(true);
    authUtilsMocks.getCsrfToken.mockReturnValue('csrf-session-hint');
    pluginBridgeMocks.isPluginEmbed.mockReturnValue(true);
    authApiMocks.me.mockResolvedValue({
      id: 7,
      email: 'user@example.com',
      username: 'user',
    });
    authApiMocks.createPluginSession.mockResolvedValue({
      plugin_token: 'scoped-plugin-token',
      expires_in: 1800,
      token_type: 'bearer',
    });

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('is-authenticated')).toHaveTextContent('true');
      expect(pluginBridgeMocks.reportPluginSessionToPlugin).toHaveBeenCalledWith(
        'scoped-plugin-token',
      );
    });

    expect(authApiMocks.createPluginSession).toHaveBeenCalledTimes(1);
  });

  it('does not probe an anonymous cookie browser without a session hint', async () => {
    authUtilsMocks.isCookieAuthMode.mockReturnValue(true);
    authApiMocks.me.mockRejectedValue({ response: { status: 401 } });
    render(<AuthProvider><AuthProbe /></AuthProvider>);
    await waitFor(() => expect(currentAuth.isLoading).toBe(false));
    expect(authApiMocks.me).not.toHaveBeenCalled();
    expect(authApiMocks.getMaintenanceStatus).toHaveBeenCalledOnce();
  });

  it('cannot restore a delayed bootstrap response after logout', async () => {
    authUtilsMocks.isCookieAuthMode.mockReturnValue(true);
    authUtilsMocks.getCsrfToken.mockReturnValue('csrf-session-hint');
    const oldMe = deferred<any>();
    authApiMocks.me.mockReturnValue(oldMe.promise);
    authApiMocks.logout.mockResolvedValue(undefined);
    render(<AuthProvider><AuthProbe /></AuthProvider>);
    await waitFor(() => expect(authApiMocks.me).toHaveBeenCalledOnce());
    await act(async () => { await currentAuth.logout(); });
    await act(async () => { oldMe.resolve({ id: 7, email: 'old@example.com' }); });
    expect(currentAuth.isAuthenticated).toBe(false);
    expect(currentAuth.isLoading).toBe(false);
  });

  it('isolates cached and in-flight private queries when the account changes', async () => {
    authApiMocks.me.mockResolvedValue({ id: 7, email: 'old@example.com' });
    authApiMocks.logout.mockResolvedValue(undefined);
    render(<AuthProvider><AuthProbe /></AuthProvider>);
    await waitFor(() => expect(currentAuth.isLoading).toBe(false));
    await act(async () => { await currentAuth.loginWithToken('account-a'); });
    queryClient.setQueryData(['physical-printers'], [{ name: 'private-account-a' }]);
    const pending = deferred<string>();
    const request = queryClient.fetchQuery({ queryKey: ['pending-private'], queryFn: () => pending.promise }).catch(() => undefined);
    await act(async () => { await currentAuth.logout(); });
    expect(queryClient.getQueryData(['physical-printers'])).toBeUndefined();
    authApiMocks.me.mockResolvedValue({ id: 8, email: 'new@example.com' });
    await act(async () => { await currentAuth.loginWithToken('account-b'); });
    await act(async () => { pending.resolve('private-account-a'); await request; });
    expect(currentAuth.user?.id).toBe(8);
    expect(queryClient.getQueryData(['physical-printers'])).toBeUndefined();
    expect(queryClient.getQueryData(['pending-private'])).toBeUndefined();
  });

  it('does not report a late plugin capability after logout', async () => {
    pluginBridgeMocks.isPluginEmbed.mockReturnValue(true);
    const capability = deferred<any>();
    authApiMocks.me.mockResolvedValue({ id: 7, email: 'old@example.com' });
    authApiMocks.createPluginSession.mockReturnValue(capability.promise);
    authApiMocks.logout.mockResolvedValue(undefined);
    render(<AuthProvider><AuthProbe /></AuthProvider>);
    await waitFor(() => expect(currentAuth.isLoading).toBe(false));
    await act(async () => { await currentAuth.loginWithToken('account-a'); });
    await act(async () => { await currentAuth.logout(); });
    await act(async () => { capability.resolve({ plugin_token: 'obsolete-capability', expires_in: 1800 }); });
    expect(pluginBridgeMocks.reportPluginSessionToPlugin).not.toHaveBeenCalled();
  });

  it('preserves same-account caches and credentials on a temporary session check failure', async () => {
    authUtilsMocks.hasSessionCandidate.mockReturnValue(true);
    authApiMocks.me.mockResolvedValue({ id: 7, email: 'same@example.com' });
    render(<AuthProvider><AuthProbe /></AuthProvider>);
    await waitFor(() => expect(currentAuth.user?.id).toBe(7));
    queryClient.setQueryData(['physical-printers'], ['same-account']);
    await act(async () => { await currentAuth.refreshUser(); });
    expect(queryClient.getQueryData(['physical-printers'])).toEqual(['same-account']);
    const log = vi.spyOn(console, 'error').mockImplementation(() => {});
    authApiMocks.me.mockRejectedValue({ response: { status: 500 } });
    await act(async () => { await currentAuth.refreshUser(); });
    expect(currentAuth.user?.id).toBe(7);
    expect(authUtilsMocks.removeToken).not.toHaveBeenCalled();
    expect(log).toHaveBeenCalledOnce();
    log.mockRestore();
  });

  it.each(['success', 'failure'])('ignores stale refreshUser %s after switching accounts', async (outcome) => {
    authUtilsMocks.hasSessionCandidate.mockReturnValue(true);
    authApiMocks.me.mockResolvedValue({ id: 7, email: 'old@example.com' });
    render(<AuthProvider><AuthProbe /></AuthProvider>);
    await waitFor(() => expect(currentAuth.user?.id).toBe(7));
    const old = deferred<any>();
    authApiMocks.me.mockReturnValueOnce(old.promise);
    const pending = currentAuth.refreshUser();
    authApiMocks.me.mockResolvedValue({ id: 8, email: 'new@example.com' });
    await act(async () => { await currentAuth.loginWithToken('new-account'); });
    authUtilsMocks.removeToken.mockClear();
    await act(async () => {
      if (outcome === 'success') old.resolve({ id: 7, email: 'old@example.com' });
      else old.reject({ response: { status: 401 } });
      await pending;
    });
    expect(currentAuth.user?.id).toBe(8);
    expect(authUtilsMocks.removeToken).not.toHaveBeenCalled();
  });

  it('does not establish a superseded login after logout', async () => {
    const login = deferred<any>();
    authApiMocks.login.mockReturnValue(login.promise);
    authApiMocks.logout.mockResolvedValue(undefined);
    render(<AuthProvider><AuthProbe /></AuthProvider>);
    await waitFor(() => expect(currentAuth.isLoading).toBe(false));
    let pending!: Promise<unknown>;
    act(() => { pending = currentAuth.login('old@example.com', 'password').catch((error) => error); });
    await act(async () => { await currentAuth.logout(); });
    await act(async () => { login.resolve({ access_token: 'obsolete' }); await pending; });
    expect(currentAuth.isAuthenticated).toBe(false);
    expect(authUtilsMocks.setToken).not.toHaveBeenCalled();
  });

  it('invalidates older session checks when /me confirms a different account', async () => {
    authUtilsMocks.hasSessionCandidate.mockReturnValue(true);
    authApiMocks.me.mockResolvedValue({ id: 7, email: 'a@example.com' });
    render(<AuthProvider><AuthProbe /></AuthProvider>);
    await waitFor(() => expect(currentAuth.user?.id).toBe(7));
    const old = deferred<any>();
    authApiMocks.me.mockReturnValueOnce(old.promise).mockResolvedValueOnce({ id: 8, email: 'b@example.com' });
    const pending = currentAuth.refreshUser();
    await act(async () => { await currentAuth.refreshUser(); });
    await act(async () => { old.resolve({ id: 7, email: 'a@example.com' }); await pending; });
    expect(currentAuth.user?.id).toBe(8);
  });

  it('keeps an active public query usable after identity changes', async () => {
    const fetchPublic = vi.fn().mockResolvedValue('catalog-v1');
    function PublicProbe() {
      const { data } = useQuery({ queryKey: ['public-catalog'], queryFn: fetchPublic });
      return <div data-testid="public-catalog">{data}</div>;
    }
    authApiMocks.me.mockResolvedValue({ id: 7, email: 'account@example.com' });
    render(<AuthProvider><AuthProbe /><PublicProbe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('public-catalog')).toHaveTextContent('catalog-v1'));
    await waitFor(() => expect(currentAuth.isLoading).toBe(false));
    await act(async () => { await currentAuth.loginWithToken('account'); });
    fetchPublic.mockResolvedValue('catalog-v2');
    await act(async () => { await queryClient.invalidateQueries({ queryKey: ['public-catalog'] }); });
    await waitFor(() => expect(screen.getByTestId('public-catalog')).toHaveTextContent('catalog-v2'));
  });

  it('still restores an Orca token injected after bootstrap starts', async () => {
    authUtilsMocks.isOrcaEmbedded.mockReturnValue(true);
    authApiMocks.me.mockResolvedValue({ id: 7, email: 'orca@example.com' });
    render(<AuthProvider><AuthProbe /></AuthProvider>);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 150)); });
    expect(authApiMocks.me).not.toHaveBeenCalled();
    authUtilsMocks.getToken.mockReturnValue('injected-orca-token' as any);
    await waitFor(() => expect(currentAuth.user?.id).toBe(7));
    expect(authApiMocks.me).toHaveBeenCalledOnce();
  });

  it('does not refetch an active private query as a guest during logout', async () => {
    const accounts: Array<number | undefined> = [];
    function PrivateProbe() {
      const { user } = useAuth();
      const { data } = useQuery({
        queryKey: ['physical-printers'],
        enabled: Boolean(user), staleTime: 60_000,
        queryFn: async () => { accounts.push(user?.id); return [`printer-${user?.id}`]; },
      });
      return <div data-testid="private-printers">{data?.join(',')}</div>;
    }
    authApiMocks.me.mockResolvedValue({ id: 7, email: 'a@example.com' });
    authApiMocks.logout.mockResolvedValue(undefined);
    render(<AuthProvider><AuthProbe /><PrivateProbe /></AuthProvider>);
    await waitFor(() => expect(currentAuth.isLoading).toBe(false));
    await act(async () => { await currentAuth.loginWithToken('account-a'); });
    await waitFor(() => expect(screen.getByTestId('private-printers')).toHaveTextContent('printer-7'));
    await act(async () => { await currentAuth.logout(); });
    expect(accounts).not.toContain(undefined);
    expect(screen.getByTestId('private-printers')).toBeEmptyDOMElement();
    authApiMocks.me.mockResolvedValue({ id: 8, email: 'b@example.com' });
    await act(async () => { await currentAuth.loginWithToken('account-b'); });
    await waitFor(() => expect(screen.getByTestId('private-printers')).toHaveTextContent('printer-8'));
    expect(accounts).not.toContain(undefined);
  });
});
