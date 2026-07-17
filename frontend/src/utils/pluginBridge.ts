/**
 * Мост между встроенным (iframe) каталогом и Python-плагином OrcaSlicer.
 *
 * Плагин (PR #14530) грузит наш SPA по /embed/catalog в <iframe> внутри окна
 * OrcaSlicer. Действия из каталога (импорт пресета) уходят наверх через
 * window.parent.postMessage; шелл плагина ретранслирует их в Python.
 *
 * Это ОТДЕЛЬНЫЙ путь от форкового моста (window.filamenthub / window.wx) —
 * тот WebView-мост не трогаем, он продолжает работать как раньше.
 */

export const PLUGIN_MESSAGE_SOURCE = 'filamenthub-plugin';

const EMBED_FLAG = 'fh_plugin_embed';

// В iframe плагина sessionStorage недоступен (SecurityError в партиционированном
// контексте), поэтому липкость режима держит модульный флаг: SPA-навигация
// страницу не перезагружает, и он живёт всю iframe-сессию. sessionStorage
// остаётся страховкой на жёсткую перезагрузку в обычном браузере.
let embedSessionFlag = false;
let activePluginToken: string | null = null;

/**
 * Запущен ли каталог во встроенном (плагинном) режиме. Определяем по маршруту
 * /embed и запоминаем на сессию, чтобы режим сохранялся при переходах внутри
 * iframe (например, на страницу материала).
 */
export function isPluginEmbed(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  if (window.location.pathname.startsWith('/embed')) {
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
  if (typeof window === 'undefined' || window.parent === window) {
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

/**
 * Проверка, что URL доставки OAuth-сессии указывает строго на loopback плагина
 * (http://127.0.0.1|localhost). Единственный адресат, которому позволено принять
 * минтованные токены — чтобы поддельная ссылка plugin-start не увела сессию на
 * чужой хост. Применяется и при сохранении, и при чтении хендофа.
 */
export function isLoopbackDeliveryUrl(url: string): boolean {
  return isLoopbackOrigin(url);
}

// Хендоф внешнего OAuth: страница plugin-start кладёт сюда loopback-cb + nonce,
// страница callback их считывает и редиректит браузер на loopback с токенами.
export const PLUGIN_OAUTH_HANDOFF_KEY = 'fh_plugin_oauth_handoff';

export function consumePluginOAuthHandoff(): { cb: string; nonce: string } | null {
  try {
    const raw = sessionStorage.getItem(PLUGIN_OAUTH_HANDOFF_KEY);
    if (!raw) {
      return null;
    }
    sessionStorage.removeItem(PLUGIN_OAUTH_HANDOFF_KEY);
    const parsed = JSON.parse(raw) as { cb?: unknown; nonce?: unknown };
    if (
      typeof parsed.cb === 'string' &&
      typeof parsed.nonce === 'string' &&
      parsed.cb &&
      parsed.nonce &&
      isLoopbackDeliveryUrl(parsed.cb)
    ) {
      return { cb: parsed.cb, nonce: parsed.nonce };
    }
  } catch {
    // Хранилище недоступно или мусор — хендофа нет.
  }
  return null;
}

function isTrustedPluginParentEvent(event: MessageEvent): boolean {
  if (event.source !== window.parent) {
    return false;
  }
  // Trusted parents mirror the /embed frame-ancestors CSP: an opaque `null`
  // origin (file:// WebView shell), our own origin, or the plugin's
  // loopback-served shell (http://127.0.0.1:*), which exists because WebView2
  // SetPage documents get an opaque origin the CSP could never allowlist.
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
 * access/refresh credentials браузера никогда не пересекают iframe boundary.
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

/**
 * Запустить вход через Google/Yandex во внешнем системном браузере. Внутри
 * встроенного WebView провайдеры отдают 403 (disallowed_useragent) / «refused to
 * connect», поэтому Python открывает браузер, а сессия возвращается в плагин по
 * loopback. Здесь мы лишь просим шелл начать флоу.
 */
export function startPluginOAuth(provider: 'google' | 'yandex'): void {
  postToPlugin({ source: PLUGIN_MESSAGE_SOURCE, type: 'open-oauth', provider });
}

export interface PluginAuthRestore {
  accessToken: string;
  refreshToken: string;
}

/**
 * Подписка на доставку account-сессии от шелла: после внешнего OAuth шелл,
 * опросив loopback, шлёт вниз auth-restore с access/refresh токенами. SPA входит
 * ими как при обычном логине. Возвращает функцию отписки.
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
