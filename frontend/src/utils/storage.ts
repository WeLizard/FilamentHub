/**
 * Безопасная обёртка над localStorage с in-memory fallback.
 *
 * В партиционированных контекстах любой доступ к window.localStorage кидает
 * SecurityError — например, наш каталог в <iframe> плагина OrcaSlicer
 * (top-фрейм file://) или приватный режим браузера. Тогда значения живут в
 * памяти до закрытия страницы: для SPA этого достаточно (навигация внутри
 * iframe страницу не перезагружает), а в обычном браузере поведение не
 * меняется — работает настоящий localStorage.
 */

const memory = new Map<string, string>();

export const safeStorage = {
  get(key: string): string | null {
    // Память первична: если запись попала сюда, localStorage недоступен
    // (или отверг запись), и его ответ для этого ключа неактуален.
    if (memory.has(key)) {
      return memory.get(key) ?? null;
    }
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  },

  set(key: string, value: string): void {
    try {
      window.localStorage.setItem(key, value);
      memory.delete(key);
    } catch {
      memory.set(key, value);
    }
  },

  remove(key: string): void {
    memory.delete(key);
    try {
      window.localStorage.removeItem(key);
    } catch {
      // Хранилище недоступно — из памяти уже удалили.
    }
  },
};
