import { act, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { EdgeDeviceMessage, EdgeKit } from '../../utils/edgeFirmware';
import { EdgeKitInstaller } from './EdgeKitInstaller';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, role: 'admin' } }),
}));

const account = vi.hoisted(() => ({
  createPairing: vi.fn(async (_payload: unknown) => ({
    pairing_id: 5, pairing_code: 'FE-ABCDEF-123456', expires_at: '',
  })),
  pairingStatus: vi.fn(async (_id: number): Promise<{ state: string; node: unknown }> => ({
    state: 'pending', node: null,
  })),
}));
vi.mock('../../api/client', () => ({ edgeNodesAPI: account }));

const device = vi.hoisted(() => ({
  send: vi.fn(async (_line: string) => undefined),
  restart: vi.fn(async () => undefined),
  close: vi.fn(async () => undefined),
  say: (_message: unknown) => undefined as void,
}));
vi.mock('../../utils/edgeDevice', () => ({
  isEdgeSerialSupported: () => true,
  requestEdgePort: async () => ({}),
  EdgeDeviceError: class extends Error {},
  EdgeBootloaderSession: { open: vi.fn() },
  EdgeConsole: {
    open: async (_port: unknown, onMessage: (message: unknown) => void) => {
      device.say = onMessage;
      return { send: device.send, restart: device.restart, close: device.close };
    },
  },
}));

const kit: EdgeKit = {
  id: 'kit',
  status: 'prototype',
  chip: 'ESP32-C3',
  board: 'Board',
  reader: 'Reader',
  nfcPins: { sck: 4, miso: 5, mosi: 6, nss: 7, busy: 0, rst: 1 },
  firmware: { version: '0.2.0', flashBytes: 4 << 20, partitionTableOffset: 0x8000, appOffset: 0x20000, images: [] },
};

async function connect() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <EdgeKitInstaller kit={kit} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'edgeKit.checkInstalled' }));
  });
}

const say = (message: EdgeDeviceMessage) => act(async () => device.say(message));
const boot = (configured: boolean) => say({
  kind: 'boot', firmware: '0.2.0', configured, provisionWindowMs: configured ? 15000 : 0,
});

async function submitLink() {
  fireEvent.change(screen.getByLabelText('edgeKit.link.ssid'), { target: { value: 'Home' } });
  fireEvent.change(screen.getByLabelText('edgeKit.link.password'), { target: { value: 'secret-pass' } });
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'edgeKit.link.submit' }));
  });
}

describe('EdgeKitInstaller', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.values(account).forEach((mock) => mock.mockClear());
    device.send.mockClear();
    device.restart.mockClear();
  });
  afterEach(() => vi.useRealTimers());

  it('links an empty kit to the account that is signed in', async () => {
    await connect();
    await boot(false);
    await submitLink();

    expect(account.createPairing).toHaveBeenCalledWith({
      name: 'edgeKit.link.nameDefault', kind: 'esp_kit', kit_id: 'kit',
    });
    expect(device.send).toHaveBeenCalledTimes(1);
    expect(JSON.parse(device.send.mock.calls[0][0])).toMatchObject({
      wifi: { ssid: 'Home', password: 'secret-pass' },
      node: { pairing_code: 'FE-ABCDEF-123456' },
      nfc: kit.nfcPins,
    });
    // The form lets go of the password once it has been handed over.
    expect(screen.queryByDisplayValue('secret-pass')).toBeNull();

    await say({ kind: 'provision', ok: true });
    await boot(true);
    await say({ kind: 'wifi', connected: true, reason: null });
    account.pairingStatus.mockResolvedValue({ state: 'activated', node: { name: 'Workbench' } });
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });

    expect(screen.getByText('edgeKit.link.done')).toBeTruthy();
    // Nothing keeps asking the server once the answer is known.
    const asked = account.pairingStatus.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(account.pairingStatus.mock.calls.length).toBe(asked);
  });

  it('replaces the settings of a configured kit only after a confirmation', async () => {
    await connect();
    await boot(true);
    await say({ kind: 'ready', nfc: true });
    // A configured kit may hold printer connections: connecting must not touch it.
    expect(device.send).not.toHaveBeenCalled();

    await submitLink();
    expect(account.createPairing).not.toHaveBeenCalled();
    expect(screen.getByText('edgeKit.link.replaceWarning')).toBeTruthy();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'confirmModal.confirm' }));
    });
    // It takes settings only in the window after a restart.
    expect(device.restart).toHaveBeenCalledTimes(1);
    expect(device.send).not.toHaveBeenCalled();
    await boot(true);
    expect(device.send).toHaveBeenCalledTimes(1);
    expect(JSON.parse(device.send.mock.calls[0][0]).node).toEqual({ pairing_code: 'FE-ABCDEF-123456' });
  });

  it('says why the kit could not get online and stops waiting for it', async () => {
    await connect();
    await boot(false);
    await submitLink();
    await say({ kind: 'provision', ok: true });
    await boot(true);
    await say({ kind: 'wifi', connected: false, reason: 'password' });

    expect(screen.getByText('edgeKit.link.errors.wifi_password')).toBeTruthy();
    const asked = account.pairingStatus.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(account.pairingStatus.mock.calls.length).toBe(asked);
  });
});
