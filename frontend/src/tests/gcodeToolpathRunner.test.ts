import { describe, expect, it, vi } from 'vitest';

import {
  buildGcodeToolpath,
  GcodeToolpathUnavailableError,
  type ToolpathWorkerMessage,
} from '../utils/gcodeToolpathRunner';

class FakeWorker {
  onmessage: ((event: MessageEvent<ToolpathWorkerMessage>) => void) | null = null;
  onerror: ((event: ErrorEvent) => void) | null = null;
  onmessageerror: (() => void) | null = null;
  postMessage = vi.fn();
  terminate = vi.fn();

  emit(message: ToolpathWorkerMessage) {
    this.onmessage?.({ data: message } as MessageEvent<ToolpathWorkerMessage>);
  }
}

const file = new File(['G1 E1'], 'a.gcode');
const start = (worker: FakeWorker, options: Parameters<typeof buildGcodeToolpath>[1] = {}) =>
  buildGcodeToolpath(file, { createWorker: () => worker as unknown as Worker, ...options });

describe('toolpath worker runner', () => {
  it('hands the file to the worker, relays progress and resolves with the summary', async () => {
    const worker = new FakeWorker();
    const onProgress = vi.fn();

    const promise = start(worker, { onProgress });
    expect(worker.postMessage).toHaveBeenCalledWith(file);
    worker.emit({ type: 'progress', fraction: 0.4 });
    worker.emit({ type: 'result', toolpath: '{"version":1}' });

    await expect(promise).resolves.toBe('{"version":1}');
    expect(onProgress).toHaveBeenCalledWith(0.4);
    expect(worker.terminate).toHaveBeenCalledTimes(1);
  });

  it('terminates the worker the moment it is cancelled', async () => {
    const worker = new FakeWorker();
    const controller = new AbortController();

    const promise = start(worker, { signal: controller.signal });
    controller.abort();

    await expect(promise).rejects.toMatchObject({ name: 'AbortError' });
    expect(worker.terminate).toHaveBeenCalledTimes(1);
    worker.emit({ type: 'result', toolpath: 'late' });
    expect(worker.terminate).toHaveBeenCalledTimes(2);
  });

  it('does not start a worker for a run that is already cancelled', async () => {
    const createWorker = vi.fn();
    const controller = new AbortController();
    controller.abort();

    await expect(buildGcodeToolpath(file, { signal: controller.signal, createWorker }))
      .rejects.toMatchObject({ name: 'AbortError' });
    expect(createWorker).not.toHaveBeenCalled();
  });

  it.each([
    ['a failure the worker reports', (worker: FakeWorker) => worker.emit({ type: 'failed', message: 'toolpath_limit:roles' })],
    ['a crash of the worker', (worker: FakeWorker) => worker.onerror?.({ message: 'boom' } as ErrorEvent)],
    ['a message that cannot be read', (worker: FakeWorker) => worker.onmessageerror?.()],
  ])('rejects, and frees the worker, after %s', async (_label, trigger) => {
    const worker = new FakeWorker();

    const promise = start(worker);
    trigger(worker);

    await expect(promise).rejects.toBeInstanceOf(GcodeToolpathUnavailableError);
    expect(worker.terminate).toHaveBeenCalledTimes(1);
  });

  it('rejects when the browser cannot start a worker or take the file', async () => {
    const refusing = vi.fn(() => {
      throw new GcodeToolpathUnavailableError('worker_unsupported');
    });
    await expect(buildGcodeToolpath(file, { createWorker: refusing }))
      .rejects.toBeInstanceOf(GcodeToolpathUnavailableError);

    const worker = new FakeWorker();
    worker.postMessage.mockImplementation(() => {
      throw new DOMException('not cloneable', 'DataCloneError');
    });
    await expect(start(worker)).rejects.toMatchObject({ name: 'DataCloneError' });
    expect(worker.terminate).toHaveBeenCalledTimes(1);
  });
});
