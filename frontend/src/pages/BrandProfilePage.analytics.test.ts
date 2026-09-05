import { cleanup, render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { BrandMonthlyRegisteredSpools } from '../types/api';
import {
  formatBrandAnalyticsMonth,
  getMonthlyRegisteredSpoolsValue,
  MonthlyRegisteredSpoolsCard,
} from './BrandProfilePage';

const translations: Record<string, string> = {
  'brandProfile.monthlyRegisteredSpools': 'Новые катушки в учёте — {{month}}',
  'brandProfile.monthlyRegisteredSpoolsInsufficient': 'Not enough data',
  'brandProfile.monthlyRegisteredSpoolsUnavailableScope': 'Unavailable for this territory',
  'brandProfile.monthlyRegisteredSpoolsHint': 'Snapshot of spools still registered when the report was captured.',
  'brandProfile.monthlyRegisteredSpoolsCapturedHint': 'Still registered as of {{capturedAt}} UTC.',
};

const translate = (key: string, options?: Record<string, unknown>) => {
  let value = translations[key] ?? key;
  for (const [name, replacement] of Object.entries(options ?? {})) {
    value = value.replace(`{{${name}}}`, String(replacement));
  }
  return value;
};

vi.mock('react-i18next', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-i18next')>()),
  useTranslation: () => ({
    t: translate,
    i18n: { language: 'ru' },
  }),
}));

afterEach(cleanup);

const metric = (
  status: BrandMonthlyRegisteredSpools['status'],
  value: number | null,
): BrandMonthlyRegisteredSpools => ({
  month: '2026-08',
  status,
  value,
  captured_at: status === 'available' ? '2026-09-01T00:00:00Z' : null,
});

describe('brand monthly registered spools presentation', () => {
  it('formats the completed UTC month and an available physical-spool count', () => {
    expect(formatBrandAnalyticsMonth('2026-08', 'en')).toBe('August 2026');
    expect(getMonthlyRegisteredSpoolsValue(metric('available', 1250), 'en', translate)).toBe('1,250');
  });

  it.each([
    ['insufficient_cohort', 'Not enough data'],
    ['unavailable_scope', 'Unavailable for this territory'],
  ] as const)('shows the %s privacy status without turning null into zero', (status, expected) => {
    const value = getMonthlyRegisteredSpoolsValue(metric(status, null), 'en', translate);
    expect(value).toBe(expected);
    expect(value).not.toBe('0');
  });

  it('renders an available count with its localized month and capture-time semantics', () => {
    render(createElement(MonthlyRegisteredSpoolsCard, { metric: metric('available', 1250) }));

    expect(screen.getByText(/Новые катушки в учёте — август 2026/i)).toBeInTheDocument();
    expect(screen.getByText((content) => content.replace(/\s/g, ' ') === '1 250')).toBeInTheDocument();
    expect(screen.getByText(/Still registered as of .* UTC\./)).toBeInTheDocument();
  });

  it.each([
    ['insufficient_cohort', 'Not enough data'],
    ['unavailable_scope', 'Unavailable for this territory'],
  ] as const)('renders the %s status readably and hides any supplied count', (status, expected) => {
    render(createElement(MonthlyRegisteredSpoolsCard, { metric: metric(status, 987) }));

    const statusText = screen.getByText(expected);
    expect(statusText).toHaveClass('text-sm', 'md:text-base');
    expect(statusText).not.toHaveClass('md:text-3xl');
    expect(screen.queryByText('987')).not.toBeInTheDocument();
    expect(screen.queryByText('0')).not.toBeInTheDocument();
    expect(screen.getByText(/Новые катушки в учёте — август 2026/i)).toBeInTheDocument();
  });
});
