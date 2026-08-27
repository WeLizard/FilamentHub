import { Component, type ErrorInfo, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

interface ErrorBoundaryProps {
  children: ReactNode;
  homeHref?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

function ErrorFallback({ homeHref }: { homeHref: string }) {
  const { t } = useTranslation();

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-4 text-white">
      <section
        role="alert"
        className="w-full max-w-lg rounded-2xl border border-white/10 bg-white/5 p-8 text-center shadow-2xl shadow-black/40"
      >
        <h1 className="text-2xl font-semibold">{t('errorBoundary.title')}</h1>
        <p className="mt-3 text-sm leading-6 text-slate-300">
          {t('errorBoundary.defaultMessage')}
        </p>
        <a
          href={homeHref}
          className="mt-6 inline-flex rounded-lg bg-purple-600 px-5 py-2.5 font-medium transition-colors hover:bg-purple-500 focus:outline-none focus:ring-2 focus:ring-purple-300"
        >
          {t('errorBoundary.goHome')}
        </a>
      </section>
    </main>
  );
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Unhandled React render error', error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return <ErrorFallback homeHref={this.props.homeHref ?? '/'} />;
    }

    return this.props.children;
  }
}
