/** Страница с согласием на обработку персональных данных */

import { Link } from 'react-router-dom';
import { Trans, useTranslation } from 'react-i18next';
import { ArrowLeft, Shield } from 'lucide-react';

export const ConsentPage = () => {
  const { t } = useTranslation();
  const brandVerificationItems = t('consentPage.sections.general.brandVerificationItems', {
    returnObjects: true,
  }) as string[];
  const purposeItems = t('consentPage.sections.purpose.items', {
    returnObjects: true,
  }) as string[];
  const actionItems = t('consentPage.sections.actions.items', {
    returnObjects: true,
  }) as string[];
  const revocationItems = t('consentPage.sections.revocation.items', {
    returnObjects: true,
  }) as string[];
  const cookieItems = t('consentPage.sections.cookies.items', {
    returnObjects: true,
  }) as string[];
  const rightsItems = t('consentPage.sections.rights.items', {
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
            <span>{t('consentPage.backHome')}</span>
          </Link>
          <div className="flex items-center space-x-4 mb-4">
            <div className="w-12 h-12 bg-gradient-to-r from-green-500 to-emerald-500 rounded-xl flex items-center justify-center shadow-lg shadow-green-500/25">
              <Shield className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-3xl font-bold text-white">{t('consentPage.title')}</h1>
          </div>
          <p className="text-gray-400 text-sm">{t('consentPage.lastUpdated')}</p>
        </div>

        {/* Content */}
        <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-8 border border-white/20 shadow-xl">
          <div className="prose prose-invert max-w-none space-y-6 text-gray-300">
            <section>
              <p className="mb-4">{t('consentPage.intro')}</p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">{t('consentPage.sections.general.title')}</h2>
              <p className="mb-2">{t('consentPage.sections.general.paragraphs.0')}</p>
              <p className="mb-2">{t('consentPage.sections.general.paragraphs.1')}</p>
              <ul className="list-disc list-inside ml-4 mb-4 space-y-1">
                <li>{t('consentPage.sections.general.personalData.email')}</li>
                <li>{t('consentPage.sections.general.personalData.nickname')}</li>
                <li>{t('consentPage.sections.general.personalData.fullName')}</li>
                <li>{t('consentPage.sections.general.personalData.profileData')}</li>
                <li>
                  {t('consentPage.sections.general.personalData.brandVerificationIntro')}
                  <ul className="list-disc list-inside ml-6 mt-1 space-y-1">
                    {brandVerificationItems.map((item, index) => (
                      <li key={index}>{item}</li>
                    ))}
                  </ul>
                  {' '}
                  {t('consentPage.sections.general.personalData.brandVerificationNote')}
                </li>
                <li>{t('consentPage.sections.general.personalData.technicalData')}</li>
                <li>{t('consentPage.sections.general.personalData.syncSettings')}</li>
              </ul>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">{t('consentPage.sections.purpose.title')}</h2>
              <p className="mb-2">
                <Trans
                  i18nKey="consentPage.sections.purpose.paragraph"
                  components={{
                    agreementTextLink: (
                      <Link to="/user-agreement" className="text-purple-400 hover:text-purple-300 underline" />
                    ),
                    agreementPathLink: (
                      <Link to="/user-agreement" className="text-purple-400 hover:text-purple-300 underline" />
                    ),
                  }}
                />
              </p>
              <ul className="list-disc list-inside ml-4 mb-4 space-y-1">
                {purposeItems.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">{t('consentPage.sections.actions.title')}</h2>
              <p className="mb-2">{t('consentPage.sections.actions.paragraph')}</p>
              <ul className="list-disc list-inside ml-4 mb-4 space-y-1">
                {actionItems.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">{t('consentPage.sections.term.title')}</h2>
              <p className="mb-2">{t('consentPage.sections.term.paragraphs.0')}</p>
              <p className="mb-2">{t('consentPage.sections.term.paragraphs.1')}</p>
              <p className="mb-2">{t('consentPage.sections.term.paragraphs.2')}</p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">{t('consentPage.sections.revocation.title')}</h2>
              <p className="mb-2">{t('consentPage.sections.revocation.paragraphs.0')}</p>
              <p className="mb-2">{t('consentPage.sections.revocation.paragraphs.1')}</p>
              <ul className="list-disc list-inside ml-4 mb-4 space-y-1">
                {revocationItems.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
              <p className="mb-2">{t('consentPage.sections.revocation.paragraphs.2')}</p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">{t('consentPage.sections.protection.title')}</h2>
              <p className="mb-2">{t('consentPage.sections.protection.paragraphs.0')}</p>
              <p className="mb-2">{t('consentPage.sections.protection.paragraphs.1')}</p>
              <p className="mb-2">{t('consentPage.sections.protection.paragraphs.2')}</p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">{t('consentPage.sections.cookies.title')}</h2>
              <p className="mb-2">{t('consentPage.sections.cookies.paragraphs.0')}</p>
              <p className="mb-2">{t('consentPage.sections.cookies.paragraphs.1')}</p>
              <ul className="list-disc list-inside ml-4 mb-4 space-y-1">
                {cookieItems.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
              <p className="mb-2">{t('consentPage.sections.cookies.paragraphs.2')}</p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">{t('consentPage.sections.rights.title')}</h2>
              <p className="mb-2">{t('consentPage.sections.rights.paragraph')}</p>
              <ul className="list-disc list-inside ml-4 mb-4 space-y-1">
                {rightsItems.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">{t('consentPage.sections.contacts.title')}</h2>
              <p className="mb-2">{t('consentPage.sections.contacts.paragraphs.0')}</p>
              <p className="mb-2">
                <Trans
                  i18nKey="consentPage.sections.contacts.paragraphs.1"
                  components={{
                    agreementTextLink: (
                      <Link to="/user-agreement" className="text-purple-400 hover:text-purple-300 underline" />
                    ),
                    agreementPathLink: (
                      <Link to="/user-agreement" className="text-purple-400 hover:text-purple-300 underline" />
                    ),
                  }}
                />
              </p>
            </section>

            <section className="mt-8 pt-6 border-t border-white/20">
              <p className="text-sm text-gray-400">{t('consentPage.confirmation')}</p>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
};
