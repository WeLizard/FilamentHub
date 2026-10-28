import { render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CrmWorkspacePage } from '../pages/CrmWorkspacePage';

const mocks = vi.hoisted(() => ({
  getQuote: vi.fn(),
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { currency: 'RUB' } }),
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));
vi.mock('../hooks/useUserCurrency', () => ({ useUserCurrency: () => ({ currency: 'RUB' }) }));
vi.mock('../api/client', () => {
  const empty = () => Promise.resolve({ items: [], total: 0, page: 1, size: 20 });
  const crmAPI = new Proxy({} as Record<string, unknown>, {
    get: (_target, name) => (name === 'getQuote' ? mocks.getQuote : empty),
  });
  return { crmAPI, spoolsAPI: new Proxy({}, { get: () => empty }) };
});

function renderAt(url: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}><CrmWorkspacePage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CRM workspace ?quote= link', () => {
  beforeEach(() => {
    mocks.getQuote.mockReset();
    mocks.getQuote.mockReturnValue(new Promise(() => undefined));
  });

  it('opens the quote named in the link', async () => {
    renderAt('/workspace?quote=42');
    await waitFor(() => expect(mocks.getQuote).toHaveBeenCalledWith(42));
    expect(mocks.getQuote).toHaveBeenCalledTimes(1);
  });

  it.each(['0', '-3', 'abc', '1.5', '', '12abc', '99999999999'])('ignores the invalid value %j', async (value) => {
    renderAt(`/workspace?quote=${value}`);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(mocks.getQuote).not.toHaveBeenCalled();
  });
});
