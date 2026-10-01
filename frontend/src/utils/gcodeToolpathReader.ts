// Streams a sliced file through the toolpath walker in constant memory: nothing larger
// than one chunk of the file is ever held, whatever its size. Browser APIs only, so it
// runs in a worker and in Node alike.

import {
  detectSourceKind,
  GcodeExcerptError,
  listGcodePlateSources,
  requireDecompression,
} from './gcodeExcerpt';
import { serializeToolpath, ToolpathWalker, type ToolpathEvidence } from './gcodeToolpath';

type Bytes = Uint8Array<ArrayBuffer>;

export const GCODE_TOOLPATH_LIMITS = {
  // What the walker may read out of one file or plate, after decompression.
  decompressedBytes: 2 * 1024 * 1024 * 1024,
  // Progress reports closer together than this are not worth a message.
  progressStep: 0.005,
} as const;

export interface GcodeToolpathHooks {
  signal?: AbortSignal;
  /** Fraction (0..1) of the file's stored bytes read so far. */
  onProgress?: (fraction: number) => void;
}

const aborted = () => new DOMException('canceled', 'AbortError');

const throwIfAborted = (signal?: AbortSignal) => {
  if (signal?.aborted) throw aborted();
};

const requireStreams = () => {
  if (
    typeof Blob === 'undefined'
    || typeof Blob.prototype.stream !== 'function'
    || typeof TransformStream === 'undefined'
    || typeof TextDecoder === 'undefined'
  ) {
    throw new GcodeExcerptError('ERR_GCODE_BROWSER_UNSUPPORTED');
  }
};

class Progress {
  private reported = -1;

  constructor(
    private readonly total: number,
    private readonly onProgress?: (fraction: number) => void,
  ) {}

  update(consumed: number): void {
    if (!this.onProgress) return;
    const fraction = this.total > 0 ? Math.min(1, consumed / this.total) : 1;
    if (fraction - this.reported >= GCODE_TOOLPATH_LIMITS.progressStep || (fraction === 1 && this.reported < 1)) {
      this.reported = fraction;
      this.onProgress(fraction);
    }
  }
}

const countingStream = (onBytes: (length: number) => void) =>
  new TransformStream<Bytes, Bytes>({
    transform(chunk, controller) {
      onBytes(chunk.length);
      controller.enqueue(chunk);
    },
  });

/** `expectedBytes` is the size an archive declares; a stream of another size is a lie. */
export const walkGcodeStream = async (
  stream: ReadableStream<Bytes>,
  signal?: AbortSignal,
  expectedBytes?: number,
): Promise<ToolpathEvidence> => {
  const walker = new ToolpathWalker();
  const decoder = new TextDecoder('utf-8');
  const reader = stream.getReader();
  let decompressed = 0;

  try {
    for (;;) {
      throwIfAborted(signal);
      const { done, value } = await reader.read();
      if (done) break;
      decompressed += value.length;
      if (decompressed > GCODE_TOOLPATH_LIMITS.decompressedBytes) {
        throw new GcodeExcerptError('ERR_GCODE_EXCERPT_TOO_LARGE');
      }
      walker.push(decoder.decode(value, { stream: true }));
    }
    walker.push(decoder.decode());
    if (expectedBytes !== undefined && decompressed !== expectedBytes) {
      throw new GcodeExcerptError('ERR_GCODE_EXCERPT_INVALID');
    }
    return walker.finish();
  } catch (error) {
    void reader.cancel().catch(() => undefined);
    throw error;
  }
};

const plainEvidence = async (
  file: File,
  decompress: boolean,
  hooks: GcodeToolpathHooks,
): Promise<ToolpathEvidence> => {
  const progress = new Progress(file.size, hooks.onProgress);
  let consumed = 0;
  const counted = file.stream().pipeThrough(countingStream((length) => {
    consumed += length;
    progress.update(consumed);
  }));
  const stream = decompress ? counted.pipeThrough(requireDecompression('gzip')) : counted;
  const evidence = await walkGcodeStream(stream as ReadableStream<Bytes>, hooks.signal);
  progress.update(file.size);
  return evidence;
};

const platesEvidence = async (
  file: File,
  hooks: GcodeToolpathHooks,
): Promise<Record<string, ToolpathEvidence>> => {
  const sources = await listGcodePlateSources(file, hooks.signal);
  if (sources.length === 0) throw new GcodeExcerptError('ERR_GCODE_EXCERPT_INVALID');

  const progress = new Progress(
    sources.reduce((sum, source) => sum + source.compressedSize, 0),
    hooks.onProgress,
  );
  let consumed = 0;
  const plates: Record<string, ToolpathEvidence> = {};

  for (const source of sources) {
    const counted = (await source.openStored()).pipeThrough(countingStream((length) => {
      consumed += length;
      progress.update(consumed);
    }));
    const stream = source.method === 8
      ? counted.pipeThrough(requireDecompression('deflate-raw'))
      : counted;
    plates[String(source.plateIndex)] = await walkGcodeStream(
      stream as ReadableStream<Bytes>,
      hooks.signal,
      source.uncompressedSize,
    );
  }
  return plates;
};

/** The toolpath summary of one file, as the JSON text the server expects. */
export const readGcodeToolpath = async (
  file: File,
  hooks: GcodeToolpathHooks = {},
): Promise<string> => {
  requireStreams();
  throwIfAborted(hooks.signal);
  const kind = detectSourceKind(file.name);

  if (kind === '3mf') return serializeToolpath(await platesEvidence(file, hooks));
  return serializeToolpath(await plainEvidence(file, kind === 'gzip', hooks));
};
