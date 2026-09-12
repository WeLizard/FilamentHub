import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider, useInfiniteQuery } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { shouldShowInitialHistoryError } from '../utils/calculatorHistoryQueries';

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => undefined },
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

const entry = (id: number) => ({
  id,
  title: `Estimate ${id}`,
  created_at: '2026-09-12T12:00:00Z',
  total_cost: id,
  quantity: 1,
  source: 'manual',
}) as never;

describe('Calculator history feed', () => {
  it('keeps loaded pages and classifies a next-page failure separately', async () => {
    const queryPage = vi.fn(async ({ pageParam }: { pageParam: string | null }) => {
      if (pageParam === 'page-2') throw new Error('second page unavailable');
      return { items: [entry(1)], total: 2, next_cursor: 'page-2' };
    });
    const Harness = () => {
      const query = useInfiniteQuery({
        queryKey: ['history-query-state-test'],
        queryFn: ({ pageParam }) => queryPage({ pageParam }),
        initialPageParam: null as string | null,
        getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
        retry: false,
      });
      const count = query.data?.pages.flatMap((page) => page.items).length ?? 0;
      return (
        <>
          <span>count:{count}</span>
          {shouldShowInitialHistoryError(query.error, query.data?.pages) ? <span>initial-error</span> : null}
          {query.isFetchNextPageError ? <span>next-page-error</span> : null}
          <button type="button" onClick={() => void query.fetchNextPage()}>next</button>
        </>
      );
    };
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><Harness /></QueryClientProvider>);

    expect(await screen.findByText('count:1')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'next' }));
    expect(await screen.findByText('next-page-error')).toBeInTheDocument();
    expect(screen.getByText('count:1')).toBeInTheDocument();
    expect(screen.queryByText('initial-error')).not.toBeInTheDocument();
    await waitFor(() => expect(queryPage).toHaveBeenCalledTimes(2));
  });

  it('exposes a retry action when the first compact page fails', async () => {
    const { HistoryView } = await import('../pages/CalculatorPage');
    const onRetryLoad = vi.fn();
    render(
      <HistoryView
        entries={[]}
        historyLoadError="History unavailable"
        historyLoadMoreError={null}
        isDeletingHistory={false}
        restoringEntryId={null}
        failedRestoreEntryId={null}
        isLoading={false}
        isLoadingMore={false}
        hasMore={false}
        total={0}
        onRetryLoad={onRetryLoad}
        onLoadMore={vi.fn()}
        onDeleteEntry={vi.fn()}
        onRestoreEntry={vi.fn()}
        formatCurrency={(value) => String(value)}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'common.retry' }));
    expect(onRetryLoad).toHaveBeenCalledTimes(1);
  });

  it('renders appended entries and exposes a retryable next-page error', async () => {
    const { HistoryView } = await import('../pages/CalculatorPage');
    const onLoadMore = vi.fn();
    render(
      <HistoryView
        entries={[entry(2), entry(1)]}
        historyLoadError={null}
        historyLoadMoreError="Next page failed"
        isDeletingHistory={false}
        restoringEntryId={null}
        failedRestoreEntryId={null}
        isLoading={false}
        isLoadingMore={false}
        hasMore
        total={3}
        onRetryLoad={vi.fn()}
        onLoadMore={onLoadMore}
        onDeleteEntry={vi.fn()}
        onRestoreEntry={vi.fn()}
        formatCurrency={(value) => String(value)}
      />,
    );

    expect(screen.getByText('Estimate 2')).toBeInTheDocument();
    expect(screen.getByText('Estimate 1')).toBeInTheDocument();
    expect(screen.getByText('Next page failed')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'profilePage.calculator.historyLoadMore' }));
    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });

  it('removes the load-more action at the terminal cursor', async () => {
    const { HistoryView } = await import('../pages/CalculatorPage');
    render(
      <HistoryView
        entries={[entry(1)]}
        historyLoadError={null}
        historyLoadMoreError={null}
        isDeletingHistory={false}
        restoringEntryId={null}
        failedRestoreEntryId={null}
        isLoading={false}
        isLoadingMore={false}
        hasMore={false}
        total={1}
        onRetryLoad={vi.fn()}
        onLoadMore={vi.fn()}
        onDeleteEntry={vi.fn()}
        onRestoreEntry={vi.fn()}
        formatCurrency={(value) => String(value)}
      />,
    );

    expect(screen.queryByRole('button', { name: 'profilePage.calculator.historyLoadMore' })).not.toBeInTheDocument();
  });

  it('shows hydration progress and exposes retry on the failed entry', async () => {
    const { HistoryView } = await import('../pages/CalculatorPage');
    const onRestoreEntry = vi.fn();
    const { rerender } = render(
      <HistoryView
        entries={[entry(1)]}
        historyLoadError={null}
        historyLoadMoreError={null}
        isDeletingHistory={false}
        restoringEntryId={1}
        failedRestoreEntryId={null}
        isLoading={false}
        isLoadingMore={false}
        hasMore={false}
        total={1}
        onRetryLoad={vi.fn()}
        onLoadMore={vi.fn()}
        onDeleteEntry={vi.fn()}
        onRestoreEntry={onRestoreEntry}
        formatCurrency={(value) => String(value)}
      />,
    );
    expect(screen.getByRole('button', { name: 'profilePage.calculator.restoreHistoryEntry' })).toBeDisabled();

    rerender(
      <HistoryView
        entries={[entry(1)]}
        historyLoadError={null}
        historyLoadMoreError={null}
        isDeletingHistory={false}
        restoringEntryId={null}
        failedRestoreEntryId={1}
        isLoading={false}
        isLoadingMore={false}
        hasMore={false}
        total={1}
        onRetryLoad={vi.fn()}
        onLoadMore={vi.fn()}
        onDeleteEntry={vi.fn()}
        onRestoreEntry={onRestoreEntry}
        formatCurrency={(value) => String(value)}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'common.retry' }));
    expect(onRestoreEntry).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }));
  });
});
