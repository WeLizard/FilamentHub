import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

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
  result_data: { cost_final: id, cost_total: id, quantity: 1 },
  request_data: {},
  parsed_jobs: [],
}) as never;

describe('Calculator history feed', () => {
  it('renders appended entries and exposes a retryable next-page error', async () => {
    const { HistoryView } = await import('../pages/CalculatorPage');
    const onLoadMore = vi.fn();
    render(
      <HistoryView
        entries={[entry(2), entry(1)]}
        historyLoadError={null}
        historyLoadMoreError="Next page failed"
        isDeletingHistory={false}
        isLoading={false}
        isLoadingMore={false}
        hasMore
        total={3}
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
        isLoading={false}
        isLoadingMore={false}
        hasMore={false}
        total={1}
        onLoadMore={vi.fn()}
        onDeleteEntry={vi.fn()}
        onRestoreEntry={vi.fn()}
        formatCurrency={(value) => String(value)}
      />,
    );

    expect(screen.queryByRole('button', { name: 'profilePage.calculator.historyLoadMore' })).not.toBeInTheDocument();
  });
});
