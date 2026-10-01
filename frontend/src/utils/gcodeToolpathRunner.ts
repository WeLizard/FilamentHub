// Runs the toolpath reader in a Web Worker so that a minute of line-walking over a
// 60 MB file never blocks the page, and so that cancelling stops it at once.

export type ToolpathWorkerMessage =
  | { type: 'progress'; fraction: number }
  | { type: 'result'; toolpath: string }
  | { type: 'failed'; message: string };

export class GcodeToolpathUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'GcodeToolpathUnavailableError';
  }
}

export interface GcodeToolpathRun {
  signal?: AbortSignal;
  onProgress?: (fraction: number) => void;
  createWorker?: () => Worker;
}

const createToolpathWorker = (): Worker => {
  if (typeof Worker === 'undefined') {
    throw new GcodeToolpathUnavailableError('worker_unsupported');
  }
  return new Worker(new URL('./gcodeToolpath.worker.ts', import.meta.url), { type: 'module' });
};

/**
 * The toolpath summary of a file as JSON text. Rejects with an AbortError when
 * cancelled (the worker is terminated) and with any other error when the summary could
 * not be built; the caller then sends the file's summary without it.
 */
export const buildGcodeToolpath = (
  file: File,
  { signal, onProgress, createWorker = createToolpathWorker }: GcodeToolpathRun = {},
): Promise<string> =>
  new Promise<string>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('canceled', 'AbortError'));
      return;
    }

    let worker: Worker;
    try {
      worker = createWorker();
    } catch (error) {
      reject(error);
      return;
    }

    const settle = (outcome: () => void) => {
      signal?.removeEventListener('abort', onAbort);
      worker.terminate();
      outcome();
    };
    const onAbort = () => settle(() => reject(new DOMException('canceled', 'AbortError')));
    signal?.addEventListener('abort', onAbort, { once: true });

    worker.onmessage = (event: MessageEvent<ToolpathWorkerMessage>) => {
      const message = event.data;
      if (message.type === 'progress') {
        onProgress?.(message.fraction);
      } else if (message.type === 'result') {
        settle(() => resolve(message.toolpath));
      } else {
        settle(() => reject(new GcodeToolpathUnavailableError(message.message)));
      }
    };
    worker.onerror = (event) => settle(() => reject(
      new GcodeToolpathUnavailableError(event.message || 'worker_error'),
    ));
    worker.onmessageerror = () => settle(() => reject(
      new GcodeToolpathUnavailableError('worker_message_error'),
    ));

    try {
      worker.postMessage(file);
    } catch (error) {
      settle(() => reject(error));
    }
  });
