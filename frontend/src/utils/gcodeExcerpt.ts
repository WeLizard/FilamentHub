// Cuts the small parts of a sliced file that a quote needs, in the browser, so the
// whole file (often 60+ MB) never has to be uploaded. Only browser APIs are used.

const KIB = 1024;
const MIB = 1024 * KIB;

export const GCODE_EXCERPT_LIMITS = {
  // Contents up to this size are sent whole as `head`; larger ones as head + tail.
  wholeContentBytes: 5 * MIB,
  headBytes: 1 * MIB,
  tailBytes: 4 * MIB,
  sliceInfoBytes: 2 * MIB,
  projectSettingsBytes: 4 * MIB,
  modelSettingsBytes: 1 * MIB,
  plateJsonBytes: 1 * MIB,
  thumbnailBytes: 8 * MIB,
  requestBytes: 24 * MIB,
  // The toolpath summary's own cap (256 KiB), then room for multipart boundaries and
  // part headers, inside the request cap.
  requestOverheadBytes: 256 * KIB + 64 * KIB,
  centralDirectoryBytes: 8 * MIB,
} as const;

export type GcodeExcerptContainer = 'plain_gcode' | 'gcode_3mf';

export type GcodeExcerptErrorCode =
  | 'ERR_GCODE_UNSUPPORTED_FILE'
  | 'ERR_GCODE_EXCERPT_INVALID'
  | 'ERR_GCODE_EXCERPT_TOO_LARGE'
  | 'ERR_GCODE_BROWSER_UNSUPPORTED';

/** The code doubles as an `apiErrors.*` translation key. */
export class GcodeExcerptError extends Error {
  readonly code: GcodeExcerptErrorCode;

  constructor(code: GcodeExcerptErrorCode) {
    super(code);
    this.name = 'GcodeExcerptError';
    this.code = code;
  }
}

export interface GcodeExcerptPart {
  field: 'head' | 'tail' | 'entry';
  blob: Blob;
  /** For 3MF entries this is the exact path inside the archive. */
  filename: string;
}

export interface GcodeExcerpt {
  fileName: string;
  fileSizeBytes: number;
  container: GcodeExcerptContainer;
  parts: GcodeExcerptPart[];
  /** JSON text of the walk over every move, built beside the excerpt; see gcodeToolpath.ts. */
  toolpath?: string;
}

const invalid = () => new GcodeExcerptError('ERR_GCODE_EXCERPT_INVALID');
const tooLarge = () => new GcodeExcerptError('ERR_GCODE_EXCERPT_TOO_LARGE');
const aborted = () => new DOMException('canceled', 'AbortError');

const throwIfAborted = (signal?: AbortSignal) => {
  if (signal?.aborted) throw aborted();
};

const readBytes = async (
  source: Blob,
  start: number,
  end: number,
  signal?: AbortSignal,
): Promise<Uint8Array<ArrayBuffer>> => {
  throwIfAborted(signal);
  const buffer = await source.slice(start, end).arrayBuffer();
  throwIfAborted(signal);
  return new Uint8Array(buffer);
};

const concatBytes = (chunks: Uint8Array[], totalLength: number): Uint8Array<ArrayBuffer> => {
  const out = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  return out;
};

export const requireDecompression = (format: 'gzip' | 'deflate-raw') => {
  if (typeof DecompressionStream === 'undefined') {
    throw new GcodeExcerptError('ERR_GCODE_BROWSER_UNSUPPORTED');
  }
  try {
    return new DecompressionStream(format);
  } catch {
    throw new GcodeExcerptError('ERR_GCODE_BROWSER_UNSUPPORTED');
  }
};

// ---------------------------------------------------------------------------
// Plain G-code and .gcode.gz
// ---------------------------------------------------------------------------

const partsFromContent = (
  head: Blob,
  tail: Blob | null,
): GcodeExcerptPart[] => [
  { field: 'head', blob: head, filename: 'head.gcode' },
  ...(tail ? [{ field: 'tail' as const, blob: tail, filename: 'tail.gcode' }] : []),
];

const plainFileParts = (file: Blob): GcodeExcerptPart[] => {
  const { wholeContentBytes, headBytes, tailBytes } = GCODE_EXCERPT_LIMITS;
  if (file.size <= wholeContentBytes) return partsFromContent(file.slice(0, file.size), null);
  // head ends at headBytes and tail starts at size - tailBytes > headBytes, so the
  // two slices never overlap.
  return partsFromContent(
    file.slice(0, headBytes),
    file.slice(file.size - tailBytes, file.size),
  );
};

const gzipParts = async (file: Blob, signal?: AbortSignal): Promise<GcodeExcerptPart[]> => {
  const { wholeContentBytes, headBytes, tailBytes } = GCODE_EXCERPT_LIMITS;
  const reader = file.stream().pipeThrough(requireDecompression('gzip')).getReader();
  const head = new Uint8Array(headBytes);
  let headLength = 0;
  let total = 0;
  const tailChunks: Uint8Array[] = [];
  let tailLength = 0;

  try {
    for (;;) {
      throwIfAborted(signal);
      const { done, value } = await reader.read();
      if (done) break;
      total += value.length;
      if (headLength < headBytes) {
        const take = Math.min(headBytes - headLength, value.length);
        head.set(value.subarray(0, take), headLength);
        headLength += take;
      }
      tailChunks.push(value);
      tailLength += value.length;
      // Drop the oldest chunk only while at least tailBytes remain without it, so
      // memory stays near tailBytes however large the decompressed content is.
      while (tailChunks.length > 1 && tailLength - tailChunks[0].length >= tailBytes) {
        tailLength -= tailChunks.shift()!.length;
      }
    }
  } catch (error) {
    void reader.cancel().catch(() => undefined);
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    if (signal?.aborted) throw aborted();
    throw invalid();
  }
  throwIfAborted(signal);

  const tail = concatBytes(tailChunks, tailLength);
  if (total <= wholeContentBytes) {
    // The tail buffer covers [total - tailLength, total) and tailLength >= min(total,
    // tailBytes), so it always reaches back to at most headLength.
    const whole = new Uint8Array(total);
    whole.set(head.subarray(0, headLength), 0);
    if (total > headLength) {
      whole.set(tail.subarray(headLength - (total - tailLength)), headLength);
    }
    return partsFromContent(new Blob([whole]), null);
  }
  return partsFromContent(
    new Blob([head]),
    new Blob([tail.subarray(tailLength - tailBytes)]),
  );
};

// ---------------------------------------------------------------------------
// .gcode.3mf (ZIP)
// ---------------------------------------------------------------------------

const SIG_EOCD = 0x06054b50;
const SIG_EOCD64 = 0x06064b50;
const SIG_EOCD64_LOCATOR = 0x07064b50;
const SIG_CENTRAL = 0x02014b50;
const SIG_LOCAL = 0x04034b50;
const EOCD_SIZE = 22;
const EOCD64_LOCATOR_SIZE = 20;
const EOCD64_SIZE = 56;
const LOCAL_HEADER_SIZE = 30;
const MAX_COMMENT = 0xffff;
const U16_MARKER = 0xffff;
const U32_MARKER = 0xffffffff;

interface EntryRule {
  pattern: RegExp;
  limit: number;
  thumbnail: boolean;
  priority: number;
}

// Order is also the order parts are sent in, so the required and most useful entries
// are never the ones dropped by the request cap.
const ENTRY_RULES: EntryRule[] = [
  { pattern: /^metadata\/slice_info\.config$/, limit: GCODE_EXCERPT_LIMITS.sliceInfoBytes, thumbnail: false, priority: 0 },
  { pattern: /^metadata\/project_settings\.config$/, limit: GCODE_EXCERPT_LIMITS.projectSettingsBytes, thumbnail: false, priority: 1 },
  { pattern: /^metadata\/model_settings\.config$/, limit: GCODE_EXCERPT_LIMITS.modelSettingsBytes, thumbnail: false, priority: 2 },
  { pattern: /^metadata\/plate_\d{1,6}\.json$/, limit: GCODE_EXCERPT_LIMITS.plateJsonBytes, thumbnail: false, priority: 3 },
  { pattern: /^metadata\/plate_\d{1,6}(?:_small)?\.png$/, limit: GCODE_EXCERPT_LIMITS.thumbnailBytes, thumbnail: true, priority: 4 },
];

// Plate G-code is walked as a stream by the toolpath reader; the excerpt never carries it.
const GCODE_PLATE_RULE: EntryRule = {
  pattern: /^metadata\/plate_(\d{1,6})\.gcode$/,
  limit: 0,
  thumbnail: false,
  priority: 0,
};

const SLICE_INFO_PATH = 'metadata/slice_info.config';

interface ZipEntry {
  name: string;
  nameLower: string;
  rule: EntryRule;
  method: number;
  compressedSize: number;
  uncompressedSize: number;
  localHeaderOffset: number;
}

interface CentralDirectoryLocation {
  offset: number;
  size: number;
  entryCount: number;
}

const readU64 = (view: DataView, offset: number): number => {
  const value = view.getBigUint64(offset, true);
  if (value > BigInt(Number.MAX_SAFE_INTEGER)) throw invalid();
  return Number(value);
};

// The comment length must run exactly to the end of the buffer, which rules out a
// signature that merely appears inside a comment.
const findEocd = (tail: Uint8Array, view: DataView): number => {
  for (let index = tail.length - EOCD_SIZE; index >= 0; index -= 1) {
    if (
      view.getUint32(index, true) === SIG_EOCD
      && index + EOCD_SIZE + view.getUint16(index + 20, true) === tail.length
    ) {
      return index;
    }
  }
  return -1;
};

const locateCentralDirectory = async (
  file: Blob,
  signal?: AbortSignal,
): Promise<CentralDirectoryLocation> => {
  const fileSize = file.size;
  if (fileSize < EOCD_SIZE) throw invalid();

  // Archives without a comment end with the bare 22-byte record, so read just that
  // first; only a comment forces the wider window (which may graze entry data).
  let tailStart = fileSize - EOCD_SIZE;
  let tail = await readBytes(file, tailStart, fileSize, signal);
  let tailView = new DataView(tail.buffer);
  let eocdIndex = findEocd(tail, tailView);
  if (eocdIndex < 0) {
    tailStart = Math.max(0, fileSize - (EOCD_SIZE + MAX_COMMENT));
    tail = await readBytes(file, tailStart, fileSize, signal);
    tailView = new DataView(tail.buffer);
    eocdIndex = findEocd(tail, tailView);
  }
  if (eocdIndex < 0) throw invalid();

  const diskNumber = tailView.getUint16(eocdIndex + 4, true);
  const centralDisk = tailView.getUint16(eocdIndex + 6, true);
  let entryCount = tailView.getUint16(eocdIndex + 10, true);
  let size = tailView.getUint32(eocdIndex + 12, true);
  let offset = tailView.getUint32(eocdIndex + 16, true);
  const eocdPosition = tailStart + eocdIndex;

  const needsZip64 = entryCount === U16_MARKER
    || size === U32_MARKER
    || offset === U32_MARKER
    || diskNumber === U16_MARKER
    || centralDisk === U16_MARKER;

  if (needsZip64) {
    if (eocdPosition < EOCD64_LOCATOR_SIZE) throw invalid();
    const locator = await readBytes(file, eocdPosition - EOCD64_LOCATOR_SIZE, eocdPosition, signal);
    const locatorView = new DataView(locator.buffer);
    if (locatorView.getUint32(0, true) !== SIG_EOCD64_LOCATOR) throw invalid();
    if (locatorView.getUint32(16, true) > 1) throw invalid();
    const recordPosition = readU64(locatorView, 8);
    if (recordPosition + EOCD64_SIZE > eocdPosition) throw invalid();

    const record = await readBytes(file, recordPosition, recordPosition + EOCD64_SIZE, signal);
    const recordView = new DataView(record.buffer);
    if (recordView.getUint32(0, true) !== SIG_EOCD64) throw invalid();
    if (recordView.getUint32(16, true) !== 0 || recordView.getUint32(20, true) !== 0) throw invalid();
    entryCount = readU64(recordView, 32);
    size = readU64(recordView, 40);
    offset = readU64(recordView, 48);
  } else if (diskNumber !== 0 || centralDisk !== 0) {
    throw invalid();
  }

  if (offset + size > eocdPosition) throw invalid();
  if (size > GCODE_EXCERPT_LIMITS.centralDirectoryBytes) throw tooLarge();
  return { offset, size, entryCount };
};

const matchEntryRule = (nameLower: string, rules: readonly EntryRule[]): EntryRule | null =>
  rules.find((rule) => rule.pattern.test(nameLower)) ?? null;

const parseCentralDirectory = (
  directory: Uint8Array,
  entryCount: number,
  fileSize: number,
  rules: readonly EntryRule[] = ENTRY_RULES,
): ZipEntry[] => {
  const view = new DataView(directory.buffer, directory.byteOffset, directory.byteLength);
  const decoder = new TextDecoder('utf-8');
  const entries: ZipEntry[] = [];
  let position = 0;

  for (let index = 0; index < entryCount; index += 1) {
    if (position + 46 > directory.length) throw invalid();
    if (view.getUint32(position, true) !== SIG_CENTRAL) throw invalid();
    const flags = view.getUint16(position + 8, true);
    const method = view.getUint16(position + 10, true);
    let compressedSize = view.getUint32(position + 20, true);
    let uncompressedSize = view.getUint32(position + 24, true);
    const nameLength = view.getUint16(position + 28, true);
    const extraLength = view.getUint16(position + 30, true);
    const commentLength = view.getUint16(position + 32, true);
    const diskStart = view.getUint16(position + 34, true);
    let localHeaderOffset = view.getUint32(position + 42, true);
    const nameStart = position + 46;
    const extraStart = nameStart + nameLength;
    const next = extraStart + extraLength + commentLength;
    if (next > directory.length) throw invalid();

    const name = decoder.decode(directory.subarray(nameStart, extraStart));
    const nameLower = name.toLowerCase();
    const rule = matchEntryRule(nameLower, rules);

    if (rule) {
      if (
        compressedSize === U32_MARKER
        || uncompressedSize === U32_MARKER
        || localHeaderOffset === U32_MARKER
        || diskStart === U16_MARKER
      ) {
        // ZIP64 extra field carries only the fields whose 32-bit value is the marker,
        // in this fixed order.
        let extraPosition = extraStart;
        const extraEnd = extraStart + extraLength;
        let found = false;
        while (extraPosition + 4 <= extraEnd) {
          const id = view.getUint16(extraPosition, true);
          const dataSize = view.getUint16(extraPosition + 2, true);
          const dataStart = extraPosition + 4;
          const dataEnd = dataStart + dataSize;
          if (dataEnd > extraEnd) throw invalid();
          if (id === 0x0001) {
            let cursor = dataStart;
            const take64 = () => {
              if (cursor + 8 > dataEnd) throw invalid();
              const value = readU64(view, cursor);
              cursor += 8;
              return value;
            };
            if (uncompressedSize === U32_MARKER) uncompressedSize = take64();
            if (compressedSize === U32_MARKER) compressedSize = take64();
            if (localHeaderOffset === U32_MARKER) localHeaderOffset = take64();
            if (diskStart === U16_MARKER) {
              if (cursor + 4 > dataEnd) throw invalid();
              if (view.getUint32(cursor, true) !== 0) throw invalid();
            }
            found = true;
            break;
          }
          extraPosition = dataEnd;
        }
        if (!found) throw invalid();
      } else if (diskStart !== 0) {
        throw invalid();
      }

      if (flags & 0x1) throw invalid(); // encrypted entries are not supported
      if (method !== 0 && method !== 8) throw invalid();
      if (method === 0 && compressedSize !== uncompressedSize) throw invalid();
      if (localHeaderOffset + LOCAL_HEADER_SIZE > fileSize) throw invalid();

      entries.push({
        name,
        nameLower,
        rule,
        method,
        compressedSize,
        uncompressedSize,
        localHeaderOffset,
      });
    }
    position = next;
  }
  return entries;
};

const locateEntryData = async (
  file: Blob,
  entry: ZipEntry,
  signal?: AbortSignal,
): Promise<{ dataStart: number; dataEnd: number }> => {
  const header = await readBytes(
    file,
    entry.localHeaderOffset,
    entry.localHeaderOffset + LOCAL_HEADER_SIZE,
    signal,
  );
  const view = new DataView(header.buffer);
  if (view.getUint32(0, true) !== SIG_LOCAL) throw invalid();
  const dataStart = entry.localHeaderOffset
    + LOCAL_HEADER_SIZE
    + view.getUint16(26, true)
    + view.getUint16(28, true);
  const dataEnd = dataStart + entry.compressedSize;
  if (dataEnd > file.size) throw invalid();
  return { dataStart, dataEnd };
};

const extractEntry = async (
  file: Blob,
  entry: ZipEntry,
  signal?: AbortSignal,
): Promise<Blob> => {
  const { dataStart, dataEnd } = await locateEntryData(file, entry, signal);

  if (entry.method === 0) {
    const bytes = await readBytes(file, dataStart, dataEnd, signal);
    return new Blob([bytes]);
  }

  const reader = file
    .slice(dataStart, dataEnd)
    .stream()
    .pipeThrough(requireDecompression('deflate-raw'))
    .getReader();
  // The declared size already passed the cap; a stream that inflates beyond it is
  // lying about its size and is rejected as soon as it does.
  const out = new Uint8Array(entry.uncompressedSize);
  let length = 0;
  try {
    for (;;) {
      throwIfAborted(signal);
      const { done, value } = await reader.read();
      if (done) break;
      if (length + value.length > out.length) throw invalid();
      out.set(value, length);
      length += value.length;
    }
  } catch (error) {
    void reader.cancel().catch(() => undefined);
    if (error instanceof GcodeExcerptError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    if (signal?.aborted) throw aborted();
    throw invalid();
  }
  if (length !== out.length) throw invalid();
  return new Blob([out]);
};

const threeMfParts = async (file: Blob, signal?: AbortSignal): Promise<GcodeExcerptPart[]> => {
  const location = await locateCentralDirectory(file, signal);
  const directory = await readBytes(file, location.offset, location.offset + location.size, signal);
  const entries = parseCentralDirectory(directory, location.entryCount, file.size);

  const seen = new Set<string>();
  for (const entry of entries) {
    if (seen.has(entry.nameLower)) throw invalid();
    seen.add(entry.nameLower);
  }
  if (!seen.has(SLICE_INFO_PATH)) throw invalid();

  const ordered = [...entries].sort((a, b) => a.rule.priority - b.rule.priority);
  const budget = GCODE_EXCERPT_LIMITS.requestBytes - GCODE_EXCERPT_LIMITS.requestOverheadBytes;
  let used = 0;
  const parts: GcodeExcerptPart[] = [];

  for (const entry of ordered) {
    const { rule } = entry;
    if (entry.uncompressedSize > rule.limit) {
      if (rule.thumbnail) continue;
      throw tooLarge();
    }
    // A thumbnail that would push the request past its cap is simply left out; any
    // other entry that does not fit makes the file unusable.
    if (used + entry.uncompressedSize > budget) {
      if (rule.thumbnail) continue;
      throw tooLarge();
    }
    const blob = await extractEntry(file, entry, signal);
    used += blob.size;
    parts.push({ field: 'entry', blob, filename: entry.name });
  }
  return parts;
};

/** One sliced plate's G-code inside a 3MF, readable as a stream of its stored bytes. */
export interface GcodePlateSource {
  plateIndex: number;
  method: 0 | 8;
  compressedSize: number;
  uncompressedSize: number;
  /** The entry as stored: raw bytes for method 0, deflate-raw for method 8. */
  openStored: () => Promise<ReadableStream<Uint8Array<ArrayBuffer>>>;
}

export const listGcodePlateSources = async (
  file: Blob,
  signal?: AbortSignal,
): Promise<GcodePlateSource[]> => {
  const location = await locateCentralDirectory(file, signal);
  const directory = await readBytes(file, location.offset, location.offset + location.size, signal);
  const entries = parseCentralDirectory(directory, location.entryCount, file.size, [GCODE_PLATE_RULE]);

  const seen = new Set<string>();
  const sources: GcodePlateSource[] = [];
  for (const entry of entries) {
    if (seen.has(entry.nameLower)) throw invalid();
    seen.add(entry.nameLower);
    const match = GCODE_PLATE_RULE.pattern.exec(entry.nameLower);
    sources.push({
      plateIndex: Number(match![1]),
      method: entry.method as 0 | 8,
      compressedSize: entry.compressedSize,
      uncompressedSize: entry.uncompressedSize,
      openStored: async () => {
        const { dataStart, dataEnd } = await locateEntryData(file, entry, signal);
        return file.slice(dataStart, dataEnd).stream();
      },
    });
  }
  return sources.sort((a, b) => a.plateIndex - b.plateIndex);
};

// ---------------------------------------------------------------------------
// Entry points
// ---------------------------------------------------------------------------

type SourceKind = 'plain' | 'gzip' | '3mf';

export const detectSourceKind = (fileName: string): SourceKind => {
  const lower = fileName.toLowerCase();
  if (lower.endsWith('.3mf')) return '3mf';
  if (lower.endsWith('.gz')) return 'gzip';
  if (lower.endsWith('.gcode') || lower.endsWith('.txt')) return 'plain';
  throw new GcodeExcerptError('ERR_GCODE_UNSUPPORTED_FILE');
};

export const buildGcodeExcerpt = async (
  file: File,
  signal?: AbortSignal,
): Promise<GcodeExcerpt> => {
  const kind = detectSourceKind(file.name);
  throwIfAborted(signal);
  const base = { fileName: file.name, fileSizeBytes: file.size };

  if (kind === '3mf') {
    return { ...base, container: 'gcode_3mf', parts: await threeMfParts(file, signal) };
  }
  if (kind === 'gzip') {
    return { ...base, container: 'plain_gcode', parts: await gzipParts(file, signal) };
  }
  return { ...base, container: 'plain_gcode', parts: plainFileParts(file) };
};

export const buildGcodeExcerptFormData = (excerpt: GcodeExcerpt): FormData => {
  const formData = new FormData();
  formData.append('file_name', excerpt.fileName);
  formData.append('file_size_bytes', String(excerpt.fileSizeBytes));
  formData.append('container', excerpt.container);
  if (excerpt.toolpath !== undefined) formData.append('toolpath', excerpt.toolpath);
  for (const part of excerpt.parts) {
    formData.append(part.field, part.blob, part.filename);
  }
  return formData;
};
