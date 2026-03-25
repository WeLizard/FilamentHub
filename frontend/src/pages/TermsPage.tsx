/** Страница с пользовательским соглашением */

import { Link } from 'react-router-dom';
import { Trans, useTranslation } from 'react-i18next';
import { ArrowLeft, Package } from 'lucide-react';
import { SEOHead } from '../components/SEOHead';

const TERM_ITEM_KEYS = [
  'authorization',
  'account',
  'authData',
  'content',
  'profile',
  'paidServices',
  'registration',
  'site',
  'service',
  'moderator',
] as const;

export const TermsPage = () => {
  const { t } = useTranslation();
  const prohibitedActions = t('termsPage.sections.content.prohibitedActions', {
    returnObjects: true,
  }) as string[];

  return (
    <>
      <SEOHead
        title={t('termsPage.title')}
        url="/user-agreement"
        type="website"
        allowAI={false}
      />
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      {/* Animated Background */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-purple-500/10 rounded-full blur-3xl animate-pulse"></div>
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-blue-500/10 rounded-full blur-3xl animate-pulse delay-1000"></div>
      </div>

      {/* Content */}
      <div className="relative max-w-4xl mx-auto px-6 py-8 z-10">
        {/* Header */}
        <div className="mb-8">
          <Link
            to="/"
            className="inline-flex items-center space-x-2 text-purple-400 hover:text-purple-300 transition-colors mb-4"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>{t('termsPage.backHome')}</span>
          </Link>
          <div className="flex items-center space-x-4 mb-4">
            <div className="w-12 h-12 bg-gradient-to-r from-purple-500 to-pink-500 rounded-xl flex items-center justify-center shadow-lg shadow-purple-500/25">
              <Package className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-3xl font-bold text-white">{t('termsPage.title')}</h1>
          </div>
          <p className="text-gray-400 text-sm">{t('termsPage.lastUpdated')}</p>
        </div>

        {/* Content */}
        <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-8 border border-white/20 shadow-xl">
          <div className="prose prose-invert max-w-none space-y-6 text-gray-300">
            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('termsPage.sections.subject.title')}</h2>
              <p className="mb-2">{t('termsPage.sections.subject.paragraphs.0')}</p>
              <p className="mb-2">{t('termsPage.sections.subject.paragraphs.1')}</p>
            </section>

            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('termsPage.sections.general.title')}</h2>
              <p className="mb-2">{t('termsPage.sections.general.paragraphs.0')}</p>
              <p className="mb-2">
                <Trans
                  i18nKey="termsPage.sections.general.paragraphs.1"
                  components={{
                    agreementLink: (
                      <Link to="/user-agreement" className="text-purple-400 hover:text-purple-300 underline" />
                    ),
                  }}
                />
              </p>
              <p className="mb-2">{t('termsPage.sections.general.paragraphs.2')}</p>
              <p className="mb-2">{t('termsPage.sections.general.paragraphs.3')}</p>
            </section>

            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('termsPage.sections.terms.title')}</h2>
              <div className="space-y-2">
                {TERM_ITEM_KEYS.map((itemKey) => (
                  <p key={itemKey}>
                    <Trans
                      i18nKey={`termsPage.sections.terms.items.${itemKey}`}
                      components={{ strong: <strong className="text-white" /> }}
                    />
                  </p>
                ))}
              </div>
            </section>

            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('termsPage.sections.registration.title')}</h2>
              <p className="mb-2">{t('termsPage.sections.registration.paragraphs.0')}</p>
              <p className="mb-2">{t('termsPage.sections.registration.paragraphs.1')}</p>
              <p className="mb-2">{t('termsPage.sections.registration.paragraphs.2')}</p>
              <p className="mb-2">{t('termsPage.sections.registration.paragraphs.3')}</p>
              <p className="mb-2">{t('termsPage.sections.registration.paragraphs.4')}</p>
              <p className="mb-2">{t('termsPage.sections.registration.paragraphs.5')}</p>
              <p className="mb-2">{t('termsPage.sections.registration.paragraphs.6')}</p>
              <p className="mb-2">{t('termsPage.sections.registration.paragraphs.7')}</p>
              <p className="mb-2">{t('termsPage.sections.registration.paragraphs.8')}</p>
            </section>

            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('termsPage.sections.userData.title')}</h2>
              <p className="mb-2">{t('termsPage.sections.userData.paragraphs.0')}</p>
              <p className="mb-2">{t('termsPage.sections.userData.paragraphs.1')}</p>
              <p className="mb-2">
                <Trans
                  i18nKey="termsPage.sections.userData.paragraphs.2"
                  components={{
                    consentTextLink: (
                      <Link
                        to="/personal-data-consent"
                        className="text-purple-400 hover:text-purple-300 underline"
                      />
                    ),
                    consentPathLink: (
                      <Link
                        to="/personal-data-consent"
                        className="text-purple-400 hover:text-purple-300 underline"
                      />
                    ),
                  }}
                />
              </p>
            </section>

            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('termsPage.sections.termination.title')}</h2>
              <p className="mb-2">
                <strong className="text-white">{t('termsPage.sections.termination.adminTitle')}</strong>
              </p>
              <p className="mb-2 ml-4">{t('termsPage.sections.termination.adminParagraph')}</p>
              <p className="mb-2">
                <strong className="text-white">{t('termsPage.sections.termination.userTitle')}</strong>
              </p>
              <p className="mb-2 ml-4">{t('termsPage.sections.termination.userParagraphs.0')}</p>
              <p className="mb-2 ml-4">{t('termsPage.sections.termination.userParagraphs.1')}</p>
            </section>

            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('termsPage.sections.content.title')}</h2>
              <p className="mb-2">{t('termsPage.sections.content.paragraphs.0')}</p>
              <p className="mb-2 ml-4">{t('termsPage.sections.content.paragraphs.1')}</p>
              <p className="mb-2 ml-4">{t('termsPage.sections.content.paragraphs.2')}</p>
              <p className="mb-2">{t('termsPage.sections.content.paragraphs.3')}</p>
              <ul className="list-disc list-inside ml-6 mb-2 space-y-1">
                {prohibitedActions.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
              <p className="mb-2">{t('termsPage.sections.content.paragraphs.4')}</p>
            </section>

            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('termsPage.sections.adminRights.title')}</h2>
              <p className="mb-2">{t('termsPage.sections.adminRights.paragraphs.0')}</p>
              <p className="mb-2">{t('termsPage.sections.adminRights.paragraphs.1')}</p>
              <p className="mb-2">{t('termsPage.sections.adminRights.paragraphs.2')}</p>
              <p className="mb-2">{t('termsPage.sections.adminRights.paragraphs.3')}</p>
              <p className="mb-2">{t('termsPage.sections.adminRights.paragraphs.4')}</p>
              <p className="mb-2">{t('termsPage.sections.adminRights.paragraphs.5')}</p>
            </section>

            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('termsPage.sections.liability.title')}</h2>
              <p className="mb-2">{t('termsPage.sections.liability.paragraphs.0')}</p>
              <p className="mb-2">{t('termsPage.sections.liability.paragraphs.1')}</p>
            </section>

            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('termsPage.sections.advertising.title')}</h2>
              <p className="mb-2">{t('termsPage.sections.advertising.paragraphs.0')}</p>
              <p className="mb-2">{t('termsPage.sections.advertising.paragraphs.1')}</p>
              <p className="mb-2">{t('termsPage.sections.advertising.paragraphs.2')}</p>
              <p className="mb-2">{t('termsPage.sections.advertising.paragraphs.3')}</p>
              <p className="mb-2">{t('termsPage.sections.advertising.paragraphs.4')}</p>
            </section>

            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('termsPage.sections.final.title')}</h2>
              <p className="mb-2">{t('termsPage.sections.final.paragraphs.0')}</p>
              <p className="mb-2 ml-4">{t('termsPage.sections.final.paragraphs.1')}</p>
              <p className="mb-2 ml-8">{t('termsPage.sections.final.paragraphs.2')}</p>
              <p className="mb-2 ml-8">{t('termsPage.sections.final.paragraphs.3')}</p>
              <p className="mb-2 ml-4">{t('termsPage.sections.final.paragraphs.4')}</p>
              <p className="mb-2">{t('termsPage.sections.final.paragraphs.5')}</p>
              <p className="mb-2">{t('termsPage.sections.final.paragraphs.6')}</p>
            </section>
          </div>
        </div>
      </div>
    </div>
    </>
  );
};
