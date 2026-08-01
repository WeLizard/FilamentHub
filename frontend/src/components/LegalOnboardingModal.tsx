import { useEffect, useState } from 'react';
import { Check, Loader2, LogOut, ShieldCheck, Trash2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { authAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import type { LegalRequirements } from '../types/api';
import { translateApiError } from '../utils/translateApiError';
import { DeleteAccountModal } from './DeleteAccountModal';
import { ModalOverlay } from './ModalOverlay';

export function LegalOnboardingModal() {
  const { t, i18n } = useTranslation();
  const { acceptLegalDocuments, logout, user } = useAuth();
  const [requirements, setRequirements] = useState<LegalRequirements | null>(null);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [personalDataConsent, setPersonalDataConsent] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDelete, setShowDelete] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void authAPI.getLegalRequirements(user?.legal_document_pack)
      .then((value) => {
        if (!cancelled) {
          setRequirements(value);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(t('legalOnboarding.loadError'));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [t, user?.legal_document_pack]);

  const isReacceptance = Boolean(user?.legal_previously_accepted);
  const effectiveDate = requirements
    ? new Intl.DateTimeFormat(i18n.resolvedLanguage || i18n.language, {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      }).format(new Date(`${requirements.legal_update_effective_date}T00:00:00`))
    : '';

  const handleAccept = async () => {
    if (!requirements || !termsAccepted || !personalDataConsent) {
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      await acceptLegalDocuments({
        terms_accepted: true,
        personal_data_consent: true,
        terms_version: requirements.terms_version,
        personal_data_consent_version: requirements.personal_data_consent_version,
        privacy_policy_version: requirements.privacy_policy_version,
        legal_language: (i18n.resolvedLanguage || i18n.language || 'en').slice(0, 2).toLowerCase(),
        legal_pack: requirements.legal_pack,
      });
    } catch (err: any) {
      setError(
        translateApiError(
          t,
          err?.response?.data?.detail,
          t('legalOnboarding.submitError'),
        ),
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <ModalOverlay
      onClose={() => undefined}
      closeOnOverlayClick={false}
      closeOnEscape={false}
      className="!bg-slate-950/85"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="legal-onboarding-title"
        className="w-full max-w-lg rounded-2xl border border-white/15 bg-slate-900/95 p-6 shadow-2xl shadow-purple-950/40 backdrop-blur-xl sm:p-8"
      >
        <div className="mb-6 flex items-start gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-purple-500/15 text-purple-300">
            <ShieldCheck className="h-6 w-6" />
          </div>
          <div>
            <h2 id="legal-onboarding-title" className="text-xl font-semibold text-white">
              {t('legalOnboarding.title')}
            </h2>
            <p className="mt-1 text-sm leading-6 text-slate-300">
              {t('legalOnboarding.description')}
            </p>
          </div>
        </div>

        {isReacceptance && requirements && (
          <div className="mb-4 rounded-xl border border-purple-400/25 bg-purple-500/10 px-4 py-3 text-sm leading-6 text-purple-100">
            <p>{t('legalOnboarding.updated', { date: effectiveDate })}</p>
            <p className="text-slate-300">{t('legalOnboarding.noReregistration')}</p>
            {requirements.legal_update_note && (
              <p className="mt-1 text-slate-300">{requirements.legal_update_note}</p>
            )}
          </div>
        )}

        {error && (
          <div className="mb-4 rounded-xl border border-red-400/25 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {error}
          </div>
        )}

        <div className="space-y-3">
          <div className="flex w-full items-start gap-3 rounded-xl border border-white/10 bg-white/5 p-4">
            <button
              type="button"
              role="checkbox"
              aria-label={t('legalOnboarding.acceptTerms')}
              aria-checked={termsAccepted}
              onClick={() => setTermsAccepted((value) => !value)}
              className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded ${termsAccepted ? 'bg-purple-600 text-white' : 'border border-white/25 text-transparent'}`}
            >
              <Check className="h-4 w-4" />
            </button>
            <span className="text-sm leading-6 text-slate-200">
              {t('legalOnboarding.acceptTerms')}{' '}
              <Link
                to={requirements?.terms_url || '/user-agreement'}
                target="_blank"
                rel="noopener noreferrer"
                className="text-purple-300 underline hover:text-purple-200"
              >
                {t('authModal.agree_terms_user_agreement')}
              </Link>
            </span>
          </div>

          <div className="flex w-full items-start gap-3 rounded-xl border border-white/10 bg-white/5 p-4">
            <button
              type="button"
              role="checkbox"
              aria-label={t('legalOnboarding.acceptPersonalData')}
              aria-checked={personalDataConsent}
              onClick={() => setPersonalDataConsent((value) => !value)}
              className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded ${personalDataConsent ? 'bg-purple-600 text-white' : 'border border-white/25 text-transparent'}`}
            >
              <Check className="h-4 w-4" />
            </button>
            <span className="text-sm leading-6 text-slate-200">
              {t('legalOnboarding.acceptPersonalData')}{' '}
              <Link
                to={requirements?.personal_data_consent_url || '/personal-data-consent'}
                target="_blank"
                rel="noopener noreferrer"
                className="text-purple-300 underline hover:text-purple-200"
              >
                {t('authModal.agree_terms_personal_data')}
              </Link>
            </span>
          </div>
        </div>

        <p className="mt-4 text-xs leading-5 text-slate-400">
          {t('legalOnboarding.privacyNote')}{' '}
          <Link
            to={requirements?.privacy_policy_url || '/privacy-policy'}
            target="_blank"
            rel="noopener noreferrer"
            className="text-purple-300 underline hover:text-purple-200"
          >
            {t('layout.footer_privacy')}
          </Link>
        </p>

        <p className="mt-4 text-xs leading-5 text-slate-400">
          {t('legalOnboarding.declineNote')}
        </p>

        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <button
              type="button"
              onClick={() => void logout()}
              disabled={isSubmitting}
              className="inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm text-slate-300 transition-colors hover:bg-white/5 hover:text-white disabled:opacity-50"
            >
              <LogOut className="h-4 w-4" />
              {t('legalOnboarding.logout')}
            </button>
            <button
              type="button"
              onClick={() => setShowDelete(true)}
              disabled={isSubmitting}
              className="inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm text-red-300/90 transition-colors hover:bg-red-500/10 hover:text-red-200 disabled:opacity-50"
            >
              <Trash2 className="h-4 w-4" />
              {t('legalOnboarding.deleteAccount')}
            </button>
          </div>
          <button
            type="button"
            onClick={() => void handleAccept()}
            disabled={!requirements || !termsAccepted || !personalDataConsent || isSubmitting}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 px-6 py-2.5 text-sm font-medium text-white shadow-lg shadow-purple-600/20 transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {t('legalOnboarding.continue')}
          </button>
        </div>
      </div>
      <DeleteAccountModal isOpen={showDelete} onClose={() => setShowDelete(false)} />
    </ModalOverlay>
  );
}
