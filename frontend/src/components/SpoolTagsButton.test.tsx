import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { UserSpool } from '../api/client';
import { fakeEdgeKit } from '../tests/fakeEdgeKit';
import { SpoolTagsButton } from './SpoolTagsButton';

const tagApi = vi.hoisted(() => ({
  list: vi.fn(),
  link: vi.fn(),
  unlink: vi.fn(),
  identify: vi.fn(),
}));
const qrApi = vi.hoisted(() => ({ issue: vi.fn() }));
const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
const station = vi.hoisted(() => ({ kit: null as null | ReturnType<typeof import('../tests/fakeEdgeKit').fakeEdgeKit> }));

vi.mock('../api/client', () => ({ spoolTagsAPI: tagApi, spoolQrAPI: qrApi }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('./Toast', () => ({ toast: toastMock }));
vi.mock('../utils/edgeTagStation', async (importOriginal) => {
  const original = await importOriginal<typeof import('../utils/edgeTagStation')>();
  return {
    ...original,
    // The browser's port dialog, answered with the fake kit.
    connectEdgeTagStation: () => original.EdgeTagStation.connect(station.kit!.open),
  };
});
vi.mock('./ModalOverlay', () => ({
  ModalOverlay: ({ children }: { children: ReactNode }) => (
    <div role="dialog">{children}</div>
  ),
}));

const CODE = 'FHQ1_04_UExBLTE_U_abcdefghijklmnopqrstuv';
const UID = '04112233445566';

const spool: Pick<UserSpool, 'id' | 'filament'> = {
  id: 41,
  filament: null,
};

function renderButton() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SpoolTagsButton spool={spool} />
    </QueryClientProvider>,
  );
}

function resetMocks() {
  tagApi.list.mockReset().mockResolvedValue([]);
  tagApi.link.mockReset().mockResolvedValue({
    id: 1,
    spool_id: spool.id,
    uid: '04A1B2C3',
    technology: 'unknown',
    format: null,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
  });
  tagApi.unlink.mockReset().mockResolvedValue(undefined);
  tagApi.identify.mockReset().mockImplementation(async ({ uid }: { uid: string }) => ({ uid, status: 'unlinked', spool_id: null }));
  qrApi.issue.mockReset().mockResolvedValue({
    spool_id: 41,
    short_code: CODE,
    target_url: `https://filamenthub.ru/qr/${CODE}`,
  });
  Object.values(toastMock).forEach((mock) => mock.mockReset());
}

describe('spool physical tags', () => {
  beforeEach(resetMocks);

  it('links a scanned UID to the FilamentHub spool without provider fields', async () => {
    renderButton();
    fireEvent.click(screen.getByRole('button', { name: 'spoolTags.action' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('spoolTags.uid'), {
      target: { value: '04:a1-b2:c3' },
    });
    fireEvent.submit(screen.getByRole('button', { name: 'spoolTags.link' }).closest('form')!);

    await waitFor(() => expect(tagApi.link).toHaveBeenCalledWith(41, {
      uid: '04:a1-b2:c3',
      technology: 'unknown',
      format: null,
    }));
  });

  it('lists and unlinks the canonical binding', async () => {
    tagApi.list.mockResolvedValue([{
      id: 9,
      spool_id: 41,
      uid: 'DEADBEEF',
      technology: 'uhf_rfid',
      format: 'epc-gen2',
      created_at: '2026-09-01T00:00:00Z',
      updated_at: '2026-09-01T00:00:00Z',
    }]);
    renderButton();
    fireEvent.click(screen.getByRole('button', { name: 'spoolTags.action' }));

    expect(await screen.findByText('DEADBEEF')).toBeInTheDocument();
    expect(screen.getByText('spoolTags.technologyLabel.uhf_rfid · epc-gen2')).toBeInTheDocument();
    fireEvent.click(screen.getByTitle('spoolTags.unlink'));

    await waitFor(() => expect(tagApi.unlink).toHaveBeenCalledWith(41, 'DEADBEEF'));
  });
});

describe('spool tags on an FH Edge station', () => {
  beforeEach(() => {
    resetMocks();
    // Web Serial is what makes the station available; jsdom has none.
    Object.defineProperty(navigator, 'serial', { value: {}, configurable: true });
  });

  afterEach(() => {
    Reflect.deleteProperty(navigator, 'serial');
    station.kit = null;
  });

  const openDialog = async () => {
    renderButton();
    fireEvent.click(screen.getByRole('button', { name: 'spoolTags.action' }));
    await screen.findByRole('dialog');
  };

  it('reads the tag on the station into the spool', async () => {
    station.kit = fakeEdgeKit();
    await openDialog();
    fireEvent.click(screen.getByRole('button', { name: 'edgeTags.readAndLink' }));

    await waitFor(() => expect(tagApi.link).toHaveBeenCalledWith(41, {
      uid: UID,
      technology: 'nfc',
      format: 'ntag215',
    }));
    expect(tagApi.identify).toHaveBeenCalledWith({ uid: UID, chip: 'ntag215', data: null });
    expect(toastMock.success).toHaveBeenCalledWith('spoolTags.linked', undefined, 'spool-tags');
  });

  it('writes the spool address to the tag and links it', async () => {
    station.kit = fakeEdgeKit();
    await openDialog();
    fireEvent.click(screen.getByRole('button', { name: 'edgeTags.write' }));

    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith('edgeTags.written', undefined, 'spool-tags'));
    expect(qrApi.issue).toHaveBeenCalledWith(41);
    expect(station.kit.tag?.uri).toBe(`https://filamenthub.ru/qr/${CODE}`);
    expect(tagApi.link).toHaveBeenCalledWith(41, { uid: UID, technology: 'nfc', format: 'ntag215' });
  });

  it('asks before replacing another address on the tag', async () => {
    station.kit = fakeEdgeKit({ tag: { uid: UID, type: 'ntag213', uri: 'https://example.com/spool/7' } });
    await openDialog();
    fireEvent.click(screen.getByRole('button', { name: 'edgeTags.write' }));

    expect(await screen.findByText('edgeTags.overwriteTitle')).toBeInTheDocument();
    expect(station.kit.tag?.uri).toBe('https://example.com/spool/7');
    fireEvent.click(screen.getByRole('button', { name: 'edgeTags.overwriteConfirm' }));

    await waitFor(() => expect(station.kit?.tag?.uri).toBe(`https://filamenthub.ru/qr/${CODE}`));
    await waitFor(() => expect(tagApi.link).toHaveBeenCalled());
  });

  it('asks before writing over the factory data on a tag', async () => {
    station.kit = fakeEdgeKit({ tag: { uid: UID, type: 'ntag213', data: 'W/WSZA==' } });
    tagApi.identify.mockResolvedValue({ uid: UID, status: 'unlinked', spool_id: null, format: 'tigertag' });
    await openDialog();
    fireEvent.click(screen.getByRole('button', { name: 'edgeTags.write' }));

    expect(await screen.findByText('edgeTags.overwriteFactoryMessage')).toBeInTheDocument();
    expect(station.kit.tag?.uri).toBeUndefined();
    fireEvent.click(screen.getByRole('button', { name: 'edgeTags.overwriteConfirm' }));
    await waitFor(() => expect(station.kit?.tag?.uri).toBe(`https://filamenthub.ru/qr/${CODE}`));
  });

  it('keeps the format of a factory tag it links', async () => {
    station.kit = fakeEdgeKit({ tag: { uid: UID, type: 'ntag213', data: 'W/WSZA==' } });
    tagApi.identify.mockResolvedValue({ uid: UID, status: 'unlinked', spool_id: null, format: 'tigertag' });
    await openDialog();
    fireEvent.click(screen.getByRole('button', { name: 'edgeTags.readAndLink' }));

    await waitFor(() => expect(tagApi.link).toHaveBeenCalledWith(41, { uid: UID, technology: 'nfc', format: 'tigertag' }));
    expect(tagApi.identify).toHaveBeenCalledWith({ uid: UID, chip: 'ntag213', data: 'W/WSZA==' });
  });

  it('leaves a tag of another spool untouched', async () => {
    station.kit = fakeEdgeKit();
    tagApi.identify.mockResolvedValue({ uid: UID, status: 'matched', spool_id: 7 });
    await openDialog();
    fireEvent.click(screen.getByRole('button', { name: 'edgeTags.write' }));

    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('edgeTags.errors.linked_elsewhere', undefined, 'spool-tags'));
    expect(station.kit.sent).toEqual(['{"command":"read"}']);
    expect(qrApi.issue).not.toHaveBeenCalled();
    expect(tagApi.link).not.toHaveBeenCalled();
  });

  it('explains a tag the station cannot write', async () => {
    station.kit = fakeEdgeKit({ tag: { uid: 'A1B2C3D4', type: 'iso14443a' } });
    await openDialog();
    fireEvent.click(screen.getByRole('button', { name: 'edgeTags.write' }));

    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('edgeTags.errors.not_writable', undefined, 'spool-tags'));
    expect(station.kit.sent).toEqual(['{"command":"read"}']);
  });
});
