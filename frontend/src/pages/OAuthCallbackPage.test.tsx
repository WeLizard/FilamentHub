import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { OAuthCallbackPage } from './OAuthCallbackPage';

const auth = vi.hoisted(() => ({
  user: null as { legal_onboarding_required: boolean } | null,
  isLoading: false,
  loginWithToken: vi.fn(),
}));
const api = vi.hoisted(() => ({
  oauthCallback: vi.fn(),
  failPluginOAuthFlow: vi.fn(),
  completePluginOAuthFlow: vi.fn(),
}));

vi.mock('../contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('../api/client', () => ({ authAPI: api }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

function open(address: string) {
  window.history.replaceState(null, '', address);
  render(
    <MemoryRouter initialEntries={[address]}>
      <Routes>
        <Route path="/oauth/callback/:provider" element={<OAuthCallbackPage />} />
        <Route path="/" element={<p>home</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('OAuthCallbackPage', () => {
  beforeEach(() => {
    auth.user = null;
    auth.isLoading = false;
    api.oauthCallback.mockReset();
    sessionStorage.clear();
  });

  it('takes a signed-in reader home when the answer in the address was already used', async () => {
    auth.user = { legal_onboarding_required: false };
    api.oauthCallback.mockRejectedValue({
      response: { data: { detail: { code: 'ERR_OAUTH_INVALID_STATE' } } },
    });

    open('/oauth/callback/google?code=used&state=used');

    expect(await screen.findByText('home')).toBeInTheDocument();
    expect(screen.queryByText('oauthCallback.error_title')).not.toBeInTheDocument();
  });

  it('removes the one-time code from the address before exchanging it', async () => {
    api.oauthCallback.mockReturnValue(new Promise(() => {}));

    open('/oauth/callback/google?code=fresh&state=fresh');

    await waitFor(() => expect(api.oauthCallback).toHaveBeenCalledWith('google', 'fresh', 'fresh'));
    expect(window.location.search).toBe('');
  });

  it('tells a reader who is not signed in that the link is spent', async () => {
    open('/oauth/callback/google');

    expect(await screen.findByText('oauthCallback.error_title')).toBeInTheDocument();
    expect(api.oauthCallback).not.toHaveBeenCalled();
  });
});
