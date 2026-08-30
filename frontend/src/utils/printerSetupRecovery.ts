import type { physicalPrintersAPI } from '../api/client';
import type { PrinterSetupResult } from './pluginBridge';
import { safeStorage } from './storage';

export type PrinterSetupRoute = 'manual' | 'orca' | 'edge';
export interface PendingPrinterSetup {
  payload: Parameters<typeof physicalPrintersAPI.create>[0];
  targetId: number;
  probe: PrinterSetupResult | null;
  route?: PrinterSetupRoute;
}

const historyKey = 'fhPrinterSetup';
const storageKey = (userId: number) => 'fh-printer-setup-' + userId;

function parseIntent(value: string | null): PendingPrinterSetup | null {
  try {
    const item = JSON.parse(value || 'null');
    return typeof item?.payload?.name === 'string'
      && typeof item.payload.request_id === 'string'
      && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(item.payload.request_id)
      && Number.isSafeInteger(item.targetId) && item.targetId >= 0
      && (item.route === undefined || ['manual', 'orca', 'edge'].includes(item.route))
      ? item : null;
  } catch { return null; }
}

function readHistoryIntent(userId: number): PendingPrinterSetup | null {
  try {
    const entry = window.history.state?.[historyKey];
    return entry?.userId === userId ? parseIntent(entry.intent) : null;
  } catch { return null; }
}

export function readPrinterSetupIntent(userId: number): PendingPrinterSetup | null {
  // A tab's own operation takes precedence over another tab's shared draft.
  return readHistoryIntent(userId) ?? parseIntent(safeStorage.get(storageKey(userId)));
}

export function persistPrinterSetupIntent(userId: number, intent: PendingPrinterSetup): boolean {
  const serialized = JSON.stringify(intent);
  const stored = safeStorage.set(storageKey(userId), serialized);
  let inHistory = JSON.stringify(readHistoryIntent(userId)) === serialized;
  try {
    // Preserve router-owned state and the URL. Session history survives reload
    // even when an embedded browser denies localStorage.
    if (!inHistory) window.history.replaceState({
      ...window.history.state, [historyKey]: { userId, intent: serialized },
    }, '');
    inHistory = JSON.stringify(readHistoryIntent(userId)) === serialized;
  } catch { /* The caller must not send a non-recoverable creation request. */ }
  if (!stored && !inHistory) safeStorage.remove(storageKey(userId));
  return stored || inHistory;
}

export function clearPrinterSetupIntent(userId: number, requestId: string | undefined): void {
  if (!requestId) return;
  if (parseIntent(safeStorage.get(storageKey(userId)))?.payload.request_id === requestId) {
    safeStorage.remove(storageKey(userId));
  }
  if (readHistoryIntent(userId)?.payload.request_id !== requestId) return;
  try {
    const state = { ...window.history.state };
    delete state[historyKey];
    window.history.replaceState(state, '');
  } catch { /* Replaying this already acknowledged request is idempotent. */ }
}
