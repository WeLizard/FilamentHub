import { Component, type ErrorInfo, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { clientErrorsAPI } from '../api/client';

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

let reported = false;

// The reader sees only the recovery screen; the cause must reach someone who
// can fix it. One report per page load: a failing page fails the same way again.
function reportRenderError(error: Error, info: ErrorInfo): void {
  if (reported) return;
  reported = true;
  const entry = document.querySelector<HTMLScriptElement>('script[type="module"][src*="/assets/"]');
  void clientErrorsAPI.report({
    message: String(error?.message ?? error).slice(0, 500),
    stack: String(error?.stack ?? '').slice(0, 4000),
    component_stack: String(info.componentStack ?? '').slice(0, 2000),
    // Without the query: it can carry one-time codes.
    path: window.location.pathname.slice(0, 300),
    build: (entry?.src.split('/').pop() ?? 'dev').slice(0, 80),
  }).catch(() => undefined);
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Unhandled React render error', error, info.componentStack);
    reportRenderError(error, info);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return <ErrorFallback homeHref={this.props.homeHref ?? '/'} />;
    }

    return this.props.children;
  }
}
