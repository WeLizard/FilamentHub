import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { applyPrinterContact, usePrinterContactEvents, type PrinterContactEvent } from './usePrinterContactEvents';
import type { PhysicalPrinter } from '../api/client';

const api = vi.hoisted(() => ({ list: vi.fn(), contactEvents: vi.fn() }));
vi.mock('../api/client', () => ({ physicalPrintersAPI: api }));

const oldTime = '2026-08-31T00:00:00Z';
const newTime = '2026-08-31T00:10:00Z';
const printer = {
  id: 11, last_seen_at: oldTime, reports_feed: true,
  connectors: [{ id: 21, material_system_id: 31, provider: 'octoprint', transport: 'bridge_https', active: true, last_seen_at: oldTime }],
  material_systems: [{ id: 31, slots: [{ id: 41, assignment: { spool_id: 51 } }] }],
} as PhysicalPrinter;
const update: PrinterContactEvent = {
  type: 'contact', printer_id: 11, connector_id: 21, last_seen_at: newTime,
  active: true, reports_feed: null,
};

function Surface() {
  const { data } = useQuery({ queryKey: ['physical-printers'], queryFn: api.list });
  usePrinterContactEvents(7);
  return <span>{data?.[0]?.connectors[0]?.last_seen_at}</span>;
}

describe('visible printer contact updates', () => {
  class Socket extends EventTarget {
    close() { this.dispatchEvent(new Event('close')); }
  }
  const streams: Array<{ socket: Socket; signal: AbortSignal }> = [];
  const clients: QueryClient[] = [];
  const send = (index: number, name: string, data: unknown) => {
    streams[index].socket.dispatchEvent(new MessageEvent('message', { data: JSON.stringify({ ...(data as object), type: name }) }));
  };
  beforeEach(() => {
    vi.clearAllMocks();
    streams.length = 0;
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
    api.list.mockResolvedValue([printer]);
    api.contactEvents.mockImplementation((signal: AbortSignal) => {
      const socket = new Socket();
      streams.push({ socket, signal });
      return Promise.resolve(socket);
    });
  });
  afterEach(() => {
    clients.forEach((client) => client.clear());
    clients.length = 0;
    vi.useRealTimers();
  });
  const renderSurfaces = () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
    clients.push(client);
    return { client, ...render(<QueryClientProvider client={client}><Surface /><Surface /></QueryClientProvider>) };
  };

  it('shares one channel, restores the badge without polling, and closes while hidden/unmounted', async () => {
    const view = renderSurfaces();
    await waitFor(() => expect(api.contactEvents).toHaveBeenCalledTimes(1));
    await act(async () => send(0, 'ready', {}));
    await waitFor(() => expect(screen.getAllByText(oldTime)).toHaveLength(2));
    const snapshotCalls = api.list.mock.calls.length;
    view.client.setQueryData(['octoprint-bridge-status', 11, 31], { last_seen_at: oldTime, paired: true });
    view.client.setQueryData(['octoprint-bridge-status', 11, 32], { last_seen_at: oldTime, paired: true });
    view.client.setQueryData(['printer-bridge-status', 11, 31, 'edge_agent'], { last_seen_at: oldTime, paired: true });
    await act(async () => send(0, 'contact', update));
    await waitFor(() => expect(screen.getAllByText(newTime)).toHaveLength(2));
    expect(api.list).toHaveBeenCalledTimes(snapshotCalls);
    expect(view.client.getQueryData<PhysicalPrinter[]>(['physical-printers'])?.[0].material_systems).toBe(printer.material_systems);
    expect(view.client.getQueryData(['octoprint-bridge-status', 11, 31])).toEqual({ last_seen_at: newTime, paired: true });
    expect(view.client.getQueryData(['octoprint-bridge-status', 11, 32])).toEqual({ last_seen_at: oldTime, paired: true });
    expect(view.client.getQueryData(['printer-bridge-status', 11, 31, 'edge_agent'])).toEqual({ last_seen_at: oldTime, paired: true });
    vi.useFakeTimers();
    await act(async () => { await vi.advanceTimersByTimeAsync(10 * 60_000); });
    expect(api.list).toHaveBeenCalledTimes(snapshotCalls);
    expect(api.contactEvents).toHaveBeenCalledTimes(1);
    await act(async () => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(streams[0].signal.aborted).toBe(true);
    await act(async () => { await vi.advanceTimersByTimeAsync(10 * 60_000); });
    expect(api.contactEvents).toHaveBeenCalledTimes(1);
    await act(async () => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(api.contactEvents).toHaveBeenCalledTimes(2);
    await act(async () => send(1, 'ready', {}));
    expect(api.list.mock.calls.length).toBeGreaterThan(snapshotCalls);
    view.unmount();
    expect(streams[1].signal.aborted).toBe(true);
    await act(async () => { await vi.advanceTimersByTimeAsync(10 * 60_000); });
    expect(api.contactEvents).toHaveBeenCalledTimes(2);
  });

  it('does not open on a hidden screen and backs off after connection failure', async () => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    api.contactEvents.mockRejectedValue(new Error('unreachable'));
    vi.useFakeTimers();
    const view = renderSurfaces();
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(api.contactEvents).not.toHaveBeenCalled();
    await act(async () => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(api.contactEvents).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(api.contactEvents).toHaveBeenCalledTimes(1);
    view.unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(api.contactEvents).toHaveBeenCalledTimes(1);
  });

  it('does not regress a newer contact or change another printer and its spool assignments', () => {
    const other = { ...printer, id: 12 };
    const patched = applyPrinterContact([printer, other], update);
    const delayed = applyPrinterContact(patched, { ...update, last_seen_at: oldTime });
    expect(delayed[0].connectors[0].last_seen_at).toBe(newTime);
    expect(delayed[0].material_systems).toBe(printer.material_systems);
    expect(delayed[1]).toBe(other);
    const inventory = applyPrinterContact([printer], { ...update, connector_id: null, reports_feed: true });
    expect(inventory[0].last_seen_at).toBe(newTime);
    const lateInventory = applyPrinterContact(inventory, { ...update, connector_id: null, last_seen_at: oldTime, reports_feed: false });
    expect(lateInventory[0].reports_feed).toBe(true);
  });

  it('coalesces reset bursts and cancels a queued refresh when the screen hides', async () => {
    const view = renderSurfaces();
    await waitFor(() => expect(api.contactEvents).toHaveBeenCalledTimes(1));
    await act(async () => send(0, 'ready', {}));
    const snapshotCalls = api.list.mock.calls.length;
    vi.useFakeTimers();
    await act(async () => {
      for (let index = 0; index < 20; index++) send(0, 'contact', { ...update, last_seen_at: null });
    });
    expect(api.list).toHaveBeenCalledTimes(snapshotCalls);
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(api.list).toHaveBeenCalledTimes(snapshotCalls + 1);
    await act(async () => {
      send(0, 'contact', { ...update, printer_id: 999 });
    });
    await act(async () => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
      document.dispatchEvent(new Event('visibilitychange'));
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(api.list).toHaveBeenCalledTimes(snapshotCalls + 1);
    view.unmount();
  });

  it('does not reconnect after authentication has been rejected', async () => {
    api.contactEvents.mockRejectedValue({ response: { status: 401 } });
    vi.useFakeTimers();
    const view = renderSurfaces();
    await act(async () => { await vi.advanceTimersByTimeAsync(10 * 60_000); });
    expect(api.contactEvents).toHaveBeenCalledTimes(1);
    await act(async () => { window.dispatchEvent(new Event('online')); });
    expect(api.contactEvents).toHaveBeenCalledTimes(1);
    view.unmount();
  });
});
