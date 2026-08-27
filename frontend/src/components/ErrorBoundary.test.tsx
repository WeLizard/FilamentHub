import { lazy, Suspense } from 'react';
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ErrorBoundary } from './ErrorBoundary';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

function BrokenChild(): never {
  throw new Error('render failed');
}

describe('ErrorBoundary', () => {
  let consoleError: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => {
    consoleError.mockRestore();
  });

  it('leaves a successful render unchanged', () => {
    render(
      <ErrorBoundary>
        <p>healthy child</p>
      </ErrorBoundary>,
    );

    expect(screen.getByText('healthy child')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows the localized recovery screen when a child render fails', () => {
    render(
      <ErrorBoundary homeHref="/ru/">
        <BrokenChild />
      </ErrorBoundary>,
    );

    expect(screen.getByRole('heading', { name: 'errorBoundary.title' })).toBeInTheDocument();
    expect(screen.getByText('errorBoundary.defaultMessage')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'errorBoundary.goHome' })).toHaveAttribute(
      'href',
      '/ru/',
    );
    expect(consoleError).toHaveBeenCalled();
  });

  it('catches a rejected lazy import', async () => {
    const BrokenLazyChild = lazy(() => Promise.reject(new Error('chunk failed')));

    render(
      <ErrorBoundary>
        <Suspense fallback={<p>loading</p>}>
          <BrokenLazyChild />
        </Suspense>
      </ErrorBoundary>,
    );

    expect(
      await screen.findByRole('heading', { name: 'errorBoundary.title' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('loading')).not.toBeInTheDocument();
  });
});
