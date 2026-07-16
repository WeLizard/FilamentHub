import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

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
}));

vi.mock('../utils/auth', () => authUtilsMocks);

const pluginBridgeMocks = vi.hoisted(() => ({
  isPluginEmbed: vi.fn(() => false),
  reportLogoutToPlugin: vi.fn(),
  reportPluginSessionToPlugin: vi.fn(),
  subscribeToPluginLogout: vi.fn(() => undefined),
}));

vi.mock('../utils/pluginBridge', () => pluginBridgeMocks);

import { AuthProvider, useAuth } from '../contexts/AuthContext';

function AuthProbe() {
  const auth = useAuth();

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
    </div>
  );
}

describe('AuthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    authUtilsMocks.getToken.mockReturnValue(null);
    authUtilsMocks.isCookieAuthMode.mockReturnValue(false);
    authUtilsMocks.isOrcaEmbedded.mockReturnValue(false);
    authUtilsMocks.shouldPersistTokensLocally.mockReturnValue(true);
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
});
