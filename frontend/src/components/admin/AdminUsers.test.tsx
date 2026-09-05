import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AdminUsers } from './AdminUsers';

const mocks = vi.hoisted(() => ({
  listUsers: vi.fn(),
  createReauthChallenge: vi.fn(),
  deactivateUser: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));

vi.mock('../../api/client', () => ({
  adminAPI: {
    listUsers: (...args: unknown[]) => mocks.listUsers(...args),
    createReauthChallenge: (...args: unknown[]) => mocks.createReauthChallenge(...args),
    deactivateUser: (...args: unknown[]) => mocks.deactivateUser(...args),
    activateUser: vi.fn(),
    previewUserDeletion: vi.fn(),
    deleteUserAccount: vi.fn(),
    setUserProAccess: vi.fn(),
    promoteToAdmin: vi.fn(),
    demoteToUser: vi.fn(),
    linkUserToBrand: vi.fn(),
    unlinkUserFromBrand: vi.fn(),
    getUserAchievements: vi.fn(),
    grantUserAchievement: vi.fn(),
    revokeUserAchievement: vi.fn(),
  },
  brandsAPI: { list: vi.fn().mockResolvedValue({ items: [] }) },
}));

vi.mock('../AdminConfirmationDialog', () => ({
  AdminConfirmationDialog: (props: {
    isOpen: boolean;
    challengeKey: string;
    requestChallenge: () => Promise<unknown>;
    onConfirm: (proof: { challenge_id: string; code: string }) => Promise<unknown>;
  }) => props.isOpen ? (
    <button
      type="button"
      onClick={async () => {
        await props.requestChallenge();
        await props.onConfirm({ challenge_id: 'challenge-1', code: '123456' });
      }}
    >
      {`challenge:${props.challengeKey}`}
    </button>
  ) : null,
}));

vi.mock('../Toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

describe('AdminUsers protected actions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.listUsers.mockResolvedValue({
      items: [{
        id: 42,
        email: 'member@example.com',
        username: 'member',
        role: 'user',
        full_name: null,
        avatar_url: null,
        active: true,
        email_verified: true,
        brand_id: null,
        active_organization_id: null,
        brand_name: null,
        printer_id: null,
        recommend_physical_printer_id: null,
        recommend_printer_profile_id: null,
        oauth_provider: null,
        has_password: true,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        last_login: null,
        legal_onboarding_required: false,
      }],
      total: 1,
      page: 1,
      size: 20,
      total_pages: 1,
    });
    mocks.createReauthChallenge.mockResolvedValue({
      challenge_id: 'challenge-1',
      expires_at: '2026-09-05T20:10:00Z',
      masked_email: 'a***@example.com',
    });
    mocks.deactivateUser.mockResolvedValue({ id: 42, username: 'member' });
  });

  it('binds blocking to the selected user and forwards the entered proof', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <AdminUsers />
      </QueryClientProvider>,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'adminUsers.deactivateTitle' }));
    expect(mocks.deactivateUser).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'challenge:block_user:42' }));

    await waitFor(() => expect(mocks.createReauthChallenge).toHaveBeenCalledWith({
      action: 'block_user',
      target_user_id: 42,
    }));
    expect(mocks.deactivateUser).toHaveBeenCalledWith(42, {
      challenge_id: 'challenge-1',
      code: '123456',
    });
  });
});
