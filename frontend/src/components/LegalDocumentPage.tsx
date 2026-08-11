import type { LucideIcon } from 'lucide-react';
import { ArrowLeft, Loader2, RefreshCw } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import { Link, useSearchParams } from 'react-router-dom';
import remarkGfm from 'remark-gfm';
import { useTranslation } from 'react-i18next';

import { authAPI } from '../api/client';
import type { LegalDocumentType, LegalPack } from '../types/api';
import { normalizeSiteLocale } from '../utils/siteLocale';
import { PageBackground } from './PageBackground';
import { SEOHead } from './SEOHead';

interface LegalDocumentPageProps {
  documentType: LegalDocumentType;
  route: string;
  fallbackTitleKey: string;
  icon: LucideIcon;
  iconClassName: string;
}

function normalizePack(value: string | null): LegalPack | null {
  return value === 'ru' || value === 'eu' || value === 'intl' ? value : null;
}

export function LegalDocumentPage({
  documentType,
  route,
  fallbackTitleKey,
  icon: Icon,
  iconClassName,
}: LegalDocumentPageProps) {
  const { t, i18n } = useTranslation();
  const [searchParams] = useSearchParams();
  const language = normalizeSiteLocale(i18n.resolvedLanguage || i18n.language) ?? 'en';
  const pack = normalizePack(searchParams.get('pack'));
  const edition = searchParams.get('edition');

  const documentQuery = useQuery({
    queryKey: ['legal-document', documentType, language, pack, edition],
    queryFn: () => authAPI.getLegalDocument(documentType, language, { pack, edition }),
    staleTime: edition ? Number.POSITIVE_INFINITY : 60_000,
    retry: 1,
  });

  const title = documentQuery.data?.title || t(fallbackTitleKey);
  const pinnedLegalHref = (href: string): string => {
    if (!documentQuery.data || !['/user-agreement', '/personal-data-consent', '/privacy-policy'].includes(href)) {
      return href;
    }
    const query = new URLSearchParams({
      pack: documentQuery.data.legal_pack,
      edition: documentQuery.data.edition_id,
    });
    return `${href}?${query.toString()}`;
  };

  return (
    <>
      <SEOHead title={title} url={route} type="website" allowAI={false} />
      <PageBackground ambient>

        <main className="relative z-10 mx-auto max-w-4xl px-4 py-8 sm:px-6">
          <Link
            to="/"
            className="mb-4 inline-flex items-center gap-2 text-purple-400 transition-colors hover:text-purple-300"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>{t('legalDocument.backHome')}</span>
          </Link>

          <header className="mb-8">
            <div className="mb-4 flex items-center gap-4">
              <div className={`flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-r shadow-lg ${iconClassName}`}>
                <Icon className="h-6 w-6 text-white" />
              </div>
              <h1 className="text-3xl font-bold text-white">{title}</h1>
            </div>
            {documentQuery.data?.revision_label && (
              <p className="text-sm text-gray-400">{documentQuery.data.revision_label}</p>
            )}
          </header>

          <div className="rounded-2xl border border-white/20 bg-white/10 p-5 shadow-xl backdrop-blur-sm sm:p-8">
            {documentQuery.isLoading && (
              <div className="flex min-h-48 items-center justify-center gap-3 text-slate-300">
                <Loader2 className="h-5 w-5 animate-spin" />
                <span>{t('legalDocument.loading')}</span>
              </div>
            )}

            {documentQuery.isError && (
              <div className="flex min-h-48 flex-col items-center justify-center gap-4 text-center">
                <p className="text-slate-200">{t('legalDocument.loadError')}</p>
                <button
                  type="button"
                  onClick={() => void documentQuery.refetch()}
                  className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-sm text-white transition-colors hover:bg-white/10"
                >
                  <RefreshCw className="h-4 w-4" />
                  {t('legalDocument.retry')}
                </button>
              </div>
            )}

            {documentQuery.data && (
              <article className="max-w-none text-[15px] leading-7 text-gray-300 sm:text-base">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    h2: ({ children }) => (
                      <h2 className="mb-4 mt-8 text-2xl font-bold text-white first:mt-0">{children}</h2>
                    ),
                    h3: ({ children }) => (
                      <h3 className="mb-3 mt-6 text-xl font-semibold text-white">{children}</h3>
                    ),
                    p: ({ children }) => <p className="mb-3">{children}</p>,
                    ul: ({ children }) => (
                      <ul className="mb-4 ml-6 list-disc space-y-1">{children}</ul>
                    ),
                    ol: ({ children }) => (
                      <ol className="mb-4 ml-6 list-decimal space-y-1">{children}</ol>
                    ),
                    li: ({ children }) => <li className="pl-1">{children}</li>,
                    strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
                    a: ({ href, children }) => {
                      const className = 'text-purple-300 underline decoration-purple-400/60 underline-offset-2 hover:text-purple-200';
                      return href?.startsWith('/') ? (
                        <Link to={pinnedLegalHref(href)} className={className}>{children}</Link>
                      ) : (
                        <a href={href} target="_blank" rel="noopener noreferrer" className={className}>{children}</a>
                      );
                    },
                    blockquote: ({ children }) => (
                      <blockquote className="my-4 border-l-2 border-purple-400/60 pl-4 text-slate-300">{children}</blockquote>
                    ),
                    hr: () => <hr className="my-7 border-white/15" />,
                    table: ({ children }) => (
                      <div className="my-5 overflow-x-auto">
                        <table className="w-full border-collapse text-left text-sm">{children}</table>
                      </div>
                    ),
                    th: ({ children }) => <th className="border border-white/15 bg-white/5 px-3 py-2 text-white">{children}</th>,
                    td: ({ children }) => <td className="border border-white/15 px-3 py-2 align-top">{children}</td>,
                  }}
                >
                  {documentQuery.data.markdown}
                </ReactMarkdown>
              </article>
            )}
          </div>
        </main>
      </PageBackground>
    </>
  );
}
