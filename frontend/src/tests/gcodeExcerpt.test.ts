// @vitest-environment node
// Node provides File, Blob streams and (De)CompressionStream, which jsdom lacks.
import { describe, expect, it } from 'vitest';

import {
  buildGcodeExcerpt,
  buildGcodeExcerptFormData,
  GCODE_EXCERPT_LIMITS,
  type GcodeExcerptErrorCode,
} from '../utils/gcodeExcerpt';
import { readGcodeToolpath } from '../utils/gcodeToolpathReader';

const MIB = 1024 * 1024;
const encoder = new TextEncoder();

const pseudoRandomBytes = (length: number, seed = 1): Uint8Array<ArrayBuffer> => {
  const out = new Uint8Array(length);
  let x = seed >>> 0;
  for (let index = 0; index < length; index += 1) {
    x = (Math.imul(x, 1664525) + 1013904223) >>> 0;
    out[index] = x >>> 24;
  }
  return out;
};

const text = (value: string): Uint8Array<ArrayBuffer> => new Uint8Array(encoder.encode(value));

const pipe = async (
  data: Uint8Array<ArrayBuffer>,
  stream: CompressionStream,
): Promise<Uint8Array<ArrayBuffer>> =>
  new Uint8Array(await new Response(new Blob([data]).stream().pipeThrough(stream)).arrayBuffer());

const bytesOf = async (blob: Blob) => new Uint8Array(await blob.arrayBuffer());

// toEqual on multi-megabyte arrays is far too slow; compare in a plain loop.
const sameBytes = (actual: Uint8Array, expected: Uint8Array): boolean => {
  if (actual.length !== expected.length) return false;
  for (let index = 0; index < actual.length; index += 1) {
    if (actual[index] !== expected[index]) return false;
  }
  return true;
};

interface TestEntry {
  name: string;
  data: Uint8Array<ArrayBuffer>;
  method?: 0 | 8;
  flags?: number;
  /** Central directory claims this size while the data inflates to something else. */
  declaredSize?: number;
}

interface BuiltZip {
  file: File;
  dataRanges: Map<string, [number, number]>;
}

const buildZip = async (
  entries: TestEntry[],
  { zip64 = false, comment = '' }: { zip64?: boolean; comment?: string } = {},
): Promise<BuiltZip> => {
  const chunks: Uint8Array<ArrayBuffer>[] = [];
  let position = 0;
  const push = (chunk: Uint8Array<ArrayBuffer>) => {
    chunks.push(chunk);
    position += chunk.length;
  };
  const dataRanges = new Map<string, [number, number]>();
  const central: Array<{
    entry: TestEntry;
    method: number;
    compressedSize: number;
    uncompressedSize: number;
    offset: number;
  }> = [];

  for (const entry of entries) {
    const method = entry.method ?? 0;
    const stored = method === 8 ? await pipe(entry.data, new CompressionStream('deflate-raw')) : entry.data;
    const name = text(entry.name);
    const header = new Uint8Array(30);
    const view = new DataView(header.buffer);
    view.setUint32(0, 0x04034b50, true);
    view.setUint16(4, 20, true);
    view.setUint16(6, entry.flags ?? 0, true);
    view.setUint16(8, method, true);
    view.setUint32(18, stored.length, true);
    view.setUint32(22, entry.data.length, true);
    view.setUint16(26, name.length, true);
    const offset = position;
    push(header);
    push(name);
    dataRanges.set(entry.name, [position, position + stored.length]);
    push(stored);
    central.push({
      entry,
      method,
      compressedSize: stored.length,
      uncompressedSize: entry.declaredSize ?? entry.data.length,
      offset,
    });
  }

  const centralStart = position;
  for (const item of central) {
    const name = text(item.entry.name);
    const extra = new Uint8Array(zip64 ? 28 : 0);
    const header = new Uint8Array(46);
    const view = new DataView(header.buffer);
    view.setUint32(0, 0x02014b50, true);
    view.setUint16(4, 45, true);
    view.setUint16(6, 45, true);
    view.setUint16(8, item.entry.flags ?? 0, true);
    view.setUint16(10, item.method, true);
    view.setUint16(28, name.length, true);
    view.setUint16(30, extra.length, true);
    if (zip64) {
      view.setUint32(20, 0xffffffff, true);
      view.setUint32(24, 0xffffffff, true);
      view.setUint32(42, 0xffffffff, true);
      const extraView = new DataView(extra.buffer);
      extraView.setUint16(0, 0x0001, true);
      extraView.setUint16(2, 24, true);
      extraView.setBigUint64(4, BigInt(item.uncompressedSize), true);
      extraView.setBigUint64(12, BigInt(item.compressedSize), true);
      extraView.setBigUint64(20, BigInt(item.offset), true);
    } else {
      view.setUint32(20, item.compressedSize, true);
      view.setUint32(24, item.uncompressedSize, true);
      view.setUint32(42, item.offset, true);
    }
    push(header);
    push(name);
    push(extra);
  }
  const centralSize = position - centralStart;

  if (zip64) {
    const record = new Uint8Array(56);
    const recordView = new DataView(record.buffer);
    recordView.setUint32(0, 0x06064b50, true);
    recordView.setBigUint64(4, 44n, true);
    recordView.setUint16(12, 45, true);
    recordView.setUint16(14, 45, true);
    recordView.setBigUint64(24, BigInt(central.length), true);
    recordView.setBigUint64(32, BigInt(central.length), true);
    recordView.setBigUint64(40, BigInt(centralSize), true);
    recordView.setBigUint64(48, BigInt(centralStart), true);
    const recordPosition = position;
    push(record);
    const locator = new Uint8Array(20);
    const locatorView = new DataView(locator.buffer);
    locatorView.setUint32(0, 0x07064b50, true);
    locatorView.setBigUint64(8, BigInt(recordPosition), true);
    locatorView.setUint32(16, 1, true);
    push(locator);
  }

  const commentBytes = text(comment);
  const eocd = new Uint8Array(22);
  const eocdView = new DataView(eocd.buffer);
  eocdView.setUint32(0, 0x06054b50, true);
  eocdView.setUint16(8, zip64 ? 0xffff : central.length, true);
  eocdView.setUint16(10, zip64 ? 0xffff : central.length, true);
  eocdView.setUint32(12, zip64 ? 0xffffffff : centralSize, true);
  eocdView.setUint32(16, zip64 ? 0xffffffff : centralStart, true);
  eocdView.setUint16(20, commentBytes.length, true);
  push(eocd);
  push(commentBytes);

  return { file: new File(chunks, 'plate.gcode.3mf'), dataRanges };
};

const recordSlices = (file: File): Array<[number, number]> => {
  const ranges: Array<[number, number]> = [];
  const original = file.slice.bind(file);
  file.slice = ((start?: number, end?: number, type?: string) => {
    ranges.push([start ?? 0, end ?? file.size]);
    return original(start, end, type);
  }) as typeof file.slice;
  return ranges;
};

const sliceInfo = text('<config><plate><metadata key="index" value="1"/></plate></config>');
const settings = text(JSON.stringify({ layer_height: '0.2', note: 'x'.repeat(50_000) }));
const modelSettings = text('<config><object id="2"/></config>');
const plateJson = text('{"bbox_all":[0,0,10,10]}');
const png = pseudoRandomBytes(20_000, 7);

const sampleEntries = (gcode: Uint8Array<ArrayBuffer>): TestEntry[] => [
  { name: '[Content_Types].xml', data: text('<Types/>'), method: 8 },
  { name: '3D/3dmodel.model', data: pseudoRandomBytes(30_000, 3), method: 8 },
  { name: 'Metadata/plate_1.gcode', data: gcode },
  { name: 'Metadata/slice_info.config', data: sliceInfo, method: 8 },
  { name: 'Metadata/project_settings.config', data: settings, method: 8 },
  { name: 'Metadata/MODEL_settings.config', data: modelSettings },
  { name: 'Metadata/plate_1.json', data: plateJson },
  { name: 'Metadata/plate_1.png', data: png },
  { name: 'Metadata/plate_1_small.png', data: png.subarray(0, 4_000) as Uint8Array<ArrayBuffer> },
  { name: 'Metadata/plate_no_light_1.png', data: png },
  { name: 'Metadata/top_1.png', data: png },
];

const expectedSampleEntries: Record<string, Uint8Array<ArrayBuffer>> = {
  'Metadata/slice_info.config': sliceInfo,
  'Metadata/project_settings.config': settings,
  'Metadata/MODEL_settings.config': modelSettings,
  'Metadata/plate_1.json': plateJson,
  'Metadata/plate_1.png': png,
  'Metadata/plate_1_small.png': png.subarray(0, 4_000) as Uint8Array<ArrayBuffer>,
};

describe('gcode.3mf excerpt', () => {
  it.each([
    ['plain ZIP', false],
    ['ZIP64 markers', true],
  ])('extracts only the allowed entries and never reads the plate G-code (%s)', async (_label, zip64) => {
    const gcode = pseudoRandomBytes(3 * MIB, 11);
    const { file, dataRanges } = await buildZip(sampleEntries(gcode), { zip64 });
    const slices = recordSlices(file);

    const excerpt = await buildGcodeExcerpt(file);

    expect(excerpt.container).toBe('gcode_3mf');
    expect(excerpt.fileSizeBytes).toBe(file.size);
    expect(excerpt.parts.map((part) => part.field)).toEqual(Array(6).fill('entry'));
    expect(excerpt.parts.map((part) => part.filename).sort()).toEqual(
      Object.keys(expectedSampleEntries).sort(),
    );
    expect(excerpt.parts[0].filename).toBe('Metadata/slice_info.config');
    for (const part of excerpt.parts) {
      expect(await bytesOf(part.blob)).toEqual(expectedSampleEntries[part.filename]);
    }

    const [gcodeStart, gcodeEnd] = dataRanges.get('Metadata/plate_1.gcode')!;
    expect(slices.some(([start, end]) => start < gcodeEnd && end > gcodeStart)).toBe(false);
    expect(Math.max(...slices.map(([start, end]) => end - start))).toBeLessThan(MIB);
  });

  it('finds the end record behind an archive comment, even one that mimics a record', async () => {
    const fakeRecord = String.fromCharCode(0x50, 0x4b, 0x05, 0x06);
    const { file } = await buildZip(
      [{ name: 'Metadata/slice_info.config', data: sliceInfo }],
      { comment: `${fakeRecord}${'c'.repeat(300)}` },
    );

    const excerpt = await buildGcodeExcerpt(file);

    expect(excerpt.parts.map((part) => part.filename)).toEqual(['Metadata/slice_info.config']);
  });

  it('leaves out an oversize thumbnail but keeps the rest', async () => {
    const { file } = await buildZip([
      { name: 'Metadata/slice_info.config', data: sliceInfo },
      { name: 'Metadata/plate_1.png', data: new Uint8Array(GCODE_EXCERPT_LIMITS.thumbnailBytes + 1) },
      { name: 'Metadata/plate_1_small.png', data: png },
    ]);

    const excerpt = await buildGcodeExcerpt(file);

    expect(excerpt.parts.map((part) => part.filename)).toEqual([
      'Metadata/slice_info.config',
      'Metadata/plate_1_small.png',
    ]);
  });

  it('drops thumbnails that would push the request past its cap', async () => {
    const thumbnail = new Uint8Array(7 * MIB);
    const { file } = await buildZip([
      { name: 'Metadata/slice_info.config', data: sliceInfo },
      ...[1, 2, 3, 4].map((index) => ({ name: `Metadata/plate_${index}.png`, data: thumbnail })),
    ]);

    const excerpt = await buildGcodeExcerpt(file);

    const total = excerpt.parts.reduce((sum, part) => sum + part.blob.size, 0);
    expect(total).toBeLessThanOrEqual(GCODE_EXCERPT_LIMITS.requestBytes);
    expect(excerpt.parts.map((part) => part.filename)).toEqual([
      'Metadata/slice_info.config',
      'Metadata/plate_1.png',
      'Metadata/plate_2.png',
      'Metadata/plate_3.png',
    ]);
  });

  const rejections: Array<[string, () => Promise<File>, GcodeExcerptErrorCode]> = [
    [
      'no slice_info.config',
      async () => (await buildZip([{ name: 'Metadata/plate_1.json', data: plateJson }])).file,
      'ERR_GCODE_EXCERPT_INVALID',
    ],
    [
      'slice_info.config over its cap',
      async () => (await buildZip([
        { name: 'Metadata/slice_info.config', data: new Uint8Array(GCODE_EXCERPT_LIMITS.sliceInfoBytes + 1) },
      ])).file,
      'ERR_GCODE_EXCERPT_TOO_LARGE',
    ],
    [
      'encrypted slice_info.config',
      async () => (await buildZip([
        { name: 'Metadata/slice_info.config', data: sliceInfo, flags: 1 },
      ])).file,
      'ERR_GCODE_EXCERPT_INVALID',
    ],
    [
      'entry that inflates past its declared size',
      async () => (await buildZip([
        {
          name: 'Metadata/slice_info.config',
          data: new Uint8Array(100_000),
          method: 8,
          declaredSize: 10,
        },
      ])).file,
      'ERR_GCODE_EXCERPT_INVALID',
    ],
    [
      'duplicate allowed entry',
      async () => (await buildZip([
        { name: 'Metadata/slice_info.config', data: sliceInfo },
        { name: 'metadata/SLICE_INFO.config', data: sliceInfo },
      ])).file,
      'ERR_GCODE_EXCERPT_INVALID',
    ],
    [
      'not a ZIP at all',
      async () => new File([pseudoRandomBytes(5_000, 5)], 'broken.gcode.3mf'),
      'ERR_GCODE_EXCERPT_INVALID',
    ],
  ];

  it.each(rejections)('rejects a file with %s', async (_label, make, code) => {
    await expect(buildGcodeExcerpt(await make())).rejects.toMatchObject({ code });
  });
});

describe('plain G-code excerpt', () => {
  it('sends a file up to 5 MiB whole as head only', async () => {
    const data = pseudoRandomBytes(5 * MIB, 21);
    const excerpt = await buildGcodeExcerpt(new File([data], 'small.gcode'));

    expect(excerpt.container).toBe('plain_gcode');
    expect(excerpt.parts.map((part) => part.field)).toEqual(['head']);
    expect(sameBytes(await bytesOf(excerpt.parts[0].blob), data)).toBe(true);
  });

  it('cuts a larger file into the first 1 MiB and the last 4 MiB without overlap', async () => {
    const data = pseudoRandomBytes(5 * MIB + 1, 22);
    const file = new File([data], 'big.gcode');
    const slices = recordSlices(file);

    const excerpt = await buildGcodeExcerpt(file);

    const [head, tail] = excerpt.parts;
    expect([head.field, tail.field]).toEqual(['head', 'tail']);
    expect(sameBytes(await bytesOf(head.blob), data.subarray(0, MIB))).toBe(true);
    expect(sameBytes(await bytesOf(tail.blob), data.subarray(data.length - 4 * MIB))).toBe(true);
    expect(head.blob.size + tail.blob.size).toBeLessThan(data.length);
    expect(slices).toEqual([[0, MIB], [data.length - 4 * MIB, data.length]]);
  });

  it('rejects an unsupported file type before reading it', async () => {
    await expect(buildGcodeExcerpt(new File(['x'], 'model.stl'))).rejects.toMatchObject({
      code: 'ERR_GCODE_UNSUPPORTED_FILE',
    });
  });
});

describe('gzip G-code excerpt', () => {
  it.each([200_000, 3 * MIB + 17, 5 * MIB, 5 * MIB + 1, 6 * MIB + 12_345])(
    'matches the plain rule for %i decompressed bytes',
    async (size) => {
      const data = pseudoRandomBytes(size, 31);
      const gz = await pipe(data, new CompressionStream('gzip'));

      const excerpt = await buildGcodeExcerpt(new File([gz], 'part.gcode.gz'));

      expect(excerpt.container).toBe('plain_gcode');
      expect(excerpt.fileSizeBytes).toBe(gz.length);
      const expected = await buildGcodeExcerpt(new File([data], 'part.gcode'));
      expect(excerpt.parts.map((part) => part.field)).toEqual(
        expected.parts.map((part) => part.field),
      );
      for (const [index, part] of excerpt.parts.entries()) {
        expect(sameBytes(
          await bytesOf(part.blob),
          await bytesOf(expected.parts[index].blob),
        )).toBe(true);
      }
    },
  );

  it('rejects data that is not valid gzip', async () => {
    await expect(
      buildGcodeExcerpt(new File([pseudoRandomBytes(10_000, 9)], 'broken.gcode.gz')),
    ).rejects.toMatchObject({ code: 'ERR_GCODE_EXCERPT_INVALID' });
  });

  it('stops reading when cancelled', async () => {
    const gz = await pipe(pseudoRandomBytes(MIB, 4), new CompressionStream('gzip'));
    const controller = new AbortController();
    controller.abort();

    await expect(
      buildGcodeExcerpt(new File([gz], 'part.gcode.gz'), controller.signal),
    ).rejects.toMatchObject({ name: 'AbortError' });
  });
});

describe('excerpt form data', () => {
  it('names each 3MF entry by its exact archive path', async () => {
    const { file } = await buildZip([
      { name: 'Metadata/slice_info.config', data: sliceInfo },
      { name: 'Metadata/plate_2.json', data: plateJson },
    ]);

    const formData = buildGcodeExcerptFormData(await buildGcodeExcerpt(file));

    expect(formData.get('container')).toBe('gcode_3mf');
    expect(formData.get('file_name')).toBe('plate.gcode.3mf');
    expect(formData.get('file_size_bytes')).toBe(String(file.size));
    expect(formData.getAll('entry').map((part) => (part as File).name)).toEqual([
      'Metadata/slice_info.config',
      'Metadata/plate_2.json',
    ]);
  });

  it('carries the toolpath summary as one text field, and none when there is none', async () => {
    const { file } = await buildZip([{ name: 'Metadata/slice_info.config', data: sliceInfo }]);
    const excerpt = await buildGcodeExcerpt(file);

    expect(buildGcodeExcerptFormData(excerpt).has('toolpath')).toBe(false);
    expect(buildGcodeExcerptFormData({ ...excerpt, toolpath: '{"1":{}}' }).get('toolpath')).toBe('{"1":{}}');
  });
});

describe('toolpath of a gcode.3mf', () => {
  const plateGcode = (extrusion: number) => text(`M83\n;TYPE:Outer wall\nG1 X1 E${extrusion}\n`);

  it('walks every plate G-code entry, stored or deflated, and nothing else', async () => {
    const { file } = await buildZip([
      { name: 'Metadata/slice_info.config', data: sliceInfo, method: 8 },
      { name: 'Metadata/plate_2.gcode', data: plateGcode(4), method: 8 },
      { name: 'Metadata/plate_1.gcode', data: plateGcode(2) },
      { name: 'Metadata/plate_1.png', data: png },
    ]);
    const progress: number[] = [];

    const toolpath = JSON.parse(await readGcodeToolpath(file, { onProgress: (value) => progress.push(value) }));

    expect(Object.keys(toolpath)).toEqual(['1', '2']);
    expect(toolpath['1'].extrusion_by_tool_role).toEqual({ '0': { 'outer wall': 2 } });
    expect(toolpath['2'].extrusion_by_tool_role).toEqual({ '0': { 'outer wall': 4 } });
    expect(progress.at(-1)).toBe(1);
    expect(progress).toEqual([...progress].sort((a, b) => a - b));
  });

  it('reads a ZIP64 archive too', async () => {
    const { file } = await buildZip(
      [
        { name: 'Metadata/slice_info.config', data: sliceInfo },
        { name: 'Metadata/plate_1.gcode', data: plateGcode(3), method: 8 },
      ],
      { zip64: true },
    );

    const toolpath = JSON.parse(await readGcodeToolpath(file));

    expect(toolpath['1'].extrusion_by_tool_role).toEqual({ '0': { 'outer wall': 3 } });
  });

  it('is refused for an archive whose G-code cannot be read, while its excerpt still builds', async () => {
    const encrypted = (await buildZip([
      { name: 'Metadata/slice_info.config', data: sliceInfo },
      { name: 'Metadata/plate_1.gcode', data: plateGcode(1), flags: 1 },
    ])).file;
    const corrupt = (await buildZip([
      { name: 'Metadata/slice_info.config', data: sliceInfo },
      { name: 'Metadata/plate_1.gcode', data: pseudoRandomBytes(5_000, 3), method: 8, declaredSize: 5 },
    ])).file;
    const without = (await buildZip([{ name: 'Metadata/slice_info.config', data: sliceInfo }])).file;

    await expect(readGcodeToolpath(encrypted)).rejects.toMatchObject({ code: 'ERR_GCODE_EXCERPT_INVALID' });
    await expect(readGcodeToolpath(corrupt)).rejects.toMatchObject({ code: 'ERR_GCODE_EXCERPT_INVALID' });
    await expect(readGcodeToolpath(without)).rejects.toMatchObject({ code: 'ERR_GCODE_EXCERPT_INVALID' });
    // The excerpt itself does not care about the G-code entry.
    await expect(buildGcodeExcerpt(encrypted)).resolves.toMatchObject({ container: 'gcode_3mf' });
  });

  it('stops when cancelled', async () => {
    const controller = new AbortController();
    controller.abort();

    await expect(readGcodeToolpath(new File(['G1 E1'], 'a.gcode'), { signal: controller.signal }))
      .rejects.toMatchObject({ name: 'AbortError' });
  });
});
