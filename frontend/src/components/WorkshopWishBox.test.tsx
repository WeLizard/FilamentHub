import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { WorkshopWishBox } from './WorkshopWishBox';

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('../api/client', () => ({
  feedbackAPI: { create: mocks.create },
}));
vi.mock('../utils/translateApiError', () => ({
  translateApiError: (_t: unknown, _detail: unknown, fallback?: string) => fallback ?? 'error',
}));

function renderWishBox() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <WorkshopWishBox />
    </QueryClientProvider>,
  );
}

describe('WorkshopWishBox', () => {
  beforeEach(() => {
    mocks.create.mockReset().mockResolvedValue({ id: 1 });
  });

  it('sends a feature feedback with the workshop source', async () => {
    renderWishBox();
    const textarea = screen.getByRole('textbox', {
      name: 'settings.workshopWish.label',
    });
    const submit = screen.getByRole('button', {
      name: 'settings.workshopWish.submit',
    });
    expect(submit).toBeDisabled();

    fireEvent.change(textarea, { target: { value: 'Хочу фирменные КП' } });
    expect(submit).toBeEnabled();
    fireEvent.click(submit);

    await waitFor(() =>
      expect(mocks.create).toHaveBeenCalledWith({
        type: 'feature',
        subject: 'settings.workshopWish.subject',
        message: 'Хочу фирменные КП',
        source: 'profile_workshop_tab',
      }),
    );
    expect(
      await screen.findByText('settings.workshopWish.success'),
    ).toBeInTheDocument();
    expect(textarea).toHaveValue('');
  });

  it('keeps edits made while a wish is being sent', async () => {
    let finishSending: (wish: { id: number }) => void = () => {};
    mocks.create.mockReturnValue(new Promise<{ id: number }>((resolve) => {
      finishSending = resolve;
    }));
    renderWishBox();
    const textarea = screen.getByRole('textbox', { name: 'settings.workshopWish.label' });
    fireEvent.change(textarea, { target: { value: 'Хочу API' } });
    fireEvent.click(screen.getByRole('button', { name: 'settings.workshopWish.submit' }));
    expect(await screen.findByRole('button', { name: 'settings.workshopWish.sending' })).toBeDisabled();

    fireEvent.change(textarea, { target: { value: 'Хочу отчёты' } });
    finishSending({ id: 1 });

    expect(await screen.findByText('settings.workshopWish.success')).toBeInTheDocument();
    expect(textarea).toHaveValue('Хочу отчёты');
  });

  it('does not send an empty wish', () => {
    renderWishBox();
    const submit = screen.getByRole('button', {
      name: 'settings.workshopWish.submit',
    });

    fireEvent.click(submit);

    expect(mocks.create).not.toHaveBeenCalled();
  });

  it('shows an error when sending fails', async () => {
    mocks.create.mockRejectedValue({
      response: { data: { detail: 'ERR_REQUEST_NOT_PENDING' } },
    });
    renderWishBox();
    fireEvent.change(
      screen.getByRole('textbox', { name: 'settings.workshopWish.label' }),
      { target: { value: 'Хочу API' } },
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'settings.workshopWish.submit' }),
    );

    expect(
      await screen.findByText('settings.workshopWish.error'),
    ).toBeInTheDocument();
  });
});
