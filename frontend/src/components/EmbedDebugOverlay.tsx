/** Диагностический оверлей для embed-режима (iframe плагина OrcaSlicer):
 *  DevTools в WebView плагина недоступен, поэтому window.onerror /
 *  unhandledrejection выводим на экран. Вне ошибок не рендерится. */

import { useEffect, useState } from 'react';

export function EmbedDebugOverlay() {
  const [entries, setEntries] = useState<string[]>([]);

  useEffect(() => {
    const push = (line: string) => setEntries((prev) => [...prev.slice(-19), line]);
    const describe = (reason: unknown): string => {
      if (reason instanceof Error) {
        return `${reason.name}: ${reason.message}`;
      }
      try {
        return JSON.stringify(reason);
      } catch {
        return String(reason);
      }
    };
    const onError = (event: ErrorEvent) => {
      push(`error: ${event.message} @ ${event.filename}:${event.lineno}:${event.colno}`);
    };
    const onRejection = (event: PromiseRejectionEvent) => {
      push(`unhandledrejection: ${describe(event.reason)}`);
    };
    window.addEventListener('error', onError);
    window.addEventListener('unhandledrejection', onRejection);
    return () => {
      window.removeEventListener('error', onError);
      window.removeEventListener('unhandledrejection', onRejection);
    };
  }, []);

  if (entries.length === 0) return null;

  return (
    <div className="fixed bottom-0 inset-x-0 z-[9999] max-h-40 overflow-y-auto bg-black/85 border-t border-red-500/40 p-2">
      {entries.map((line, i) => (
        <div key={i} className="text-red-300 text-xs font-mono break-all">{line}</div>
      ))}
    </div>
  );
}
