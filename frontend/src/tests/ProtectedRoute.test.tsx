import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { ProtectedRoute } from '../components/ProtectedRoute';

const state = vi.hoisted(() => ({
  isAuthenticated: false, isLoading: false,
  user: null as { role: string } | null,
  unauthenticatedReason: null as 'session_expired' | null,
}));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => state }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname}{location.search}</span>;
}
function renderRoute(requiredRole?: 'admin') {
  return render(<MemoryRouter initialEntries={['/profile?tab=spools']}>
    <LocationProbe />
    <Routes>
      <Route path="/profile" element={<ProtectedRoute requiredRole={requiredRole}><span>private content</span></ProtectedRoute>} />
      <Route path="/" element={<span>home</span>} />
    </Routes>
  </MemoryRouter>);
}

describe('ProtectedRoute authentication states', () => {
  beforeEach(() => {
    state.isAuthenticated = false; state.isLoading = false;
    state.user = null; state.unauthenticatedReason = null;
  });
  afterEach(() => vi.useRealTimers());

  it('keeps the expired-session explanation visible and returns to the same page after sign-in', async () => {
    vi.useFakeTimers();
    state.unauthenticatedReason = 'session_expired';
    renderRoute();
    expect(screen.getByText('protectedRoute.session_expired_title')).toBeInTheDocument();
    expect(screen.queryByText('protectedRoute.redirect_countdown')).not.toBeInTheDocument();
    expect(screen.queryByText('private content')).not.toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(6_000); });
    expect(screen.getByTestId('location')).toHaveTextContent('/profile?tab=spools');
    fireEvent.click(screen.getByRole('button', { name: 'protectedRoute.login_button' }));
    expect(screen.getByTestId('location')).toHaveTextContent('/?auth=login&return_url=%2Fprofile%3Ftab%3Dspools');
  });

  it('preserves the guest explanation and its existing redirect', async () => {
    vi.useFakeTimers();
    renderRoute();
    expect(screen.getByText('protectedRoute.auth_required_title')).toBeInTheDocument();
    expect(screen.queryByText('protectedRoute.session_expired_title')).not.toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(screen.getByTestId('location')).toHaveTextContent('/');
    expect(screen.getByText('home')).toBeInTheDocument();
  });

  it('keeps a role denial separate from expired authentication', () => {
    state.isAuthenticated = true; state.user = { role: 'user' };
    renderRoute('admin');
    expect(screen.getByText('protectedRoute.access_denied_title')).toBeInTheDocument();
    expect(screen.queryByText('protectedRoute.session_expired_title')).not.toBeInTheDocument();
    expect(screen.queryByText('private content')).not.toBeInTheDocument();
  });

  it('does not mount protected consumers until authentication resolves', () => {
    state.isLoading = true;
    renderRoute();
    expect(screen.getByText('protectedRoute.loading')).toBeInTheDocument();
    expect(screen.queryByText('private content')).not.toBeInTheDocument();
  });
});
