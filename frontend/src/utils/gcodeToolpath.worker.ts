import { readGcodeToolpath } from './gcodeToolpathReader';
import type { ToolpathWorkerMessage } from './gcodeToolpathRunner';

interface ToolpathWorkerScope {
  onmessage: ((event: MessageEvent<File>) => void) | null;
  postMessage: (message: ToolpathWorkerMessage) => void;
}

const scope = self as unknown as ToolpathWorkerScope;

scope.onmessage = (event) => {
  readGcodeToolpath(event.data, {
    onProgress: (fraction) => scope.postMessage({ type: 'progress', fraction }),
  }).then(
    (toolpath) => scope.postMessage({ type: 'result', toolpath }),
    (error: unknown) => scope.postMessage({
      type: 'failed',
      message: error instanceof Error ? error.message : 'toolpath_failed',
    }),
  );
};
