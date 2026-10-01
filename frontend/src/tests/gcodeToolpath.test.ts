// @vitest-environment node
// Node provides File, Blob streams and (De)CompressionStream, which jsdom lacks.
import { describe, expect, it } from 'vitest';

// The same fixture and expected walk the backend test reads: the two implementations of
// the line walk cannot drift apart without one of the suites failing.
import fixtureGcode from '../../../backend/tests/fixtures/gcode_toolpath_parity/toolpath.gcode?raw';
import fixtureEvidence from '../../../backend/tests/fixtures/gcode_toolpath_parity/expected_evidence.json?raw';
import bambuGcode from '../../../backend/tests/fixtures/gcode_toolpath_parity/bambu_toolpath.gcode?raw';
import bambuEvidence from '../../../backend/tests/fixtures/gcode_toolpath_parity/bambu_expected_evidence.json?raw';
import {
  serializeToolpath,
  TOOLPATH_LIMITS,
  ToolpathLimitError,
  ToolpathWalker,
  type ToolpathEvidence,
} from '../utils/gcodeToolpath';
import { readGcodeToolpath, walkGcodeStream } from '../utils/gcodeToolpathReader';

const EXPECTED = JSON.parse(fixtureEvidence) as ToolpathEvidence;
const encoder = new TextEncoder();

const walk = (text: string, chunkSizes: number[] = [text.length || 1]): ToolpathEvidence => {
  const walker = new ToolpathWalker();
  let position = 0;
  for (let step = 0; position < text.length; step += 1) {
    const size = chunkSizes[step % chunkSizes.length];
    walker.push(text.slice(position, position + size));
    position += size;
  }
  return walker.finish();
};

// The totals are sums of the same doubles in the same order as the server's, so they
// match exactly; the tolerance only keeps a harmless last-digit difference from failing
// a test that is about the walk, not about floating point.
const TOLERANCE = 1e-6;

const expectSameEvidence = (actual: unknown, expected: unknown, path = 'evidence'): void => {
  if (typeof expected === 'number') {
    expect(typeof actual, path).toBe('number');
    expect(Math.abs((actual as number) - expected), path).toBeLessThanOrEqual(TOLERANCE);
  } else if (Array.isArray(expected)) {
    expect(Array.isArray(actual), path).toBe(true);
    expect((actual as unknown[]).length, path).toBe(expected.length);
    expected.forEach((item, index) => expectSameEvidence((actual as unknown[])[index], item, `${path}[${index}]`));
  } else if (expected !== null && typeof expected === 'object') {
    expect(Object.keys(actual as object).sort(), path).toEqual(Object.keys(expected).sort());
    for (const [key, value] of Object.entries(expected)) {
      expectSameEvidence((actual as Record<string, unknown>)[key], value, `${path}.${key}`);
    }
  } else {
    expect(actual, path).toBe(expected);
  }
};

const streamOf = (bytes: Uint8Array<ArrayBuffer>, sizes: number[]): ReadableStream<Uint8Array<ArrayBuffer>> => {
  let position = 0;
  let step = 0;
  return new ReadableStream({
    pull(controller) {
      if (position >= bytes.length) {
        controller.close();
        return;
      }
      const size = sizes[step % sizes.length];
      step += 1;
      controller.enqueue(bytes.slice(position, position + size));
      position += size;
    },
  });
};

describe('toolpath walker against the shared fixture', () => {
  it('reads the fixture exactly as the backend does', () => {
    expect(fixtureGcode).toContain('\r\n');
    expect(/(?<!\r)\n/.test(fixtureGcode)).toBe(true);

    expectSameEvidence(walk(fixtureGcode), EXPECTED);
  });

  it('gives the same result whatever way the stream is cut, including inside CRLF pairs', () => {
    for (const sizes of [[1], [2], [3], [5, 1, 7], [64], [127, 3], [1000]]) {
      expectSameEvidence(walk(fixtureGcode, sizes), EXPECTED, `chunks ${sizes.join(',')}`);
    }
    // One cut at every offset of the fixture, so each line end meets a boundary.
    for (let cut = 1; cut < fixtureGcode.length; cut += 1) {
      const walker = new ToolpathWalker();
      walker.push(fixtureGcode.slice(0, cut));
      walker.push(fixtureGcode.slice(cut));
      expectSameEvidence(walker.finish(), EXPECTED, `cut at ${cut}`);
    }
  });

  it('reads bytes cut inside a multi-byte character and inside a line end', async () => {
    const text = fixtureGcode
      .replace(/Cube_id_0/g, 'Деталь_id_0')
      .replace(/Cube_id_1/g, 'Крышка_id_1');
    const expected = walk(text);
    expect(expected.object_names).toContain('Деталь_id_0');

    for (const sizes of [[1], [3], [2, 5, 1]]) {
      const evidence = await walkGcodeStream(streamOf(new Uint8Array(encoder.encode(text)), sizes));
      expectSameEvidence(evidence, expected, `byte chunks ${sizes.join(',')}`);
    }
  });

  it('reads a whole file given to the reader and returns the JSON the server expects', async () => {
    const file = new File([encoder.encode(fixtureGcode)], 'toolpath.gcode');
    const progress: number[] = [];

    const json = await readGcodeToolpath(file, { onProgress: (fraction) => progress.push(fraction) });

    expectSameEvidence(JSON.parse(json), EXPECTED);
    expect(progress.at(-1)).toBe(1);
  });

  it('reads a gzip-compressed file the same way', async () => {
    const gzipped = new Response(
      new Blob([encoder.encode(fixtureGcode)]).stream().pipeThrough(new CompressionStream('gzip')),
    );
    const file = new File([await gzipped.arrayBuffer()], 'toolpath.gcode.gz');

    expectSameEvidence(JSON.parse(await readGcodeToolpath(file)), EXPECTED);
  });
});

describe('toolpath walker against the Bambu-style fixture', () => {
  const expected = JSON.parse(bambuEvidence) as ToolpathEvidence;

  it('reads FEATURE roles and labelled objects exactly as the backend does', () => {
    expect(bambuGcode).toContain('M624');
    expect(bambuGcode).toContain('\r\n');

    expectSameEvidence(walk(bambuGcode), expected);
    expect(expected.object_names).toContain('label 31');
    expect(expected.support_roles).toEqual(['support', 'support interface']);
  });

  it('gives the same result however the file is cut', () => {
    for (const sizes of [[1], [2], [3], [7, 1, 11], [64]]) {
      expectSameEvidence(walk(bambuGcode, sizes), expected, `chunks ${sizes.join(',')}`);
    }
    for (let cut = 1; cut < bambuGcode.length; cut += 1) {
      const walker = new ToolpathWalker();
      walker.push(bambuGcode.slice(0, cut));
      walker.push(bambuGcode.slice(cut));
      expectSameEvidence(walker.finish(), expected, `cut at ${cut}`);
    }
  });

  it('takes the object name from the end of its first block and keeps it', () => {
    const evidence = walk([
      'M83',
      '; start printing object, unique label id: 5',
      '; FEATURE: Outer wall',
      'G1 E1',
      '; stop printing object First id:1 copy 0',
      '; stop printing object, unique label id: 5',
      '; start printing object, unique label id: 5',
      'G1 E1',
      '; stop printing object Second id:2 copy 0',
      '; stop printing object, unique label id: 5',
      '; stop printing object Outside id:3 copy 0',
      'G1 E1',
      '',
    ].join('\n'));

    expect(evidence.extrusion_by_tool_object['0']).toEqual({ First_id_1_copy_0: 2 });
    expect(evidence.object_names).toEqual(['First_id_1_copy_0']);
    expect(evidence.extrusion_by_tool_role['0']).toEqual({ 'outer wall': 3 });
  });

  it('refuses more labelled objects than the server accepts, and names that are too long', () => {
    const labels = Array.from(
      { length: TOOLPATH_LIMITS.objects + 1 },
      (_, index) => `; start printing object, unique label id: ${index}`,
    ).join('\n');
    expect(() => walk(labels)).toThrow(ToolpathLimitError);

    const longName = 'x'.repeat(TOOLPATH_LIMITS.nameChars);
    expect(() => walk([
      '; start printing object, unique label id: 1',
      `; stop printing object ${longName} id:1 copy 0`,
    ].join('\n'))).toThrow(ToolpathLimitError);
  });
});

describe('toolpath walker line handling', () => {
  const moves = (separator: string) =>
    ['M83', ';TYPE:Outer wall', 'G1 X1 E1', 'G1 X2 E2', ';TYPE:Brim', 'G1 X3 E0.5'].join(separator);

  it('ends a line wherever the server does', () => {
    const expected = walk(moves('\n'));
    expect(expected.extrusion_by_tool_role['0']).toEqual({ 'outer wall': 3, brim: 0.5 });

    for (const separator of ['\r\n', '\r', '\v', '\f', '\x1c', '\x1e', '\x85', ' ', ' ']) {
      expectSameEvidence(walk(moves(separator)), expected, JSON.stringify(separator));
    }
  });

  it('reads a last line that has no line end, and a lone carriage return at the very end', () => {
    expect(walk('M83\nG1 X1 E2').extrusion_by_tool_role['0']).toEqual({ unclassified: 2 });
    expect(walk('M83\nG1 X1 E2\r').extrusion_by_tool_role['0']).toEqual({ unclassified: 2 });
    expect(walk('').extrusion_by_tool_role).toEqual({});
  });

  it('counts a tool change only between two different tools', () => {
    const evidence = walk('T0\nT0\nT1\nT1 ; again\nT0\nT0X\nTOOL\n');

    expect(evidence.observed_toolchange_count).toBe(2);
    expect(evidence.observed_tool).toBe(0);
  });

  it('does not treat G10, G92 text or a comment as an extrusion move', () => {
    const evidence = walk('M83\nG10 E5\nG1 X1 ; E7\nG1 F900\nG92.1 E3\nG920 E4\nG1 X1 E1\n');

    expect(evidence.extrusion_by_tool_role['0']).toEqual({ unclassified: 1 });
  });

  it('recovers a retraction before it counts anything as material', () => {
    const evidence = walk('M83\nG1 E-1\nG1 E0.4\nG1 E0.9\n');

    expect(evidence.extrusion_by_tool_role['0'].unclassified).toBeCloseTo(0.3, 9);
  });

  it('keeps absolute extrusion per tool across tool changes', () => {
    const evidence = walk('M82\nT0\nG1 E5\nT1\nG1 E2\nT0\nG1 E7\nT1\nG92 E0\nG1 E1\n');

    expect(evidence.extrusion_by_tool_role).toEqual({
      '0': { unclassified: 7 },
      '1': { unclassified: 3 },
    });
  });
});

describe('toolpath summary limits', () => {
  const rolesOf = (count: number) =>
    Array.from({ length: count }, (_, index) => `;TYPE:role ${index}\nG1 E1`).join('\n');

  it('refuses what the server would refuse', () => {
    const { rolesPerTool, objects, nameChars, toolIndex } = TOOLPATH_LIMITS;
    const attempts: Array<[string, string, string]> = [
      ['M83\n' + rolesOf(rolesPerTool + 1), 'roles', 'roles of one tool'],
      [
        Array.from({ length: objects + 1 }, (_, index) => `EXCLUDE_OBJECT_DEFINE NAME=o${index}`).join('\n'),
        'objects',
        'defined objects',
      ],
      [`M83\n;TYPE:${'x'.repeat(nameChars + 1)}\nG1 E1`, 'name', 'role name'],
      [`T${toolIndex + 1}`, 'tool_index', 'tool index'],
      ['M83\nG1 E' + '9'.repeat(400), 'value', 'overflowing amount'],
    ];

    for (const [text, reason, label] of attempts) {
      expect(() => walk(text), label).toThrow(ToolpathLimitError);
      try {
        walk(text);
      } catch (error) {
        expect((error as ToolpathLimitError).reason, label).toBe(reason);
      }
    }
  });

  it('accepts exactly the limits', () => {
    expect(Object.keys(walk('M83\n' + rolesOf(TOOLPATH_LIMITS.rolesPerTool)).extrusion_by_tool_role['0']))
      .toHaveLength(TOOLPATH_LIMITS.rolesPerTool);
    expect(() => walk(`T${TOOLPATH_LIMITS.toolIndex}`)).not.toThrow();
  });

  it('refuses a summary over the size the server accepts', () => {
    const names = Array.from(
      { length: TOOLPATH_LIMITS.objects },
      (_, index) => `${String(index).padStart(4, '0')}${'n'.repeat(TOOLPATH_LIMITS.nameChars - 4)}`,
    );
    const heavy: ToolpathEvidence = {
      ...EXPECTED,
      object_names: names,
      extrusion_by_tool_object: { '0': Object.fromEntries(names.map((name) => [name, 1])) },
    };

    expect(() => serializeToolpath(heavy)).toThrow(ToolpathLimitError);
    expect(() => serializeToolpath({ ...heavy, extrusion_by_tool_object: {} })).not.toThrow();
    expect(() => serializeToolpath(EXPECTED)).not.toThrow();
  });

  it('refuses one line that is longer than memory may hold', () => {
    const walker = new ToolpathWalker();
    const piece = 'x'.repeat(1024 * 1024);

    expect(() => {
      for (let index = 0; index < 5; index += 1) walker.push(piece);
    }).toThrow(ToolpathLimitError);
  });
});

describe('toolpath walker on a large file', () => {
  it('walks a file far larger than any buffer in constant memory', async () => {
    // About 30 MB, generated chunk by chunk and never held whole.
    const unit = [
      'M83',
      'EXCLUDE_OBJECT_START NAME=Part_id_0',
      ';TYPE:Outer wall',
      ...Array.from({ length: 200 }, (_, index) => `G1 X${index}.123 Y${index}.456 E0.0123 F1800`),
      'EXCLUDE_OBJECT_END',
      ';TYPE:Sparse infill',
      ...Array.from({ length: 100 }, (_, index) => `G1 X${index}.5 Y${index}.5 E0.02`),
      '',
    ].join('\r\n');
    const unitBytes = new Uint8Array(encoder.encode(unit));
    const repeats = Math.ceil((30 * 1024 * 1024) / unitBytes.length);
    let produced = 0;
    const stream = new ReadableStream<Uint8Array<ArrayBuffer>>({
      pull(controller) {
        if (produced === repeats) {
          controller.close();
          return;
        }
        produced += 1;
        controller.enqueue(unitBytes.slice());
      },
    });
    const memory = (globalThis as unknown as { process: { memoryUsage: () => { heapUsed: number } } }).process;
    const before = memory.memoryUsage().heapUsed;
    let peak = before;
    const sampler = setInterval(() => { peak = Math.max(peak, memory.memoryUsage().heapUsed); }, 20);

    const evidence = await walkGcodeStream(stream);
    clearInterval(sampler);

    const role = evidence.extrusion_by_tool_role['0'];
    expect(role['outer wall']).toBeCloseTo(repeats * 200 * 0.0123, 3);
    expect(role['sparse infill']).toBeCloseTo(repeats * 100 * 0.02, 3);
    expect(evidence.extrusion_by_tool_object['0']['Part_id_0']).toBeCloseTo(repeats * 200 * 0.0123, 3);
    // Holding the file would take 30 MB of buffers plus its text; the walk takes a few chunks.
    expect(peak - before).toBeLessThan(25 * 1024 * 1024);
  }, 60_000);
});
