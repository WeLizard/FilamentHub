import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AdminConfirmationDialog } from './AdminConfirmationDialog';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

const challenge = {
  challenge_id: 'challenge-1',
  expires_at: '2026-09-05T20:10:00Z',
  masked_email: 'a***@example.com',
};

function renderDialog(overrides: Partial<React.ComponentProps<typeof AdminConfirmationDialog>> = {}) {
  const props: React.ComponentProps<typeof AdminConfirmationDialog> = {
    isOpen: true,
    challengeKey: 'block_user:7',
    title: 'Block user',
    message: 'Block user seven?',
    confirmText: 'Block',
    requestChallenge: vi.fn().mockResolvedValue(challenge),
    onConfirm: vi.fn().mockResolvedValue(undefined),
    onClose: vi.fn(),
    ...overrides,
  };
  return { ...render(<AdminConfirmationDialog {...props} />), props };
}

describe('AdminConfirmationDialog', () => {
  beforeEach(() => vi.clearAllMocks());

  it('requires a six-digit code and forwards the challenge proof', async () => {
    const { props } = renderDialog();

    fireEvent.click(screen.getByRole('button', { name: 'adminConfirmation.sendCode' }));
    const input = await screen.findByRole('textbox', { name: /adminConfirmation\.codeLabel/ });
    const confirm = screen.getByRole('button', { name: 'Block' });
    expect(confirm).toBeDisabled();

    fireEvent.change(input, { target: { value: '12a34567' } });
    expect(input).toHaveValue('123456');
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);

    await waitFor(() => expect(props.onConfirm).toHaveBeenCalledWith({
      challenge_id: 'challenge-1',
      code: '123456',
    }));
  });

  it('keeps the challenge and editable code after a rejected proof', async () => {
    const onConfirm = vi.fn().mockRejectedValue({
      response: { data: { detail: { code: 'ERR_ADMIN_CONFIRMATION_INVALID' } } },
    });
    renderDialog({ onConfirm });

    fireEvent.click(screen.getByRole('button', { name: 'adminConfirmation.sendCode' }));
    const input = await screen.findByRole('textbox', { name: /adminConfirmation\.codeLabel/ });
    fireEvent.change(input, { target: { value: '111111' } });
    fireEvent.click(screen.getByRole('button', { name: 'Block' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('adminConfirmation.errorFallback');
    expect(input).toHaveValue('111111');
    fireEvent.change(input, { target: { value: '222222' } });
    expect(input).toHaveValue('222222');
  });

  it('discards a local challenge when the protected target changes', async () => {
    const { rerender, props } = renderDialog();
    fireEvent.click(screen.getByRole('button', { name: 'adminConfirmation.sendCode' }));
    expect(await screen.findByRole('textbox', { name: /adminConfirmation\.codeLabel/ })).toBeInTheDocument();

    rerender(<AdminConfirmationDialog {...props} challengeKey="block_user:8" />);

    expect(screen.queryByRole('textbox', { name: /adminConfirmation\.codeLabel/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'adminConfirmation.sendCode' })).toBeInTheDocument();
  });

  it('discards the old proof when delivery of a replacement code fails', async () => {
    const requestChallenge = vi.fn()
      .mockResolvedValueOnce(challenge)
      .mockRejectedValueOnce({ response: { status: 503 } })
      .mockResolvedValueOnce({ ...challenge, challenge_id: 'challenge-2' });
    renderDialog({ requestChallenge });
    fireEvent.click(screen.getByRole('button', { name: 'adminConfirmation.sendCode' }));
    const input = await screen.findByRole('textbox', { name: /adminConfirmation\.codeLabel/ });
    fireEvent.change(input, { target: { value: '123456' } });

    fireEvent.click(screen.getByRole('button', { name: 'adminConfirmation.resend' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('adminConfirmation.errorFallback');
    expect(screen.queryByRole('textbox', { name: /adminConfirmation\.codeLabel/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'adminConfirmation.sendCode' }));
    expect(await screen.findByRole('textbox', { name: /adminConfirmation\.codeLabel/ })).toHaveValue('');
  });
});
