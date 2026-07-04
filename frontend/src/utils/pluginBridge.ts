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

import { getToken } from './auth';

export const PLUGIN_MESSAGE_SOURCE = 'filamenthub-plugin';

const EMBED_FLAG = 'fh_plugin_embed';

/**
 * Запущен ли каталог во встроенном (плагинном) режиме. Определяем по маршруту
 * /embed и запоминаем на сессию, чтобы режим сохранялся при переходах внутри
 * iframe (например, на страницу материала).
 */
export function isPluginEmbed(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  try {
    if (window.location.pathname.startsWith('/embed')) {
      sessionStorage.setItem(EMBED_FLAG, '1');
      return true;
    }
    return sessionStorage.getItem(EMBED_FLAG) === '1';
  } catch {
    return window.location.pathname.startsWith('/embed');
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

/**
 * Импортировать пресет в OrcaSlicer через плагин: шелл → Python → data_dir.
 * Токен нужен, чтобы Python скачал авторизованный экспорт
 * (GET /presets/{id}/export/orcaslicer.json). В iframe пользователь входит на
 * сайте как обычно, поэтому токен берём каноническим getToken().
 */
export function importPresetToPlugin(presetId: number): void {
  postToPlugin({
    source: PLUGIN_MESSAGE_SOURCE,
    type: 'import-preset',
    presetId,
    token: getToken() ?? '',
  });
}
