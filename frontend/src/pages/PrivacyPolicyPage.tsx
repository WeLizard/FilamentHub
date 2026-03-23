/** Privacy Policy page */

import { Link } from 'react-router-dom';
import { Trans, useTranslation } from 'react-i18next';
import { ArrowLeft, Lock } from 'lucide-react';

export const PrivacyPolicyPage = () => {
  const { t } = useTranslation();
  const dataCategories = t('privacyPage.sections.dataCollected.categories', {
    returnObjects: true,
  }) as string[];
  const purposeItems = t('privacyPage.sections.purposes.items', {
    returnObjects: true,
  }) as string[];
  const thirdPartyServices = t('privacyPage.sections.thirdParty.services', {
    returnObjects: true,
  }) as string[];
  const userRights = t('privacyPage.sections.rights.items', {
    returnObjects: true,
  }) as string[];

  return (
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
            <span>{t('privacyPage.backHome')}</span>
          </Link>
          <div className="flex items-center space-x-4 mb-4">
            <div className="w-12 h-12 bg-gradient-to-r from-blue-500 to-cyan-500 rounded-xl flex items-center justify-center shadow-lg shadow-blue-500/25">
              <Lock className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-3xl font-bold text-white">{t('privacyPage.title')}</h1>
          </div>
          <p className="text-gray-400 text-sm">{t('privacyPage.lastUpdated')}</p>
        </div>

        {/* Content */}
        <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-8 border border-white/20 shadow-xl">
          <div className="prose prose-invert max-w-none space-y-6 text-gray-300">
            {/* 1. General */}
            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('privacyPage.sections.general.title')}</h2>
              {(t('privacyPage.sections.general.paragraphs', { returnObjects: true }) as string[]).map((p, i) => (
                <p key={i} className="mb-2">{p}</p>
              ))}
            </section>

            {/* 2. Data Collected */}
            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('privacyPage.sections.dataCollected.title')}</h2>
              <p className="mb-2">{t('privacyPage.sections.dataCollected.intro')}</p>
              <ul className="list-disc list-inside ml-4 mb-4 space-y-1">
                {dataCategories.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
              <p className="mb-2">{t('privacyPage.sections.dataCollected.oauth')}</p>
            </section>

            {/* 3. Purposes */}
            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('privacyPage.sections.purposes.title')}</h2>
              <p className="mb-2">{t('privacyPage.sections.purposes.intro')}</p>
              <ul className="list-disc list-inside ml-4 mb-4 space-y-1">
                {purposeItems.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
              <p className="mb-2 font-medium text-purple-300">{t('privacyPage.sections.purposes.note')}</p>
            </section>

            {/* 4. Third-Party Services */}
            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('privacyPage.sections.thirdParty.title')}</h2>
              <p className="mb-2">{t('privacyPage.sections.thirdParty.intro')}</p>
              <ul className="list-disc list-inside ml-4 mb-4 space-y-2">
                {thirdPartyServices.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
              <p className="mb-2">{t('privacyPage.sections.thirdParty.note')}</p>
            </section>

            {/* 5. Cross-Border Transfer */}
            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('privacyPage.sections.crossBorder.title')}</h2>
              {(t('privacyPage.sections.crossBorder.paragraphs', { returnObjects: true }) as string[]).map((p, i) => (
                <p key={i} className="mb-2">{p}</p>
              ))}
            </section>

            {/* 6. Retention */}
            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('privacyPage.sections.retention.title')}</h2>
              {(t('privacyPage.sections.retention.paragraphs', { returnObjects: true }) as string[]).map((p, i) => (
                <p key={i} className="mb-2">{p}</p>
              ))}
            </section>

            {/* 7. Security */}
            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('privacyPage.sections.security.title')}</h2>
              {(t('privacyPage.sections.security.paragraphs', { returnObjects: true }) as string[]).map((p, i) => (
                <p key={i} className="mb-2">{p}</p>
              ))}
            </section>

            {/* 8. User Rights */}
            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('privacyPage.sections.rights.title')}</h2>
              <p className="mb-2">{t('privacyPage.sections.rights.intro')}</p>
              <ul className="list-disc list-inside ml-4 mb-4 space-y-1">
                {userRights.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
              <p className="mb-2">{t('privacyPage.sections.rights.note')}</p>
            </section>

            {/* 9. Cookies */}
            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('privacyPage.sections.cookies.title')}</h2>
              {(t('privacyPage.sections.cookies.paragraphs', { returnObjects: true }) as string[]).map((p, i) => (
                <p key={i} className="mb-2">{p}</p>
              ))}
            </section>

            {/* 10. Children */}
            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('privacyPage.sections.children.title')}</h2>
              {(t('privacyPage.sections.children.paragraphs', { returnObjects: true }) as string[]).map((p, i) => (
                <p key={i} className="mb-2">{p}</p>
              ))}
            </section>

            {/* 11. Changes */}
            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('privacyPage.sections.changes.title')}</h2>
              <p className="mb-2">
                <Trans
                  i18nKey="privacyPage.sections.changes.paragraphs.0"
                  components={{
                    privacyLink: (
                      <Link to="/privacy-policy" className="text-purple-400 hover:text-purple-300 underline" />
                    ),
                  }}
                />
              </p>
              <p className="mb-2">{t('privacyPage.sections.changes.paragraphs.1')}</p>
            </section>

            {/* 12. Contacts */}
            <section>
              <h2 className="text-2xl font-bold text-white mb-4">{t('privacyPage.sections.contacts.title')}</h2>
              <p className="mb-2">{t('privacyPage.sections.contacts.paragraphs.0')}</p>
              <p className="mb-2">
                <Trans
                  i18nKey="privacyPage.sections.contacts.paragraphs.1"
                  components={{
                    termsLink: (
                      <Link to="/user-agreement" className="text-purple-400 hover:text-purple-300 underline" />
                    ),
                    consentLink: (
                      <Link to="/personal-data-consent" className="text-purple-400 hover:text-purple-300 underline" />
                    ),
                  }}
                />
              </p>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
};
