import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  sample_value: { value: ['actual value'] },
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

function makeObservation(id: number) {
  return { ...observation, id, field_name: `future_orca_field_${id}` };
}

type TestObservation = Omit<typeof observation, 'sample_value'> & {
  sample_value: { value: unknown } | null;
};

function listResponse(items: TestObservation[] = [observation], page = 1, size = 25, total = items.length) {
  return {
    items,
    total,
    new_count: total,
    page,
    size,
    pages: Math.ceil(total / size),
    registry_version: observation.registry_version,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

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

async function clickCopyList() {
  const button = screen.getByRole('button', { name: 'adminOrcaSchema.copyList' });
  await waitFor(() => expect(button).toBeEnabled());
  await act(async () => { fireEvent.click(button); });
}

describe('AdminOrcaSchemaObservations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.list.mockResolvedValue(listResponse());
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: mocks.writeText },
    });
    mocks.writeText.mockResolvedValue(undefined);
  });

  it('copies every matching page with filters and the latest JSON sample', async () => {
    const records = Array.from({ length: 101 }, (_, index) => makeObservation(index + 1));
    mocks.list.mockImplementation(async ({ page, size, status, scope, search }) => {
      expect(status).toBe('reviewed');
      expect(scope).toBe('process');
      expect(search).toBe('future');
      return listResponse(records.slice((page - 1) * size, page * size), page, size, records.length);
    });
    renderObservations();

    fireEvent.change(await screen.findByRole('combobox', { name: 'adminOrcaSchema.scopeFilter' }), { target: { value: 'process' } });
    fireEvent.change(screen.getByRole('combobox', { name: 'adminOrcaSchema.statusFilter' }), { target: { value: 'reviewed' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'adminOrcaSchema.search' }), { target: { value: ' future ' } });
    await clickCopyList();

    await waitFor(() => expect(mocks.writeText).toHaveBeenCalledOnce());
    const copied = JSON.parse(mocks.writeText.mock.calls[0][0]);
    expect(copied).toEqual({
      filters: { status: 'reviewed', scope: 'process', search: 'future' },
      bundle_registry_version: observation.registry_version,
      count: 101,
      observations: records.map((item) => ({
        field_name: item.field_name,
        scope: item.scope,
        value_shape: item.value_shape,
        sample_value: item.sample_value,
        status: item.status,
        occurrences: item.occurrences,
        first_source: item.first_source,
        last_source: item.last_source,
        first_seen_at: item.first_seen_at,
        last_seen_at: item.last_seen_at,
        registry_version: item.registry_version,
      })),
    });
    expect(mocks.list.mock.calls.filter(([params]) => params.size === 100).map(([params]) => params.page)).toEqual([1, 2]);
    expect(mocks.toastSuccess).toHaveBeenCalledWith('adminOrcaSchema.listCopied');
    expect(mocks.update).not.toHaveBeenCalled();
    expect(JSON.stringify(copied)).not.toContain('reviewed_by_user_id');
    expect(JSON.stringify(copied)).not.toContain('"id"');
    expect(screen.queryByRole('button', { name: 'adminOrcaSchema.copyData' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'adminOrcaSchema.markReviewed' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'adminOrcaSchema.reopen' })).not.toBeInTheDocument();
  });

  it('distinguishes a captured JSON null from an unavailable legacy sample', async () => {
    const captured = { ...makeObservation(1), sample_value: { value: null } };
    const legacy = { ...makeObservation(2), sample_value: null };
    mocks.list.mockImplementation(async ({ page, size }) => (
      listResponse([captured, legacy], page, size, 2)
    ));
    renderObservations();

    await clickCopyList();

    await waitFor(() => expect(mocks.writeText).toHaveBeenCalledOnce());
    const copied = JSON.parse(mocks.writeText.mock.calls[0][0]);
    expect(copied.observations.map((item: { sample_value: unknown }) => item.sample_value)).toEqual([
      { value: null }, null,
    ]);
  });

  it('does not copy or claim success after a later page fails', async () => {
    const records = Array.from({ length: 101 }, (_, index) => makeObservation(index + 1));
    mocks.list.mockImplementation(async ({ page, size }) => {
      if (size === 25) return listResponse(records.slice(0, 25), 1, 25, records.length);
      if (page === 2) throw new Error('network');
      return listResponse(records.slice(0, 100), 1, 100, records.length);
    });
    renderObservations();

    await clickCopyList();

    expect(await screen.findByRole('alert')).toHaveTextContent('adminOrcaSchema.copyListLoadError');
    expect(mocks.writeText).not.toHaveBeenCalled();
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
    expect(mocks.update).not.toHaveBeenCalled();
  });

  it('rejects a duplicate across pages without copying a partial list', async () => {
    const records = Array.from({ length: 101 }, (_, index) => makeObservation(index + 1));
    mocks.list.mockImplementation(async ({ page, size }) => {
      if (size === 25) return listResponse(records.slice(0, 25), 1, 25, records.length);
      return page === 1
        ? listResponse(records.slice(0, 100), 1, 100, records.length)
        : listResponse([records[0]], 2, 100, records.length);
    });
    renderObservations();
    await clickCopyList();
    expect(await screen.findByRole('alert')).toHaveTextContent('adminOrcaSchema.copyListChanged');
    expect(mocks.writeText).not.toHaveBeenCalled();
  });

  it('rejects a changed total across pages', async () => {
    const records = Array.from({ length: 101 }, (_, index) => makeObservation(index + 1));
    mocks.list.mockImplementation(async ({ page, size }) => {
      if (size === 25) return listResponse(records.slice(0, 25), 1, 25, records.length);
      return page === 1
        ? listResponse(records.slice(0, 100), 1, 100, records.length)
        : listResponse([records[100]], 2, 100, records.length + 1);
    });
    renderObservations();
    await clickCopyList();
    expect(await screen.findByRole('alert')).toHaveTextContent('adminOrcaSchema.copyListChanged');
    expect(mocks.writeText).not.toHaveBeenCalled();
  });

  it('abandons the old copy when filters change during loading', async () => {
    const pending = deferred<ReturnType<typeof listResponse>>();
    mocks.list.mockImplementation(({ size }) => size === 100 ? pending.promise : Promise.resolve(listResponse()));
    renderObservations();
    await clickCopyList();
    await waitFor(() => expect(mocks.list.mock.calls.some(([params]) => params.size === 100)).toBe(true));
    fireEvent.change(screen.getByRole('combobox', { name: 'adminOrcaSchema.scopeFilter' }), { target: { value: 'filament' } });
    await act(async () => { pending.resolve(listResponse([observation], 1, 100)); });

    await waitFor(() => expect(screen.getByRole('button', { name: 'adminOrcaSchema.copyList' })).toBeEnabled());
    expect(mocks.writeText).not.toHaveBeenCalled();
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
    expect(mocks.update).not.toHaveBeenCalled();
  });

  it('offers complete read-only text for manual copy when clipboard rejects', async () => {
    mocks.list.mockImplementation(({ size }) => Promise.resolve(listResponse([observation], 1, size)));
    mocks.writeText.mockRejectedValue(new Error('denied'));
    renderObservations();
    await clickCopyList();

    const textarea = await screen.findByRole('textbox', { name: 'adminOrcaSchema.manualCopyTitle' });
    expect(textarea).toHaveAttribute('readonly');
    expect(JSON.parse((textarea as HTMLTextAreaElement).value).count).toBe(1);
    expect(screen.getByText('adminOrcaSchema.manualCopyHint')).toBeInTheDocument();
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
    expect(mocks.update).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'adminOrcaSchema.close' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('offers manual copy when clipboard is unavailable', async () => {
    mocks.list.mockImplementation(({ size }) => Promise.resolve(listResponse([observation], 1, size)));
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
    renderObservations();
    await clickCopyList();
    expect(await screen.findByRole('textbox', { name: 'adminOrcaSchema.manualCopyTitle' })).toHaveAttribute('readonly');
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
    expect(mocks.update).not.toHaveBeenCalled();
  });

  it('labels pagination and disables copy when a refresh fails with stale data', async () => {
    mocks.list.mockResolvedValueOnce(listResponse([observation], 1, 25, 26));
    mocks.list.mockRejectedValueOnce(new Error('network'));
    renderObservations();

    const copyButton = screen.getByRole('button', { name: 'adminOrcaSchema.copyList' });
    await waitFor(() => expect(copyButton).toBeEnabled());
    expect(screen.getByRole('button', { name: 'adminOrcaSchema.previousPage' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'adminOrcaSchema.nextPage' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'adminOrcaSchema.refresh' }));

    await waitFor(() => expect(screen.getByText('adminOrcaSchema.loadError')).toBeInTheDocument());
    expect(copyButton).toBeDisabled();
    fireEvent.click(copyButton);
    expect(mocks.writeText).not.toHaveBeenCalled();
    expect(mocks.update).not.toHaveBeenCalled();
  });
});
