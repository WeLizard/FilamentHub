import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import i18next from 'i18next';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import en from '../locales/en/translation.json';
import type { Notification } from '../types/api';

const i18n = vi.hoisted(() => ({ instance: null as null | typeof import('i18next').default }));
const mocks = vi.hoisted(() => ({ listFeed: vi.fn() }));

i18n.instance = i18next.createInstance();
void i18n.instance.init({ lng: 'en', resources: { en: { translation: en } }, initImmediate: false });

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: i18n.instance!.t.bind(i18n.instance), i18n: i18n.instance }),
}));
vi.mock('../api/client', () => ({
  notificationsAPI: { listFeed: (...args: unknown[]) => mocks.listFeed(...args) },
}));
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 7 }, refreshUser: vi.fn() }),
}));

import { Notifications } from './Notifications';

const lowStock = (id: number, type: Notification['type'], extra: Record<string, unknown>): Notification => ({
  id,
  user_id: 7,
  type,
  title: type,
  message: `${type}_message`,
  link: '/profile?tab=spools',
  extra_data: extra,
  read: true,
  read_at: null,
  created_at: '2026-10-29T10:00:00Z',
});

describe('Low-stock notifications', () => {
  it('render translated texts with the alert values', async () => {
    mocks.listFeed.mockResolvedValue({
      items: [
        lowStock(2, 'low_stock_spool', { spool_id: 5, name: 'Galaxy PLA', remaining_g: 80, threshold_g: 100 }),
        lowStock(1, 'low_stock_material', { material_key: 'f:12', name: 'PLA Matte', shelf_g: 450, threshold_g: 500, unknown_count: 2 }),
      ],
      next_cursor: null,
      unread_count: 0,
    });
    render(
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <Notifications />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: en.notifications.title }));
    expect(await screen.findByText('Spool running low')).toBeInTheDocument();
    expect(screen.getByText('Spool "Galaxy PLA" is running low: 80 g left (alert at 100 g).')).toBeInTheDocument();
    expect(screen.getByText('Material running low')).toBeInTheDocument();
    expect(screen.getByText(
      '"PLA Matte" in storage: 450 g left (alert at 500 g). 2 spools of unknown size are not counted.',
    )).toBeInTheDocument();
  });
});
