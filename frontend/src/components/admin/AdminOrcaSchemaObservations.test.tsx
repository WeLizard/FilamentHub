import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AdminOrcaSchemaObservations } from './AdminOrcaSchemaObservations';

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  update: vi.fn(),
  writeText: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

vi.mock('../../api/client', () => ({
  adminAPI: {
    listOrcaSchemaObservations: (...args: unknown[]) => mocks.list(...args),
    updateOrcaSchemaObservation: (...args: unknown[]) => mocks.update(...args),
  },
}));

vi.mock('../Toast', () => ({
  toast: {
    success: (...args: unknown[]) => mocks.toastSuccess(...args),
    error: (...args: unknown[]) => mocks.toastError(...args),
  },
}));

const observation = {
  id: 17,
  scope: 'process',
  field_name: 'future_orca_field',
  value_shape: 'array:string',
  status: 'new',
  occurrences: 3,
  registry_version: 'bundle-sha256:test-registry',
  first_source: 'orcaslicer_sync',
  last_source: 'orcaslicer_sync',
  first_seen_at: '2026-08-01T10:00:00Z',
  last_seen_at: '2026-08-02T10:00:00Z',
  reviewed_at: null,
  reviewed_by_user_id: null,
};

function renderObservations() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AdminOrcaSchemaObservations />
    </QueryClientProvider>,
  );
}

describe('AdminOrcaSchemaObservations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.list.mockResolvedValue({
      items: [observation],
      total: 1,
      new_count: 1,
      page: 1,
      size: 25,
      pages: 1,
      registry_version: observation.registry_version,
    });
    mocks.update.mockResolvedValue({ ...observation, status: 'reviewed' });
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: mocks.writeText },
    });
    mocks.writeText.mockResolvedValue(undefined);
  });

  it('copies bounded field metadata without a preset value', async () => {
    renderObservations();

    fireEvent.click(await screen.findByRole('button', { name: 'adminOrcaSchema.copyData' }));

    await waitFor(() => expect(mocks.writeText).toHaveBeenCalledOnce());
    const copied = JSON.parse(mocks.writeText.mock.calls[0][0]);
    expect(copied).toEqual({
      field_name: observation.field_name,
      preset_scope: observation.scope,
      value_shape: observation.value_shape,
      occurrences: observation.occurrences,
      first_seen_at: observation.first_seen_at,
      last_seen_at: observation.last_seen_at,
      first_source: observation.first_source,
      last_source: observation.last_source,
      registry_version: observation.registry_version,
    });
    expect(mocks.toastSuccess).toHaveBeenCalledWith('adminOrcaSchema.copied');
  });

  it('marks a new field as reviewed without offering an ignore action', async () => {
    renderObservations();

    fireEvent.click(await screen.findByRole('button', { name: 'adminOrcaSchema.markReviewed' }));

    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith(17, 'reviewed'));
    expect(screen.queryByText('adminOrcaSchema.ignore')).toBeNull();
    expect(screen.queryByText('adminOrcaSchema.acknowledge')).toBeNull();
  });
});
