import type { ReactNode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  acceptLegalDocuments: vi.fn(),
  getLegalRequirements: vi.fn(),
  logout: vi.fn(),
  user: {
    legal_document_pack: 'intl',
    legal_onboarding_required: true,
    legal_previously_accepted: true,
    required_legal_acceptances: ['terms'] as Array<'terms' | 'personal_data_consent'>,
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', resolvedLanguage: 'en' },
  }),
}));

vi.mock('react-router-dom', () => ({
  Link: ({ children, to, ...props }: { children: ReactNode; to: string }) => (
    <a href={to} {...props}>{children}</a>
  ),
}));

vi.mock('../api/client', () => ({
  authAPI: { getLegalRequirements: mocks.getLegalRequirements },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    acceptLegalDocuments: mocks.acceptLegalDocuments,
    logout: mocks.logout,
    user: mocks.user,
  }),
}));

vi.mock('./DeleteAccountModal', () => ({
  DeleteAccountModal: () => null,
}));

const requirements = {
  legal_pack: 'intl',
  edition_id: 'global-2026-08-01',
  terms_version: 'terms-v2',
  personal_data_consent_version: 'consent-v1',
  privacy_policy_version: 'privacy-v1',
  terms_url: '/user-agreement?pack=intl&edition=global-2026-08-01',
  personal_data_consent_url: '/personal-data-consent?pack=intl&edition=global-2026-08-01',
  privacy_policy_url: '/privacy-policy?pack=intl&edition=global-2026-08-01',
  legal_update_effective_date: '2026-08-01',
  legal_update_note: '',
};

describe('LegalOnboardingModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.user.required_legal_acceptances = ['terms'];
    mocks.getLegalRequirements.mockResolvedValue(requirements);
    mocks.acceptLegalDocuments.mockResolvedValue({});
  });

  it('asks only for the changed mandatory document', async () => {
    const { LegalOnboardingModal } = await import('./LegalOnboardingModal');
    render(<LegalOnboardingModal />);

    const termsCheckbox = await screen.findByRole('checkbox', {
      name: 'legalOnboarding.acceptTerms',
    });
    expect(
      screen.queryByRole('checkbox', { name: 'legalOnboarding.acceptPersonalData' }),
    ).not.toBeInTheDocument();

    const continueButton = screen.getByRole('button', {
      name: 'legalOnboarding.continue',
    });
    expect(continueButton).toBeDisabled();

    fireEvent.click(termsCheckbox);
    fireEvent.click(continueButton);

    await waitFor(() => expect(mocks.acceptLegalDocuments).toHaveBeenCalledTimes(1));
    expect(mocks.acceptLegalDocuments).toHaveBeenCalledWith(
      expect.objectContaining({
        terms_accepted: true,
        terms_version: 'terms-v2',
      }),
    );
    expect(mocks.acceptLegalDocuments.mock.calls[0][0]).not.toHaveProperty(
      'personal_data_consent',
    );
  });

  it('can request only renewed personal-data consent', async () => {
    mocks.user.required_legal_acceptances = ['personal_data_consent'];
    const { LegalOnboardingModal } = await import('./LegalOnboardingModal');
    render(<LegalOnboardingModal />);

    const consentCheckbox = await screen.findByRole('checkbox', {
      name: 'legalOnboarding.acceptPersonalData',
    });
    expect(
      screen.queryByRole('checkbox', { name: 'legalOnboarding.acceptTerms' }),
    ).not.toBeInTheDocument();

    fireEvent.click(consentCheckbox);
    fireEvent.click(
      screen.getByRole('button', { name: 'legalOnboarding.continue' }),
    );

    await waitFor(() => expect(mocks.acceptLegalDocuments).toHaveBeenCalledTimes(1));
    expect(mocks.acceptLegalDocuments).toHaveBeenCalledWith(
      expect.objectContaining({ personal_data_consent: true }),
    );
    expect(mocks.acceptLegalDocuments.mock.calls[0][0]).not.toHaveProperty(
      'terms_accepted',
    );
  });
});
