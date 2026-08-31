import { useEffect } from 'react';
import { useQueryClient, type QueryClient } from '@tanstack/react-query';
import { physicalPrintersAPI, type PhysicalPrinter } from '../api/client';
import { latestDeviceContact } from '../utils/deviceLink';

export interface PrinterContactEvent {
  type: 'contact';
  printer_id: number;
  connector_id: number | null;
  last_seen_at: string | null;
  active: boolean;
  reports_feed: boolean | null;
}

const PRINTERS_KEY = ['physical-printers'];
const MAX_FRAME_BYTES = 64 * 1024;
const managers = new WeakMap<QueryClient, Map<number, { count: number; stop: () => void }>>();

/** Heartbeats change contact fields only, never observations or assignments. */
export function applyPrinterContact(printers: PhysicalPrinter[], event: PrinterContactEvent): PhysicalPrinter[] {
  return printers.map((printer) => {
    if (printer.id !== event.printer_id) return printer;
    if (event.connector_id === null) {
      if (printer.last_seen_at && event.last_seen_at && Date.parse(event.last_seen_at) < Date.parse(printer.last_seen_at)) return printer;
      const lastSeen = latestDeviceContact(printer.last_seen_at, event.last_seen_at);
      return { ...printer, last_seen_at: lastSeen, reports_feed: event.reports_feed ?? printer.reports_feed };
    }
    return {
      ...printer,
      connectors: printer.connectors.map((connector) => connector.id === event.connector_id
        ? { ...connector, last_seen_at: latestDeviceContact(connector.last_seen_at, event.last_seen_at) }
        : connector),
    };
  });
}

/** Serialize snapshot-before-contact delivery, with a bounded slow-screen queue. */
export async function readPrinterContactStream(
  socket: WebSocket,
  onEvent: (name: string, data: unknown) => Promise<void> | void,
  signal: AbortSignal,
): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    let ended = false;
    let queued = 0;
    let delivery = Promise.resolve();
    const finish = (error?: Error) => {
      if (ended) return;
      ended = true;
      signal.removeEventListener('abort', abort);
      socket.removeEventListener('message', message);
      socket.removeEventListener('close', close);
      socket.removeEventListener('error', fail);
      socket.close();
      if (error) reject(error); else resolve();
    };
    const abort = () => finish();
    const close = () => finish();
    const fail = () => finish(new Error('Printer contact connection closed'));
    const message = (event: MessageEvent) => {
      if (typeof event.data !== 'string' || event.data.length > MAX_FRAME_BYTES || ++queued > 32) {
        finish(new Error('Printer contact queue exceeded'));
        return;
      }
      delivery = delivery.then(async () => {
        if (ended || signal.aborted) return;
        const data = JSON.parse(event.data);
        await onEvent(data.type, data);
      }).catch(fail).finally(() => { queued--; });
    };
    socket.addEventListener('message', message);
    socket.addEventListener('close', close);
    socket.addEventListener('error', fail);
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
  });
}

function isContact(value: unknown): value is PrinterContactEvent {
  if (!value || typeof value !== 'object') return false;
  const item = value as PrinterContactEvent;
  return item.type === 'contact' && Number.isSafeInteger(item.printer_id)
    && (item.connector_id === null || Number.isSafeInteger(item.connector_id))
    && (item.last_seen_at === null || (typeof item.last_seen_at === 'string' && Number.isFinite(Date.parse(item.last_seen_at))))
    && typeof item.active === 'boolean'
    && (item.reports_feed === null || typeof item.reports_feed === 'boolean');
}

function isBridgeQuery(key: readonly unknown[], printerId?: number): boolean {
  return (key[0] === 'printer-bridge-status' || key[0] === 'octoprint-bridge-status')
    && (printerId === undefined || key[1] === printerId);
}

function startContactStream(client: QueryClient): () => void {
  let stopped = false;
  let controller: AbortController | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | undefined;
  let resyncTimer: ReturnType<typeof setTimeout> | undefined;
  let lastRefreshAt = 0;
  let failures = 0;
  const visible = () => !stopped && document.visibilityState !== 'hidden' && navigator.onLine !== false;

  const refresh = async () => {
    lastRefreshAt = Date.now();
    await Promise.all([
      client.invalidateQueries({ queryKey: PRINTERS_KEY }),
      client.invalidateQueries({ predicate: (query) => isBridgeQuery(query.queryKey) }),
    ]);
  };
  const requestResync = () => {
    if (resyncTimer !== undefined) return;
    resyncTimer = setTimeout(() => {
      resyncTimer = undefined;
      if (visible()) void refresh().catch(() => undefined);
    }, Math.max(100, 5_000 - (Date.now() - lastRefreshAt)));
  };

  const onContact = async (event: PrinterContactEvent) => {
    const printers = client.getQueryData<PhysicalPrinter[]>(PRINTERS_KEY);
    const printer = printers?.find((item) => item.id === event.printer_id);
    const connector = printer?.connectors.find((item) => item.id === event.connector_id);
    if (!printer || (event.connector_id !== null && (!connector || !connector.active))
      || !event.active || !event.last_seen_at) {
      // A reset or new connector needs its authoritative shape, not a guessed
      // patch. This is exceptional; ordinary heartbeats never issue a GET.
      requestResync();
      return;
    }
    client.setQueryData<PhysicalPrinter[]>(PRINTERS_KEY, (old) => old && applyPrinterContact(old, event));
    if (connector) {
      client.setQueriesData<{ last_seen_at: string | null }>({
        predicate: ({ queryKey }) => isBridgeQuery(queryKey, printer.id)
          && queryKey[2] === connector.material_system_id
          && (queryKey[0] === 'octoprint-bridge-status'
            ? connector.provider === 'octoprint' && connector.transport === 'bridge_https'
            : connector.transport === (queryKey[3] ?? 'orca_plugin_lan')),
      }, (old) => old && ({ ...old, last_seen_at: latestDeviceContact(old.last_seen_at, event.last_seen_at) }));
    }
  };

  const connect = async () => {
    if (!visible() || controller) return;
    const active = new AbortController();
    controller = active;
    const started = Date.now();
    let retryAfter = 0;
    try {
      const stream = await physicalPrintersAPI.contactEvents(active.signal);
      await readPrinterContactStream(stream, async (name, data) => {
        if (active.signal.aborted) return;
        if (name === 'ready') await refresh();
        else if (name === 'contact' && isContact(data)) await onContact(data);
      }, active.signal);
    } catch (error) {
      const response = (error as { response?: { status?: number; headers?: Record<string, string> } })?.response;
      if (response?.status === 401 || response?.status === 403) {
        // The shared API client already attempted session refresh. Do not turn
        // rejected authentication into a background login/reconnect loop.
        stopped = true;
      }
      const retrySeconds = Number(response?.headers?.['retry-after'] ?? 0);
      retryAfter = Number.isFinite(retrySeconds) ? Math.min(300, Math.max(0, retrySeconds)) * 1000 : 0;
    } finally {
      if (controller === active) controller = null;
      if (!active.signal.aborted && visible()) {
        failures = Date.now() - started > 30_000 ? 0 : failures + 1;
        const backoff = Math.min(60_000, 2_000 * 2 ** Math.min(failures, 5));
        const delay = Math.max(retryAfter, backoff * (0.5 + Math.random() * 0.5));
        retryTimer = setTimeout(() => { void connect(); }, delay);
      }
    }
  };

  const pause = () => {
    clearTimeout(retryTimer);
    clearTimeout(resyncTimer);
    resyncTimer = undefined;
    controller?.abort();
    controller = null;
  };
  const visibilityChanged = () => {
    if (visible()) { clearTimeout(retryTimer); void connect(); }
    else pause();
  };
  document.addEventListener('visibilitychange', visibilityChanged);
  window.addEventListener('online', visibilityChanged);
  window.addEventListener('offline', visibilityChanged);
  window.addEventListener('pagehide', pause);
  window.addEventListener('pageshow', visibilityChanged);
  void connect();
  return () => {
    stopped = true;
    pause();
    document.removeEventListener('visibilitychange', visibilityChanged);
    window.removeEventListener('online', visibilityChanged);
    window.removeEventListener('offline', visibilityChanged);
    window.removeEventListener('pagehide', pause);
    window.removeEventListener('pageshow', visibilityChanged);
  };
}

/** Mount only alongside a visible printer-status surface, not the whole app. */
export function usePrinterContactEvents(userId: number | null | undefined): void {
  const client = useQueryClient();
  useEffect(() => {
    if (!userId) return;
    let users = managers.get(client);
    if (!users) { users = new Map(); managers.set(client, users); }
    let manager = users.get(userId);
    if (!manager) { manager = { count: 0, stop: startContactStream(client) }; users.set(userId, manager); }
    manager.count++;
    return () => {
      if (--manager.count === 0) { manager.stop(); users.delete(userId); }
    };
  }, [client, userId]);
}
