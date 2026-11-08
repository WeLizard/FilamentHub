import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { User } from '../types/api';
import { WorkshopInterestCard } from './WorkshopInterestCard';

const mocks = vi.hoisted(() => ({
  join: vi.fn(),
  leave: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('../api/client', () => ({
  subscriptionAPI: {
    joinWorkshopInterest: mocks.join,
    leaveWorkshopInterest: mocks.leave,
  },
}));
vi.mock('../utils/translateApiError', () => ({
  translateApiError: (_t: unknown, _detail: unknown, fallback?: string) => fallback ?? 'error',
}));

const interestedSubscription = {
  status: 'interested',
  trial_ends_at: null,
  current_period_end: null,
  cancel_at_period_end: false,
  is_comp: false,
  interested_at: '2026-10-31T10:00:00Z',
};

function renderCard(
  subscription: User['subscription'] = null,
  overrides: Partial<User> = {},
) {
  const onUserUpdate = vi.fn();
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <WorkshopInterestCard
        user={{ id: 1, subscription, ...overrides } as User}
        onUserUpdate={onUserUpdate}
      />
    </QueryClientProvider>,
  );
  return { onUserUpdate };
}

describe('WorkshopInterestCard', () => {
  beforeEach(() => {
    mocks.join.mockReset().mockResolvedValue({
      status: 'interested',
      interested_at: '2026-10-31T10:00:00Z',
    });
    mocks.leave.mockReset().mockResolvedValue(undefined);
  });

  it('records interest and refreshes the account', async () => {
    const { onUserUpdate } = renderCard();

    fireEvent.click(
      screen.getByRole('button', { name: 'settings.workshopInterest.join' }),
    );

    await waitFor(() => expect(mocks.join).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onUserUpdate).toHaveBeenCalledTimes(1));
    expect(
      screen.getByText('settings.workshopInterest.success'),
    ).toBeInTheDocument();
  });

  it('shows the joined state and can leave the list', async () => {
    const { onUserUpdate } = renderCard(
      interestedSubscription as User['subscription'],
    );

    expect(
      screen.getByText('settings.workshopInterest.joinedAt'),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', { name: 'settings.workshopInterest.leave' }),
    );

    await waitFor(() => expect(mocks.leave).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onUserUpdate).toHaveBeenCalledTimes(1));
  });

  it('does not offer the waitlist when access already exists', () => {
    renderCard({
      ...interestedSubscription,
      status: 'active',
      interested_at: null,
    } as User['subscription']);

    expect(
      screen.queryByRole('button', { name: 'settings.workshopInterest.join' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText('settings.workshopInterest.alreadyActive'),
    ).toBeInTheDocument();
  });

  it('offers the waitlist after a lapsed trial', () => {
    renderCard({
      ...interestedSubscription,
      status: 'trialing',
      interested_at: null,
      trial_ends_at: '2020-01-01T00:00:00Z',
    } as User['subscription']);

    expect(
      screen.getByRole('button', { name: 'settings.workshopInterest.join' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('settings.workshopInterest.alreadyActive'),
    ).not.toBeInTheDocument();
  });

  it('offers the waitlist after a lapsed paid period', () => {
    renderCard({
      ...interestedSubscription,
      status: 'active',
      interested_at: null,
      trial_ends_at: null,
      current_period_end: '2020-01-01T00:00:00Z',
    } as User['subscription']);

    expect(
      screen.getByRole('button', { name: 'settings.workshopInterest.join' }),
    ).toBeInTheDocument();
  });

  it('does not offer the waitlist to an administrator', () => {
    renderCard(null, { role: 'admin' });

    expect(
      screen.queryByRole('button', { name: 'settings.workshopInterest.join' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText('settings.workshopInterest.adminNote'),
    ).toBeInTheDocument();
  });

  it('shows an error when the request fails', async () => {
    mocks.join.mockRejectedValue({
      response: { data: { detail: 'ERR_PLAN_INTEREST_UNAVAILABLE' } },
    });
    renderCard();

    fireEvent.click(
      screen.getByRole('button', { name: 'settings.workshopInterest.join' }),
    );

    await waitFor(() =>
      expect(
        screen.getByText('settings.workshopInterest.error'),
      ).toBeInTheDocument(),
    );
  });
});
