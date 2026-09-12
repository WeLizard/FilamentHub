/**
 * Мост между каталогом и Python-плагином OrcaSlicer.
 *
 * Актуальный Pages API грузит наш SPA напрямую по /embed/catalog. Действия из
 * каталога уходят в официальный window.orca bridge. Совместимость со старым
 * iframe-host сохраняется через window.parent.postMessage.
 *
 * Это ОТДЕЛЬНЫЙ путь от форкового моста (window.filamenthub / window.wx) —
 * тот WebView-мост не трогаем, он продолжает работать как раньше.
 */

import { stripLocalePrefix } from './siteLocale';
import type { PrinterSetupConnection } from '../api/client';

export const PLUGIN_MESSAGE_SOURCE = 'filamenthub-plugin';
const PLUGIN_HOST_MESSAGE_SOURCE = 'filamenthub-host';

const EMBED_FLAG = 'fh_plugin_embed';

// В iframe плагина sessionStorage недоступен (SecurityError в партиционированном
// контексте), поэтому липкость режима держит модульный флаг: SPA-навигация
// страницу не перезагружает, и он живёт всю iframe-сессию. sessionStorage
// остаётся страховкой на жёсткую перезагрузку в обычном браузере.
let embedSessionFlag = false;
let activePluginToken: string | null = null;
let activePluginCapabilities = new Set<string>();
let directPluginBridgeInstalled = false;
let activeDirectBridgeSession: string | null = null;
let activePluginRuntime = { showDiagnostics: false };
const pluginRuntimeListeners = new Set<(runtime: PluginRuntimeState) => void>();

export interface PluginRuntimeState {
  showDiagnostics: boolean;
}

function updatePluginRuntime(incoming: Record<string, unknown>): void {
  activePluginRuntime = {
    showDiagnostics: incoming.showDiagnostics === true,
  };
  pluginRuntimeListeners.forEach((listener) => listener(activePluginRuntime));
}

/** Follow host-owned runtime flags; build mode is not a plugin setting. */
export function subscribeToPluginRuntime(
  listener: (runtime: PluginRuntimeState) => void,
): () => void {
  pluginRuntimeListeners.add(listener);
  listener(activePluginRuntime);
  return () => pluginRuntimeListeners.delete(listener);
}

function directBridgeSession(): string | null {
  if (typeof window === 'undefined') return null;
  if (activeDirectBridgeSession) return activeDirectBridgeSession;
  const value = new URLSearchParams(window.location.hash.slice(1)).get('fh_bridge');
  if (value && /^[A-Za-z0-9_-]{20,200}$/.test(value)) {
    activeDirectBridgeSession = value;
  }
  return activeDirectBridgeSession;
}

export function isDirectPluginHost(): boolean {
  return typeof window !== 'undefined'
    && window.parent === window
    && typeof window.orca?.postMessage === 'function'
    && directBridgeSession() !== null;
}

/** Retain the per-tab binding when SPA navigation changes the embedded route. */
export function preserveDirectPluginBridgeBinding(): void {
  if (!isDirectPluginHost()) return;
  const session = directBridgeSession();
  if (!session) return;
  const expectedHash = `#fh_bridge=${encodeURIComponent(session)}`;
  if (window.location.hash === expectedHash) return;
  window.history.replaceState(
    window.history.state,
    '',
    `${window.location.pathname}${window.location.search}${expectedHash}`,
  );
}

function ensureDirectPluginBridge(): boolean {
  if (!isDirectPluginHost()) return false;
  if (directPluginBridgeInstalled) return true;
  directPluginBridgeInstalled = true;
  window.orca?.onMessage?.((incoming) => {
    let data = incoming;
    if (data && typeof data === 'object') {
      const message = data as Record<string, unknown>;
      if (
        message.source === PLUGIN_HOST_MESSAGE_SOURCE
        && message.type === 'switch-to-local-shell'
        && typeof message.url === 'string'
        && isLoopbackOrigin(message.url)
      ) {
        window.location.replace(message.url);
        return;
      }
      if (message.source === PLUGIN_HOST_MESSAGE_SOURCE && message.type === 'transport') {
        updatePluginRuntime(message);
      }
      if (message.source === PLUGIN_HOST_MESSAGE_SOURCE) {
        data = { ...message, source: PLUGIN_MESSAGE_SOURCE };
      }
    }
    window.dispatchEvent(new MessageEvent('message', {
      data,
      origin: window.location.origin,
      source: window,
    }));
  });
  window.orca?.postMessage({
    source: PLUGIN_MESSAGE_SOURCE,
    type: 'host-ready',
    bridgeSession: directBridgeSession(),
  });
  return true;
}

/**
 * Запущен ли каталог во встроенном (плагинном) режиме. Определяем по маршруту
 * /embed и запоминаем на сессию, чтобы режим сохранялся при переходах внутри
 * iframe (например, на страницу материала).
 */
export function isPluginEmbed(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  if (isDirectPluginHost()) {
    ensureDirectPluginBridge();
    embedSessionFlag = true;
    try {
      sessionStorage.setItem(EMBED_FLAG, '1');
    } catch {
      // The host WebView may partition storage; the URL binding remains enough.
    }
    return true;
  }
  if (stripLocalePrefix(window.location.pathname).startsWith('/embed')) {
    ensureDirectPluginBridge();
    embedSessionFlag = true;
    try {
      sessionStorage.setItem(EMBED_FLAG, '1');
    } catch {
      // Хранилище недоступно (iframe плагина) — хватит модульного флага.
    }
    return true;
  }
  if (embedSessionFlag) {
    return true;
  }
  try {
    return sessionStorage.getItem(EMBED_FLAG) === '1';
  } catch {
    return false;
  }
}

interface PluginMessage {
  source: typeof PLUGIN_MESSAGE_SOURCE;
  type: string;
  [key: string]: unknown;
}

function postToPlugin(message: PluginMessage): void {
  if (typeof window === 'undefined') {
    return;
  }
  if (ensureDirectPluginBridge()) {
    window.orca?.postMessage({
      ...message,
      bridgeSession: directBridgeSession(),
    });
    return;
  }
  if (window.parent === window) {
    return;
  }
  window.parent.postMessage(message, '*');
}

function isLoopbackOrigin(origin: string): boolean {
  try {
    const url = new URL(origin);
    return url.protocol === 'http:' && (url.hostname === '127.0.0.1' || url.hostname === 'localhost');
  } catch {
    return false;
  }
}

export const PLUGIN_OAUTH_HANDOFF_KEY = 'fh_plugin_oauth_handoff';

export interface PluginOAuthBrowserHandoff {
  flowId: string;
}

function validPluginOAuthCredential(value: unknown): value is string {
  return typeof value === 'string' && /^[A-Za-z0-9_-]{24,128}$/.test(value);
}

/** Keep the browser-only half of a server-backed plugin OAuth flow across the provider redirect. */
export function rememberPluginOAuthHandoff(flowId: string): boolean {
  if (!validPluginOAuthCredential(flowId)) {
    return false;
  }
  try {
    sessionStorage.setItem(PLUGIN_OAUTH_HANDOFF_KEY, JSON.stringify({ flowId }));
    return true;
  } catch {
    return false;
  }
}

export function readPluginOAuthHandoff(): PluginOAuthBrowserHandoff | null {
  try {
    const raw = sessionStorage.getItem(PLUGIN_OAUTH_HANDOFF_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as { flowId?: unknown };
    if (validPluginOAuthCredential(parsed.flowId)) {
      return { flowId: parsed.flowId };
    }
  } catch {
    // Storage is unavailable or corrupt; treat the browser as a normal OAuth flow.
  }
  return null;
}

export function clearPluginOAuthHandoff(): void {
  try {
    sessionStorage.removeItem(PLUGIN_OAUTH_HANDOFF_KEY);
  } catch {
    // The flow will expire server-side even when browser storage is unavailable.
  }
}

function isTrustedPluginParentEvent(event: MessageEvent): boolean {
  if (event.source !== window.parent) {
    return false;
  }
  // Direct Pages messages are normalized into same-window MessageEvents. The
  // older shell path still uses an opaque or loopback parent origin.
  return (
    event.origin === 'null' ||
    event.origin === window.location.origin ||
    isLoopbackOrigin(event.origin)
  );
}

/**
 * Убрать тему хоста OrcaSlicer из нашего документа в embed-режиме.
 *
 * PluginWebDialog инжектит <style id="orca-host-theme"> через AddUserScript,
 * а WebView2 исполняет user-скрипты во всех фреймах, включая наш iframe.
 * Эти правила (h1-h6/button/input и т.д.) — вне CSS-слоёв, поэтому бьют любые
 * Tailwind-утилиты (v4 = нативные cascade layers) и перекрашивают сайт.
 * Тема предназначена для страниц плагинов, не для полноценного SPA — удаляем.
 */
export function stripOrcaHostTheme(): void {
  if (typeof document === 'undefined' || !isPluginEmbed()) {
    return;
  }
  // The injected style id was renamed upstream (orca-host-theme →
  // orca-plugin-defaults in the PR #14530 lifecycle refactor); strip both so
  // the SPA stays correct on either host build.
  const hostThemeIds = ['orca-host-theme', 'orca-plugin-defaults'];
  const removeIfPresent = () => {
    let removed = false;
    for (const id of hostThemeIds) {
      const style = document.getElementById(id);
      if (style) {
        style.remove();
        removed = true;
      }
    }
    return removed;
  };
  if (removeIfPresent()) {
    return;
  }
  // Инжект идёт при document-start и может опередить или отстать от бандла —
  // страхуемся наблюдателем и снимаем его, как только стиль удалён.
  const observer = new MutationObserver(() => {
    if (removeIfPresent()) {
      observer.disconnect();
    }
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.setTimeout(() => observer.disconnect(), 10000);
}

/**
 * Подписка на команды навигации от шелла плагина: кнопки Catalog/Profile/Wiki
 * над iframe шлют postMessage вниз, SPA переходит по роуту без перезагрузки.
 * Возвращает функцию отписки.
 */
export function subscribeToPluginNavigation(onNavigate: (path: string) => void): () => void {
  const handler = (event: MessageEvent) => {
    if (!isTrustedPluginParentEvent(event)) {
      return;
    }
    const data = event.data as Partial<PluginMessage> | undefined;
    if (!data || data.source !== PLUGIN_MESSAGE_SOURCE || data.type !== 'navigate') {
      return;
    }
    const path = (data as { path?: unknown }).path;
    if (typeof path === 'string' && path.startsWith('/')) {
      onNavigate(path);
    }
  };
  window.addEventListener('message', handler);
  return () => window.removeEventListener('message', handler);
}

/**
 * Подписка на сводку синка от Python через официальный host bridge. Installed
 * iframe-shell builds relay the same message shape for rolling compatibility.
 */
export interface PluginSyncResult {
  text: string;
  draftCount: number;
  operationId: string;
  scope: PluginSyncScope;
  status: 'success' | 'warning' | 'error';
  contours: Array<{
    kind: 'filament' | 'machine' | 'process';
    status: 'success' | 'warning' | 'error';
    summary: string;
  }>;
}

export type PluginSyncScope = 'all' | 'filament' | 'machine' | 'process';

function pluginRequestId(prefix: string): string {
  const random = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${random}`;
}

export function subscribeToPluginSyncResult(
  onResult: (result: PluginSyncResult) => void,
): () => void {
  const handler = (event: MessageEvent) => {
    if (!isTrustedPluginParentEvent(event)) {
      return;
    }
    const data = event.data as Partial<PluginMessage> | undefined;
    if (!data || data.source !== PLUGIN_MESSAGE_SOURCE || data.type !== 'sync-result') {
      return;
    }
    const payload = data as {
      text?: unknown;
      draftCount?: unknown;
      operationId?: unknown;
      scope?: unknown;
      status?: unknown;
      contours?: unknown;
    };
    const text = payload.text;
    if (typeof text === 'string' && text) {
      const rawDraftCount = Number(payload.draftCount);
      onResult({
        text,
        draftCount: Number.isSafeInteger(rawDraftCount) && rawDraftCount > 0
          ? rawDraftCount
          : 0,
        operationId: typeof payload.operationId === 'string' ? payload.operationId : '',
        scope: ['all', 'filament', 'machine', 'process'].includes(String(payload.scope))
          ? payload.scope as PluginSyncScope
          : 'all',
        status: ['success', 'warning', 'error'].includes(String(payload.status))
          ? payload.status as PluginSyncResult['status']
          : 'success',
        contours: Array.isArray(payload.contours)
          ? payload.contours.flatMap((item): PluginSyncResult['contours'] => {
              if (!item || typeof item !== 'object') return [];
              const contour = item as Record<string, unknown>;
              if (
                !['filament', 'machine', 'process'].includes(String(contour.kind))
                || !['success', 'warning', 'error'].includes(String(contour.status))
                || typeof contour.summary !== 'string'
              ) return [];
              return [{
                kind: contour.kind as PluginSyncResult['contours'][number]['kind'],
                status: contour.status as PluginSyncResult['contours'][number]['status'],
                summary: contour.summary,
              }];
            })
          : [],
      });
    }
  };
  window.addEventListener('message', handler);
  return () => window.removeEventListener('message', handler);
}

export interface RecoverItem {
  key: string;
  kind: 'filament' | 'machine' | 'process';
  name: string;
  account?: string;
  source: 'live' | 'backup';
  imported: boolean;
}

export function subscribeToPluginNotice(
  onNotice: (notice: { text: string; status: 'success' | 'warning' | 'error' | 'info' }) => void,
): () => void {
  const handler = (event: MessageEvent) => {
    if (!isTrustedPluginParentEvent(event)) return;
    const data = event.data as Partial<PluginMessage> | undefined;
    if (!data || data.source !== PLUGIN_MESSAGE_SOURCE || data.type !== 'plugin-notice') return;
    const payload = data as { text?: unknown; status?: unknown };
    if (typeof payload.text !== 'string' || !payload.text) return;
    const status = ['success', 'warning', 'error', 'info'].includes(String(payload.status))
      ? payload.status as 'success' | 'warning' | 'error' | 'info'
      : 'info';
    onNotice({ text: payload.text, status });
  };
  window.addEventListener('message', handler);
  return () => window.removeEventListener('message', handler);
}

/**
 * Подписка на список найденных локальных пресетов от кнопки Recover: плагин сканит
 * диск, отдаёт список — SPA показывает окно выбора с чекбоксами.
 */
export function subscribeToPluginRecoverList(onList: (items: RecoverItem[]) => void): () => void {
  const handler = (event: MessageEvent) => {
    if (!isTrustedPluginParentEvent(event)) {
      return;
    }
    const data = event.data as Partial<PluginMessage> | undefined;
    if (!data || data.source !== PLUGIN_MESSAGE_SOURCE || data.type !== 'recover-list') {
      return;
    }
    const items = (data as { items?: unknown }).items;
    if (Array.isArray(items)) {
      const normalized = items.flatMap((raw): RecoverItem[] => {
        if (!raw || typeof raw !== 'object') return [];
        const item = raw as Partial<RecoverItem>;
        if (typeof item.name !== 'string' || !item.name) return [];
        const imported = typeof item.imported === 'boolean' ? item.imported : false;
        if (
          typeof item.key === 'string' &&
          ['filament', 'machine', 'process'].includes(item.kind ?? '') &&
          ['live', 'backup'].includes(item.source ?? '') &&
          (item.account === undefined || typeof item.account === 'string')
        ) {
          return [{ ...item, imported } as RecoverItem];
        }
        // Compatibility with installed plugin builds that only recovered
        // filaments and sent {name, imported}. The old plugin also expects the
        // selected name back verbatim, hence key=name here.
        return [{
          key: item.name,
          kind: 'filament',
          name: item.name,
          source: 'live',
          imported,
        }];
      });
      onList(normalized);
    }
  };
  window.addEventListener('message', handler);
  return () => window.removeEventListener('message', handler);
}

/** Отправить плагину непротиворечивые kind:name ключи выбранных пресетов. */
export function sendRecoverImport(keys: string[]): void {
  postToPlugin({ source: PLUGIN_MESSAGE_SOURCE, type: 'recover-import', names: keys });
}

/** Request the plugin-owned Recovery Center inventory. */
export function requestPluginRecovery(): void {
  postToPlugin({ source: PLUGIN_MESSAGE_SOURCE, type: 'recover' });
}

/** Request the plugin diagnostic log through the bound host bridge. */
export function requestPluginDiagnostics(): void {
  postToPlugin({ source: PLUGIN_MESSAGE_SOURCE, type: 'read-diagnostics' });
}

export function subscribeToPluginDiagnostics(onDiagnostics: (text: string) => void): () => void {
  const handler = (event: MessageEvent) => {
    if (!isTrustedPluginParentEvent(event)) return;
    const data = event.data as Partial<PluginMessage> | undefined;
    if (!data || data.source !== PLUGIN_MESSAGE_SOURCE || data.type !== 'diagnostics') return;
    const diagnostics = (data as { text?: unknown }).text;
    if (typeof diagnostics === 'string') onDiagnostics(diagnostics);
  };
  window.addEventListener('message', handler);
  return () => window.removeEventListener('message', handler);
}

/**
 * Статус сессии для тулбара шелла: имя пользователя + счётчик пресетов
 * (аналог лейблов форковой панели). null — гость, шелл вернёт бренд-надпись.
 */
export function reportAuthStateToPlugin(label: string | null): void {
  if (!isPluginEmbed()) {
    return;
  }
  postToPlugin({ source: PLUGIN_MESSAGE_SOURCE, type: 'auth-state', label });
}

/**
 * Передать Python-плагину только короткоживущую capability-сессию. Основные
 * access/refresh credentials браузера никогда не пересекают plugin bridge.
 */
export function reportPluginSessionToPlugin(pluginToken: string): void {
  if (!isPluginEmbed()) {
    return;
  }
  activePluginToken = pluginToken;
  postToPlugin({
    source: PLUGIN_MESSAGE_SOURCE,
    type: 'auth-token',
    accessToken: pluginToken,
    refreshToken: '',
  });
}

/** Выход: плагин удаляет сохранённые токены. */
export function reportLogoutToPlugin(): void {
  if (!isPluginEmbed()) {
    return;
  }
  activePluginToken = null;
  postToPlugin({ source: PLUGIN_MESSAGE_SOURCE, type: 'auth-logout' });
}

/**
 * Профиль пользователя изменился (пресет добавлен/удалён): плагин запускает
 * автосинхронизацию, чтобы изменение попало в слайсер без ручного Sync.
 */
export function notifyProfileChanged(): void {
  if (!isPluginEmbed()) {
    return;
  }
  postToPlugin({ source: PLUGIN_MESSAGE_SOURCE, type: 'profile-changed' });
}

/**
 * Run the same complete preset sync as the Sync control in the plugin toolbar.
 * Machine, process and filament profiles are reconciled together by Python;
 * the page waits for the real result before refreshing its server data.
 */
export function requestPluginProfileSync(
  scope: PluginSyncScope = 'all',
): Promise<{ message?: string }> {
  if (!isPluginEmbed()) {
    return Promise.reject(new Error());
  }

  const operationId = pluginRequestId('sync');
  return new Promise((resolve, reject) => {
    let timeoutId: number | null = null;
    const cleanup = () => {
      window.removeEventListener('message', onMessage);
      if (timeoutId !== null) window.clearTimeout(timeoutId);
    };
    const onMessage = (event: MessageEvent) => {
      if (!isTrustedPluginParentEvent(event)) {
        return;
      }
      const data = event.data as Partial<PluginMessage> | undefined;
      if (!data || data.source !== PLUGIN_MESSAGE_SOURCE || data.type !== 'sync-result') {
        return;
      }
      const result = data as { text?: unknown; operationId?: unknown; status?: unknown };
      if (
        result.operationId !== operationId
        && (result.operationId || activePluginCapabilities.has('profile-sync-scopes-v1'))
      ) return;
      const text = result.text;
      cleanup();
      if (result.status === 'error') {
        reject(new Error(typeof text === 'string' ? text : undefined));
      } else {
        resolve({ message: typeof text === 'string' ? text : undefined });
      }
    };

    window.addEventListener('message', onMessage);
    timeoutId = window.setTimeout(() => {
      cleanup();
      reject(new Error());
    }, 120_000);
    postToPlugin({
      source: PLUGIN_MESSAGE_SOURCE,
      type: 'sync',
      scope,
      operationId,
    });
  });
}

/**
 * Подписка на команду выхода от тулбара шелла (кнопка рядом с ником): шелл шлёт
 * do-logout вниз в iframe, SPA вызывает свой logout. Возвращает функцию отписки.
 */
export function subscribeToPluginLogout(onLogout: () => void): () => void {
  const handler = (event: MessageEvent) => {
    if (!isTrustedPluginParentEvent(event)) {
      return;
    }
    const data = event.data as Partial<PluginMessage> | undefined;
    if (!data || data.source !== PLUGIN_MESSAGE_SOURCE || data.type !== 'do-logout') {
      return;
    }
    onLogout();
  };
  window.addEventListener('message', handler);
  return () => window.removeEventListener('message', handler);
}

/**
 * Импортировать пресет в OrcaSlicer через плагин: шелл → Python → data_dir.
 * В сообщение попадает только короткоживущая plugin capability, а не браузерная
 * account session.
 */
export function importPresetToPlugin(presetId: number): void {
  postToPlugin({
    source: PLUGIN_MESSAGE_SOURCE,
    type: 'import-preset',
    presetId,
    token: activePluginToken ?? '',
  });
}

/** Ask the current plugin shell which optional actions it actually supports. */
export function requestPluginCapabilities(): void {
  postToPlugin({
    source: PLUGIN_MESSAGE_SOURCE,
    type: 'plugin-capabilities-request',
  });
}

/**
 * Capability negotiation keeps newer site actions hidden in older installed
 * plugin versions instead of rendering a button that the old shell ignores.
 */
export function subscribeToPluginCapabilities(
  onCapabilities: (capabilities: ReadonlySet<string>) => void,
): () => void {
  const handler = (event: MessageEvent) => {
    if (!isTrustedPluginParentEvent(event)) {
      return;
    }
    const data = event.data as Partial<PluginMessage> | undefined;
    if (!data || data.source !== PLUGIN_MESSAGE_SOURCE || data.type !== 'plugin-capabilities') {
      return;
    }
    const capabilities = (data as { capabilities?: unknown }).capabilities;
    if (!Array.isArray(capabilities)) {
      return;
    }
    activePluginCapabilities = new Set(
      capabilities.filter((item): item is string => typeof item === 'string'),
    );
    onCapabilities(new Set(activePluginCapabilities));
  };
  window.addEventListener('message', handler);
  if (activePluginCapabilities.size > 0) {
    onCapabilities(new Set(activePluginCapabilities));
  }
  return () => window.removeEventListener('message', handler);
}

/**
 * Явно установить в OrcaSlicer управляемые копии конфигураций выбранного
 * физического принтера. Автоматическая синхронизация machine/process-профилей
 * остаётся только исходящей; этот pull запускается исключительно пользователем.
 */
function setPrinterBundleInstalledInPlugin(
  physicalPrinterId: number,
  installed: boolean,
): Promise<{ message?: string }> {
  const requestId = pluginRequestId('printer-bundle');
  return new Promise((resolve, reject) => {
    let timeoutId: number | null = null;
    const cleanup = () => {
      window.removeEventListener('message', onMessage);
      if (timeoutId !== null) window.clearTimeout(timeoutId);
    };
    const onMessage = (event: MessageEvent) => {
      if (!isTrustedPluginParentEvent(event)) return;
      const data = event.data as Partial<PluginMessage> | undefined;
      const dedicatedResult = activePluginCapabilities.has('printer-bundle-result-v1');
      if (
        !data
        || data.source !== PLUGIN_MESSAGE_SOURCE
        || (dedicatedResult
          ? data.type !== 'printer-bundle-result'
          : data.type !== 'sync-result')
      ) {
        return;
      }
      const payload = data as { requestId?: unknown; text?: unknown; status?: unknown };
      if (dedicatedResult && payload.requestId !== requestId) return;
      cleanup();
      const message = typeof payload.text === 'string' ? payload.text : undefined;
      if (payload.status === 'error') reject(new Error(message));
      else resolve({ message });
    };
    window.addEventListener('message', onMessage);
    timeoutId = window.setTimeout(() => {
      cleanup();
      reject(new Error());
    }, 120_000);
    postToPlugin({
      source: PLUGIN_MESSAGE_SOURCE,
      type: installed ? 'install-printer-bundle' : 'remove-printer-bundle',
      requestId,
      physicalPrinterId,
      token: activePluginToken ?? '',
    });
  });
}

export function installPrinterBundleInPlugin(
  physicalPrinterId: number,
): Promise<{ message?: string }> {
  return setPrinterBundleInstalledInPlugin(physicalPrinterId, true);
}

export function removePrinterBundleFromPlugin(
  physicalPrinterId: number,
): Promise<{ message?: string }> {
  return setPrinterBundleInstalledInPlugin(physicalPrinterId, false);
}

export function requestInstalledPrinterBundles(
  physicalPrinterIds: number[],
): Promise<ReadonlySet<number>> {
  const requestId = pluginRequestId('printer-bundle-status');
  return new Promise((resolve, reject) => {
    let timeoutId: number | null = null;
    const cleanup = () => {
      window.removeEventListener('message', onMessage);
      if (timeoutId !== null) window.clearTimeout(timeoutId);
    };
    const onMessage = (event: MessageEvent) => {
      if (!isTrustedPluginParentEvent(event)) return;
      const data = event.data as Partial<PluginMessage> | undefined;
      if (
        !data
        || data.source !== PLUGIN_MESSAGE_SOURCE
        || data.type !== 'printer-bundle-status-result'
      ) {
        return;
      }
      const payload = data as {
        requestId?: unknown;
        status?: unknown;
        installedPrinterIds?: unknown;
      };
      if (payload.requestId !== requestId) return;
      cleanup();
      if (payload.status === 'error') {
        reject(new Error());
        return;
      }
      const ids = Array.isArray(payload.installedPrinterIds)
        ? payload.installedPrinterIds.filter(
          (value): value is number =>
            typeof value === 'number' && Number.isInteger(value) && value > 0,
        )
        : [];
      resolve(new Set(ids));
    };
    window.addEventListener('message', onMessage);
    timeoutId = window.setTimeout(() => {
      cleanup();
      reject(new Error());
    }, 120_000);
    postToPlugin({
      source: PLUGIN_MESSAGE_SOURCE,
      type: 'printer-bundle-status',
      requestId,
      physicalPrinterIds: Array.from(new Set(physicalPrinterIds)),
      token: activePluginToken ?? '',
    });
  });
}

/**
 * Open the plugin-owned Bambu LAN form. The site sends FilamentHub IDs, the
 * one-time pairing code and an optional opaque local discovery reference. IP,
 * serial and access code stay in the host-owned local dialog.
 */
export interface LocalPrinterSetupState {
  open: boolean;
  provider: 'bambu' | 'moonraker';
  physicalPrinterId?: number;
  materialSystemId?: number;
  outcome?: 'saved' | 'cancelled' | 'removed';
}

/** Local credential dialogs expose only their lifecycle, never their fields. */
export function subscribeToLocalPrinterSetup(
  onState: (state: LocalPrinterSetupState) => void,
): () => void {
  const handler = (event: MessageEvent) => {
    if (!isTrustedPluginParentEvent(event)) return;
    const data = event.data;
    if (!data || data.source !== PLUGIN_MESSAGE_SOURCE
      || data.type !== 'local-printer-setup-state' || typeof data.open !== 'boolean'
      || !['bambu', 'moonraker'].includes(data.provider)) return;
    if (data.provider === 'bambu' && (
      !Number.isSafeInteger(data.physicalPrinterId) || data.physicalPrinterId < 1
      || !Number.isSafeInteger(data.materialSystemId) || data.materialSystemId < 1
    )) return;
    onState({
      open: data.open,
      provider: data.provider,
      ...(data.provider === 'bambu' ? {
        physicalPrinterId: data.physicalPrinterId,
        materialSystemId: data.materialSystemId,
      } : {}),
      ...(!data.open && ['saved', 'cancelled', 'removed'].includes(data.outcome)
        ? { outcome: data.outcome } : {}),
    });
  };
  window.addEventListener('message', handler);
  return () => window.removeEventListener('message', handler);
}

export function configureBambuBridgeInPlugin(
  physicalPrinterId: number,
  materialSystemId: number,
  printerName: string,
  pairingCode: string,
  connectionRef?: string,
): void {
  postToPlugin({
    source: PLUGIN_MESSAGE_SOURCE,
    type: 'configure-bambu',
    physicalPrinterId,
    materialSystemId,
    printerName,
    pairingCode,
    ...(connectionRef ? { connectionRef } : {}),
  });
}

/**
 * Remove the matching local Bambu binding when a material system is deleted
 * from the shared web UI inside OrcaSlicer. Outside the plugin this is a no-op;
 * the running bridge will receive 401 for the deleted server credential and
 * remove the same local binding on its next contact.
 */
export function removeBambuBridgeInPlugin(physicalPrinterId: number): void {
  if (!isPluginEmbed()) return;
  postToPlugin({
    source: PLUGIN_MESSAGE_SOURCE,
    type: 'remove-bambu-local',
    physicalPrinterId,
  });
}

export interface BambuMaterialChange {
  slot: number;
  presetId: number;
  presetName: string;
  currentMaterial: string | null;
  currentColor: string | null;
  targetMaterial: string;
  targetColor: string;
}

export interface BambuMaterialUnresolved {
  slot: number;
  reason: 'preset_required' | 'slot_not_found' | 'slot_empty' | 'rfid_managed' | 'preset_not_loaded';
}

export interface BambuExpectedAssignment {
  slot: number;
  preset_id: number | null;
  spool_id: number | null;
  source_ts: string | null;
}

export interface BambuMaterialActionResult {
  ok: boolean;
  operation: 'preview' | 'apply';
  code?: string | null;
  physicalPrinterId: number;
  materialSystemId: number;
  printState?: string | null;
  changes?: BambuMaterialChange[];
  unresolved?: BambuMaterialUnresolved[];
  desiredAssignments?: BambuExpectedAssignment[];
  remainingChanges?: BambuMaterialChange[];
  applied?: boolean;
}

export interface MaterialAssignmentCommit {
  materialSlotId: number;
  providerIndex: number;
  assignmentRevision: number;
  desired: {
    presetId: number | null;
    spoolId: number | null;
    sourceTs: string | null;
  } | null;
}

export interface ImmediateMaterialResult {
  ok: boolean;
  operation: 'assign' | 'refresh';
  code?: string | null;
  physicalPrinterId: number;
  materialSystemId: number;
  applied?: boolean;
  observationUploaded?: boolean;
}

function requestImmediateMaterialOperation(
  provider: 'bambu' | 'happy-hare',
  operation: 'assign' | 'refresh',
  physicalPrinterId: number,
  materialSystemId: number,
  commit?: MaterialAssignmentCommit,
): Promise<ImmediateMaterialResult> {
  const capability = operation === 'assign'
    ? 'material-assignment-v1'
    : 'material-observation-refresh-v1';
  if (!isPluginEmbed() || !activePluginCapabilities.has(capability)) {
    return Promise.reject(new Error(`${capability} unavailable`));
  }
  const requestId = pluginRequestId(`${provider}-material-${operation}`);
  const resultType = provider === 'bambu' ? 'bambu-material-result' : 'happy-hare-result';

  return new Promise((resolve, reject) => {
    let timeoutId: number | null = null;
    const cleanup = () => {
      window.removeEventListener('message', onMessage);
      if (timeoutId !== null) window.clearTimeout(timeoutId);
    };
    const onMessage = (event: MessageEvent) => {
      if (!isTrustedPluginParentEvent(event)) return;
      const data = event.data as Partial<PluginMessage> | undefined;
      if (!data || data.source !== PLUGIN_MESSAGE_SOURCE || data.type !== resultType) return;
      if ((data as { requestId?: unknown }).requestId !== requestId) return;
      const result = (data as { result?: unknown }).result;
      cleanup();
      const value = result as Partial<ImmediateMaterialResult> | null;
      if (
        !value
        || typeof value !== 'object'
        || typeof value.ok !== 'boolean'
        || value.operation !== operation
        || value.physicalPrinterId !== physicalPrinterId
        || value.materialSystemId !== materialSystemId
        || (value.code !== undefined && value.code !== null && typeof value.code !== 'string')
        || (value.applied !== undefined && typeof value.applied !== 'boolean')
        || (
          value.observationUploaded !== undefined
          && typeof value.observationUploaded !== 'boolean'
        )
      ) {
        reject(new Error('invalid material operation result'));
        return;
      }
      resolve(value as ImmediateMaterialResult);
    };
    window.addEventListener('message', onMessage);
    timeoutId = window.setTimeout(() => {
      cleanup();
      reject(new Error('material operation timeout'));
    }, 45_000);
    postToPlugin({
      source: PLUGIN_MESSAGE_SOURCE,
      type: `${provider}-material-${operation}`,
      requestId,
      physicalPrinterId,
      materialSystemId,
      ...(commit ? { commit } : {}),
    });
  });
}

export function requestBambuSlotAssignment(
  physicalPrinterId: number,
  materialSystemId: number,
  commit: MaterialAssignmentCommit,
): Promise<ImmediateMaterialResult> {
  return requestImmediateMaterialOperation(
    'bambu', 'assign', physicalPrinterId, materialSystemId, commit,
  );
}

export function requestBambuObservationRefresh(
  physicalPrinterId: number,
  materialSystemId: number,
): Promise<ImmediateMaterialResult> {
  return requestImmediateMaterialOperation(
    'bambu', 'refresh', physicalPrinterId, materialSystemId,
  );
}

export function requestHappyHareSlotAssignment(
  physicalPrinterId: number,
  materialSystemId: number,
  commit: MaterialAssignmentCommit,
): Promise<ImmediateMaterialResult> {
  return requestImmediateMaterialOperation(
    'happy-hare', 'assign', physicalPrinterId, materialSystemId, commit,
  );
}

export function requestHappyHareObservationRefresh(
  physicalPrinterId: number,
  materialSystemId: number,
): Promise<ImmediateMaterialResult> {
  return requestImmediateMaterialOperation(
    'happy-hare', 'refresh', physicalPrinterId, materialSystemId,
  );
}

/**
 * Preview or explicitly apply saved FilamentHub material assignments to a
 * paired Bambu printer. The page sends only owned entity IDs and the preview
 * version; LAN credentials and the vendor MQTT command remain in Python.
 */
export function requestBambuMaterialAction(
  operation: 'preview' | 'apply',
  physicalPrinterId: number,
  materialSystemId: number,
  expectedDesiredAssignments?: BambuExpectedAssignment[],
): Promise<BambuMaterialActionResult> {
  if (!isPluginEmbed() || !activePluginCapabilities.has('bambu-material-write')) {
    return Promise.reject(new Error('bambu-material-write unavailable'));
  }
  const requestId = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `bambu-${Date.now()}-${Math.random().toString(16).slice(2)}`;

  return new Promise((resolve, reject) => {
    let timeoutId: number | null = null;
    const cleanup = () => {
      window.removeEventListener('message', onMessage);
      if (timeoutId !== null) window.clearTimeout(timeoutId);
    };
    const onMessage = (event: MessageEvent) => {
      if (!isTrustedPluginParentEvent(event)) return;
      const data = event.data as Partial<PluginMessage> | undefined;
      if (!data || data.source !== PLUGIN_MESSAGE_SOURCE || data.type !== 'bambu-material-result') {
        return;
      }
      if ((data as { requestId?: unknown }).requestId !== requestId) return;
      const result = (data as { result?: unknown }).result;
      cleanup();
      if (!result || typeof result !== 'object') {
        reject(new Error('invalid Bambu material result'));
        return;
      }
      resolve(result as BambuMaterialActionResult);
    };
    window.addEventListener('message', onMessage);
    timeoutId = window.setTimeout(() => {
      cleanup();
      reject(new Error('Bambu material request timeout'));
    }, 90_000);
    postToPlugin({
      source: PLUGIN_MESSAGE_SOURCE,
      type: operation === 'apply' ? 'bambu-material-apply' : 'bambu-material-preview',
      requestId,
      physicalPrinterId,
      materialSystemId,
      ...(expectedDesiredAssignments ? { expectedDesiredAssignments } : {}),
    });
  });
}

export interface HappyHareAssignmentChange {
  gate: number;
  actualSpoolId: number | null;
  desiredSpoolId: number | null;
}

export interface PrinterSetupCandidate {
  connectionRef: string;
  label: string;
  physicalPrinterId: number | null;
  provider?: 'bambu' | 'moonraker' | 'octoprint';
  printerModel?: string;
  source?: 'network' | 'profile' | 'saved';
}

export interface PrinterSetupResult {
  ok: boolean;
  code?: string;
  candidates?: PrinterSetupCandidate[];
  discoveryComplete?: boolean;
  probeId?: string;
  connection?: PrinterSetupConnection;
  provider?: 'happy_hare' | 'manual';
  gateCount?: number | null;
  printerHostname?: string | null;
  spoolmanSupport?: string | null;
  observed?: boolean;
  inventoryLinked?: boolean;
}

/** The host-owned local dialog owns manual LAN credentials; this request never contains them. */
export function requestPrinterSetup(
  operation: 'list' | 'probe' | 'activate' | 'manual',
  payload: {
    connectionRef?: string;
    probeId?: string;
    physicalPrinterId?: number;
    copy?: Record<string, string>;
  } = {},
): Promise<PrinterSetupResult> {
  if (!isPluginEmbed() || !activePluginCapabilities.has('printer-setup-v1')) {
    return Promise.reject(new Error('printer setup unavailable'));
  }
  const requestId = pluginRequestId('printer-setup');
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      window.removeEventListener('message', onMessage);
      window.clearTimeout(timer);
    };
    const onMessage = (event: MessageEvent) => {
      if (!isTrustedPluginParentEvent(event)) return;
      const data = event.data;
      if (data?.source !== PLUGIN_MESSAGE_SOURCE || data.type !== 'printer-setup-result'
          || data.requestId !== requestId) return;
      cleanup();
      if (typeof data.result?.ok !== 'boolean') reject(new Error('invalid setup result'));
      else resolve(data.result as PrinterSetupResult);
    };
    const timer = window.setTimeout(() => {
      cleanup();
      reject(new Error('printer setup timeout'));
    }, operation === 'manual' || operation === 'probe' ? 600_000 : 90_000);
    window.addEventListener('message', onMessage);
    postToPlugin({ source: PLUGIN_MESSAGE_SOURCE,
      type: operation === 'manual' ? 'printer-setup-manual' : 'printer-setup',
      ...(operation === 'list' && activePluginCapabilities.has('printer-discovery-v1') ? { discovery: true } : {}),
      requestId, operation, ...payload });
  });
}

export interface HappyHareImportChange {
  gate: number;
  proposedSpoolId: number;
  desiredSpoolId: number | null;
  source: 'provider' | 'last_known';
}

export interface HappyHareUnresolvedGate {
  gate: number;
  reason: 'spool_unavailable' | 'identity_unknown' | 'ambiguous_last_known' | 'duplicate_spool';
}

export interface HappyHareExpectedAssignment {
  gate: number;
  spool_id: number | null;
}

export interface HappyHareActionResult {
  ok: boolean;
  operation: 'preview' | 'apply' | 'adopt';
  code?: string | null;
  physicalPrinterId: number;
  materialSystemId: number;
  gateCount?: number;
  printerHostname?: string | null;
  spoolmanSupport?: string | null;
  printState?: string | null;
  changes?: HappyHareAssignmentChange[];
  importChanges?: HappyHareImportChange[];
  unresolved?: HappyHareUnresolvedGate[];
  desiredAssignments?: HappyHareExpectedAssignment[];
  remainingChanges?: HappyHareAssignmentChange[];
  applied?: boolean;
  adopted?: boolean;
  adoptedGates?: number;
}

/**
 * Ask the local Orca plugin to inspect Happy Hare or apply the already saved
 * FilamentHub assignments. The page sends only owned server IDs and an
 * allowlisted operation; the Moonraker address, key and G-code stay in Python.
 */
export function requestHappyHareAction(
  operation: 'preview' | 'apply' | 'adopt',
  physicalPrinterId: number,
  materialSystemId: number,
  expectedDesiredAssignments?: HappyHareExpectedAssignment[],
): Promise<HappyHareActionResult> {
  if (!isPluginEmbed() || !activePluginCapabilities.has('happy-hare-moonraker')) {
    return Promise.reject(new Error('happy-hare-moonraker unavailable'));
  }
  const requestId = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `hh-${Date.now()}-${Math.random().toString(16).slice(2)}`;

  return new Promise((resolve, reject) => {
    let timeoutId: number | null = null;
    const cleanup = () => {
      window.removeEventListener('message', onMessage);
      if (timeoutId !== null) window.clearTimeout(timeoutId);
    };
    const onMessage = (event: MessageEvent) => {
      if (!isTrustedPluginParentEvent(event)) return;
      const data = event.data as Partial<PluginMessage> | undefined;
      if (!data || data.source !== PLUGIN_MESSAGE_SOURCE || data.type !== 'happy-hare-result') {
        return;
      }
      if ((data as { requestId?: unknown }).requestId !== requestId) return;
      const result = (data as { result?: unknown }).result;
      cleanup();
      if (!result || typeof result !== 'object') {
        reject(new Error('invalid happy-hare result'));
        return;
      }
      resolve(result as HappyHareActionResult);
    };
    window.addEventListener('message', onMessage);
    timeoutId = window.setTimeout(() => {
      cleanup();
      reject(new Error('happy-hare request timeout'));
    }, 30_000);
    postToPlugin({
      source: PLUGIN_MESSAGE_SOURCE,
      type: operation === 'apply'
        ? 'happy-hare-apply'
        : operation === 'adopt'
          ? 'happy-hare-adopt'
          : 'happy-hare-preview',
      requestId,
      physicalPrinterId,
      materialSystemId,
      ...(expectedDesiredAssignments ? { expectedDesiredAssignments } : {}),
    });
  });
}

export interface PrinterRecoveryScope {
  server_origin: string;
  owner_user_id: number;
  source_instance_id: string;
  account_id: string;
}

export interface PrinterRecoveryLocalArtifact {
  artifactKey: string;
  kind: 'machine' | 'process';
  profileId: number | null;
  name: string;
  contentHash: string | null;
  ownership: 'current' | 'foreign' | 'untracked';
  healthy: boolean;
}

export interface PrinterRecoveryLocalState {
  context: PrinterRecoveryScope;
  artifacts: PrinterRecoveryLocalArtifact[];
  originalObservations?: Partial<Record<'machine' | 'process', {
    complete: boolean;
    presentLocalProfileIds: string[];
  }>>;
}

export interface PrinterRecoveryActionResult {
  message?: string;
  status: 'success' | 'warning';
  results: Array<{
    artifactKey?: string;
    kind: 'machine' | 'process';
    profileId: number | null;
    name?: string;
    state: string;
  }>;
}

function requestPrinterRecoveryMessage<T>(
  messageType: 'printer-recovery-state' | 'apply-printer-recovery' | 'remove-printer-recovery',
  resultType: 'printer-recovery-state-result' | 'printer-recovery-action-result',
  payload: Record<string, unknown>,
): Promise<T> {
  const requestId = pluginRequestId('printer-recovery');
  return new Promise((resolve, reject) => {
    let timeoutId: number | null = null;
    const cleanup = () => {
      window.removeEventListener('message', onMessage);
      if (timeoutId !== null) window.clearTimeout(timeoutId);
    };
    const onMessage = (event: MessageEvent) => {
      if (!isTrustedPluginParentEvent(event)) return;
      const data = event.data as Partial<PluginMessage> | undefined;
      if (
        !data
        || data.source !== PLUGIN_MESSAGE_SOURCE
        || data.type !== resultType
        || data.requestId !== requestId
      ) {
        return;
      }
      cleanup();
      const message = typeof data.message === 'string' ? data.message : undefined;
      if (data.status === 'error') {
        reject(new Error(message));
        return;
      }
      resolve(data as T);
    };
    window.addEventListener('message', onMessage);
    timeoutId = window.setTimeout(() => {
      cleanup();
      reject(new Error());
    }, 120_000);
    postToPlugin({
      source: PLUGIN_MESSAGE_SOURCE,
      type: messageType,
      requestId,
      ...payload,
    });
  });
}

export async function requestPrinterRecoveryState(
  ownerUserId: number,
): Promise<PrinterRecoveryLocalState> {
  const response = await requestPrinterRecoveryMessage<{
    localState?: PrinterRecoveryLocalState;
  }>('printer-recovery-state', 'printer-recovery-state-result', { ownerUserId });
  if (!response.localState) throw new Error();
  return response.localState;
}

export function applyPrinterRecoveryInPlugin(
  bundle: Record<string, unknown>,
): Promise<PrinterRecoveryActionResult> {
  return requestPrinterRecoveryMessage<PrinterRecoveryActionResult>(
    'apply-printer-recovery',
    'printer-recovery-action-result',
    { bundle },
  );
}

export function removePrinterRecoveryFromPlugin(
  artifactKeys: string[],
): Promise<PrinterRecoveryActionResult> {
  return requestPrinterRecoveryMessage<PrinterRecoveryActionResult>(
    'remove-printer-recovery',
    'printer-recovery-action-result',
    { artifactKeys },
  );
}

/**
 * Попросить плагин разобрать нарезку: файл лежит на диске у человека, страница
 * открыть его не может, поэтому называет ключ, а Python отправляет G-code в наш
 * же разбор и возвращает результат — тот же, что при ручной загрузке.
 */
export function requestSliceParse(sourceKey: string, fileName: string): void {
  postToPlugin({ source: PLUGIN_MESSAGE_SOURCE, type: 'parse-slice', sourceKey, fileName });
}

export interface PluginSliceParseResult {
  parsed?: unknown;
  error?: string;
}

/**
 * Спросить плагин, какие из перечисленных нарезок ещё можно посчитать: список на
 * сайте живёт дольше файлов за ним.
 */
export function requestSliceKeyCheck(keys: string[]): void {
  if (keys.length === 0) {
    return;
  }
  postToPlugin({ source: PLUGIN_MESSAGE_SOURCE, type: 'check-slices', keys });
}

export interface PluginSliceHookState {
  /** Стоит ли FilamentHub в поле «Slicing Pipeline Plugin» текущего профиля печати. */
  enabled: boolean;
  /** Имя этого профиля печати. */
  preset: string;
}

export interface PluginSliceStatus {
  keys: string[];
  hook: PluginSliceHookState | null;
}

/** Подписка на ответ плагина: живые нарезки и состояние конвейера нарезки. */
export function subscribeToPluginSliceKeys(
  onStatus: (status: PluginSliceStatus) => void,
): () => void {
  const handler = (event: MessageEvent) => {
    if (!isTrustedPluginParentEvent(event)) {
      return;
    }
    const data = event.data as Partial<PluginMessage> | undefined;
    if (!data || data.source !== PLUGIN_MESSAGE_SOURCE || data.type !== 'slices-alive') {
      return;
    }
    const keys = (data as { keys?: unknown }).keys;
    const hook = (data as { hook?: unknown }).hook;
    if (Array.isArray(keys)) {
      onStatus({
        keys: keys.filter((key): key is string => typeof key === 'string'),
        hook:
          hook && typeof hook === 'object' && typeof (hook as PluginSliceHookState).enabled === 'boolean'
            ? {
                enabled: (hook as PluginSliceHookState).enabled,
                preset: String((hook as PluginSliceHookState).preset ?? ''),
              }
            : null,
      });
    }
  };
  window.addEventListener('message', handler);
  return () => window.removeEventListener('message', handler);
}

/** Подписка на разобранную нарезку от шелла (ответ на parse-slice). */
export function subscribeToPluginSliceParse(
  onResult: (result: PluginSliceParseResult) => void,
): () => void {
  const handler = (event: MessageEvent) => {
    if (!isTrustedPluginParentEvent(event)) {
      return;
    }
    const data = event.data as Partial<PluginMessage> | undefined;
    if (!data || data.source !== PLUGIN_MESSAGE_SOURCE || data.type !== 'parsed-slice') {
      return;
    }
    const result = (data as { result?: unknown }).result;
    if (result && typeof result === 'object') {
      onResult(result as PluginSliceParseResult);
    } else {
      onResult({ error: 'empty' });
    }
  };
  window.addEventListener('message', handler);
  return () => window.removeEventListener('message', handler);
}

/**
 * Запустить вход через Google/Yandex во внешнем системном браузере. Внутри
 * встроенного WebView провайдеры отдают 403 (disallowed_useragent) / «refused to
 * connect», поэтому SPA создаёт серверный одноразовый handoff и просит host
 * открыть его безопасный путь в системном браузере. Этот же SPA опрашивает
 * сервер по отдельному секрету, который никогда не передаётся host.
 */
export async function startPluginOAuth(
  provider: 'google' | 'yandex',
  signal?: AbortSignal,
): Promise<PluginAuthRestore> {
  if (!isPluginEmbed()) throw new Error('plugin OAuth requires an embedded host');
  const { authAPI } = await import('../api/client');
  const flow = await authAPI.createPluginOAuthFlow(provider, signal);
  if (
    !validPluginOAuthCredential(flow.flow_id)
    || !validPluginOAuthCredential(flow.poll_secret)
  ) {
    throw new Error('invalid plugin OAuth flow');
  }
  const browserUrl = new URL(flow.browser_url, window.location.origin);
  const expectedPath = `/oauth/plugin-start/${provider}`;
  const queryKeys = Array.from(browserUrl.searchParams.keys());
  if (
    browserUrl.origin !== window.location.origin
    || browserUrl.pathname !== expectedPath
    || browserUrl.hash
    || queryKeys.length !== 1
    || queryKeys[0] !== 'flow'
    || browserUrl.searchParams.get('flow') !== flow.flow_id
  ) {
    throw new Error('invalid plugin OAuth browser URL');
  }
  const requestId = pluginRequestId('oauth');
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener('abort', abort, { once: true });

  let unsubscribeLegacy: () => void = () => {};
  let removeOpenListener: () => void = () => {};
  const legacyResult = new Promise<PluginAuthRestore>((resolve) => {
    unsubscribeLegacy = subscribeToPluginAuthRestore(resolve);
  });
  const openFailure = new Promise<PluginAuthRestore>((_resolve, reject) => {
    const handler = (event: MessageEvent) => {
      if (!isTrustedPluginParentEvent(event)) return;
      const data = event.data as Partial<PluginMessage> | undefined;
      if (
        data?.source !== PLUGIN_MESSAGE_SOURCE
        || data.type !== 'oauth-browser-opened'
        || data.requestId !== requestId
      ) return;
      if (data.opened !== true) reject(new Error('system browser could not be opened'));
    };
    window.addEventListener('message', handler);
    removeOpenListener = () => window.removeEventListener('message', handler);
  });

  const pollResult = (async (): Promise<PluginAuthRestore> => {
    const deadline = Date.now() + Math.max(1, Math.min(flow.expires_in, 600)) * 1000;
    let delayMs = Math.max(1, Math.min(flow.interval, 10)) * 1000;
    while (Date.now() < deadline) {
      if (controller.signal.aborted) throw new DOMException('Aborted', 'AbortError');
      const result = await authAPI.pollPluginOAuthFlow(
        flow.flow_id,
        flow.poll_secret,
        controller.signal,
      );
      if (result.status === 'complete') {
        if (!result.access_token) throw new Error('plugin OAuth returned no access token');
        return {
          accessToken: result.access_token,
          refreshToken: result.refresh_token ?? '',
        };
      }
      const remainingMs = Math.max(0, result.expires_in * 1000);
      if (remainingMs === 0) break;
      await new Promise<void>((resolve, reject) => {
        let timeoutId = 0;
        const onAbort = () => {
          window.clearTimeout(timeoutId);
          reject(new DOMException('Aborted', 'AbortError'));
        };
        const done = () => {
          controller.signal.removeEventListener('abort', onAbort);
          resolve();
        };
        timeoutId = window.setTimeout(done, Math.min(delayMs, remainingMs));
        controller.signal.addEventListener('abort', onAbort, { once: true });
      });
      delayMs = Math.min(delayMs * 1.25, 5000);
    }
    throw new Error('plugin OAuth flow expired');
  })();

  postToPlugin({
    source: PLUGIN_MESSAGE_SOURCE,
    type: 'open-oauth',
    provider,
    path: `${expectedPath}?flow=${encodeURIComponent(flow.flow_id)}`,
    requestId,
  });
  try {
    return await Promise.race([pollResult, legacyResult, openFailure]);
  } finally {
    controller.abort();
    signal?.removeEventListener('abort', abort);
    unsubscribeLegacy();
    removeOpenListener();
  }
}

/**
 * Открыть страницу сайта в системном браузере, когда каталог живёт внутри панели
 * плагина: второй вкладке там появиться негде, а увести единственный фрейм со
 * страницы вики значит потерять место, на котором человек читает.
 *
 * Плагину уходит только путь — origin подставляет он сам, поэтому встроенная
 * страница не может превратить это в «открой любой адрес». Возвращает false,
 * если мы не в плагине или установленная версия такого ещё не умеет: вызывающий
 * код тогда оставляет обычный переход по ссылке.
 */
export function openSitePathInBrowser(path: string): boolean {
  if (!isPluginEmbed() || !activePluginCapabilities.has('open-external')) {
    return false;
  }
  if (!path.startsWith('/') || path.startsWith('//')) {
    return false;
  }
  postToPlugin({ source: PLUGIN_MESSAGE_SOURCE, type: 'open-external', path });
  return true;
}

export interface PluginAuthRestore {
  accessToken: string;
  refreshToken: string;
}

/**
 * Подписка на доставку account-сессии от старого host bridge. Серверный OAuth
 * handoff актуального прямого SPA завершается внутри startPluginOAuth.
 */
export function subscribeToPluginAuthRestore(
  onRestore: (tokens: PluginAuthRestore) => void,
): () => void {
  const handler = (event: MessageEvent) => {
    if (!isTrustedPluginParentEvent(event)) {
      return;
    }
    const data = event.data as Partial<PluginMessage> | undefined;
    if (!data || data.source !== PLUGIN_MESSAGE_SOURCE || data.type !== 'auth-restore') {
      return;
    }
    const accessToken = (data as { accessToken?: unknown }).accessToken;
    const refreshToken = (data as { refreshToken?: unknown }).refreshToken;
    if (typeof accessToken === 'string' && accessToken) {
      onRestore({
        accessToken,
        refreshToken: typeof refreshToken === 'string' ? refreshToken : '',
      });
    }
  };
  window.addEventListener('message', handler);
  return () => window.removeEventListener('message', handler);
}
