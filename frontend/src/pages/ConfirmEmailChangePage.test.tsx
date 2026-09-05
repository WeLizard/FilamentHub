import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ConfirmEmailChangePage } from './ConfirmEmailChangePage';

const mocks = vi.hoisted(() => ({
  confirmEmailChange: vi.fn(),
  user: { id: 7 } as { id: number } | null,
  refreshUser: vi.fn(),
}));

vi.mock('../api/client', () => ({
  authAPI: { confirmEmailChange: (...args: unknown[]) => mocks.confirmEmailChange(...args) },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: mocks.user, refreshUser: mocks.refreshUser }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

function page() {
  return (
    <MemoryRouter initialEntries={['/confirm-email-change?token=email-token']}>
      <ConfirmEmailChangePage />
    </MemoryRouter>
  );
}

describe('ConfirmEmailChangePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.user = { id: 7 };
    mocks.refreshUser = vi.fn().mockResolvedValue(undefined);
  });

  it('validates the current replacement session after a late admin confirmation', async () => {
    let resolve!: (value: { message: string; session_revoked: boolean; user_id: number | null }) => void;
    mocks.confirmEmailChange.mockReturnValue(new Promise((done) => { resolve = done; }));
    const firstRefresh = mocks.refreshUser;
    const view = render(page());

    const replacementRefresh = vi.fn().mockResolvedValue(undefined);
    mocks.refreshUser = replacementRefresh;
    view.rerender(page());
    resolve({ message: 'changed', session_revoked: true, user_id: 7 });

    await waitFor(() => expect(replacementRefresh).toHaveBeenCalledOnce());
    expect(firstRefresh).not.toHaveBeenCalled();
    expect(await screen.findByText('confirmEmailChange.adminSuccessMessage')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'confirmEmailChange.signInAgain' }))
      .toHaveAttribute('href', '/?auth=login');
  });

  it('keeps the ordinary email confirmation success flow unchanged', async () => {
    mocks.confirmEmailChange.mockResolvedValue({
      message: 'changed',
      session_revoked: false,
      user_id: null,
    });
    render(page());

    expect(await screen.findByText('confirmEmailChange.successMessage')).toBeInTheDocument();
    expect(mocks.refreshUser).not.toHaveBeenCalled();
    expect(screen.getByRole('link', { name: 'confirmEmailChange.goHome' }))
      .toHaveAttribute('href', '/');
  });

  it('does not disturb a different account established before the response arrives', async () => {
    let resolve!: (value: { message: string; session_revoked: boolean; user_id: number | null }) => void;
    mocks.confirmEmailChange.mockReturnValue(new Promise((done) => { resolve = done; }));
    const view = render(page());
    const replacementRefresh = vi.fn().mockResolvedValue(undefined);
    mocks.user = { id: 8 };
    mocks.refreshUser = replacementRefresh;
    view.rerender(page());

    resolve({ message: 'changed', session_revoked: true, user_id: 7 });

    expect(await screen.findByText('confirmEmailChange.successMessage')).toBeInTheDocument();
    expect(replacementRefresh).not.toHaveBeenCalled();
    expect(screen.getByRole('link', { name: 'confirmEmailChange.goHome' }))
      .toHaveAttribute('href', '/');
  });
});
