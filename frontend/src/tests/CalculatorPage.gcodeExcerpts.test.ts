import { describe, expect, it, vi } from 'vitest';
import type { TFunction } from 'i18next';

import type { CalculatorGcodeParseResponse } from '../types/api';
import type { GcodeExcerpt } from '../utils/gcodeExcerpt';
import { GcodeExcerptError } from '../utils/gcodeExcerpt';
import {
  getGcodeProcessingPercent,
  parseGcodeFilesFromExcerpts,
  resolveGcodeParseError,
  runForCurrentGcodeOperation,
  type GcodeBatchRun,
  type GcodeProcessingProgress,
} from '../pages/CalculatorPage';

const excerptFor = (file: File): GcodeExcerpt => ({
  fileName: file.name,
  fileSizeBytes: file.size,
  container: 'plain_gcode',
  parts: [{ field: 'head', blob: new Blob(['; total filament used [g] = 1']), filename: 'head.gcode' }],
});

const summaryJob = (fileName: string): CalculatorGcodeParseResponse => ({
  file_name: fileName,
  file_size_bytes: 70_000_000,
  detail_level: 'summary',
  object_groups: [],
  materials: [],
});

const apiError = (code: string) => ({ response: { status: 400, data: { detail: { code } } } });

const run = (overrides: Partial<GcodeBatchRun> & { files: File[] }): GcodeBatchRun => ({
  signal: new AbortController().signal,
  buildExcerpt: vi.fn(async (file: File) => excerptFor(file)),
  parseExcerpt: vi.fn(async (excerpt: GcodeExcerpt) => ({ jobs: [summaryJob(excerpt.fileName)] })),
  onProgress: vi.fn(),
  ensureCurrent: vi.fn(),
  ...overrides,
});

// Wraps the key so a present translation differs from the missing-key fallback path.
const t = ((key: string) => `T[${key}]`) as TFunction;

describe('G-code summary parsing without uploading the file', () => {
  it('sends only the excerpt of each file and keeps one job key per file', async () => {
    const first = new File(['a'], 'one.gcode');
    const second = new File(['b'], 'two.gcode');
    const parseExcerpt = vi.fn(async (excerpt: GcodeExcerpt) => ({
      jobs: [summaryJob(excerpt.fileName)],
    }));
    const onProgress = vi.fn();

    const result = await parseGcodeFilesFromExcerpts(
      run({ files: [first, second], parseExcerpt, onProgress }),
    );

    expect(parseExcerpt.mock.calls.map(([excerpt]) => excerpt.fileName)).toEqual([
      'one.gcode',
      'two.gcode',
    ]);
    expect(result.failedFiles).toEqual([]);
    expect(result.jobs.map((job) => job.key)).toEqual([
      '0:one.gcode:70000000:0',
      '1:two.gcode:70000000:0',
    ]);
    expect(onProgress.mock.calls.map(([progress]) => (
      `${progress.phase}:${progress.processedFiles}/${progress.totalFiles}`
    ))).toEqual(['reading:0/2', 'analyzing:0/2', 'reading:1/2', 'analyzing:1/2']);
  });

  it('keeps going after one file fails and reports it as a partial result', async () => {
    const files = [new File(['a'], 'bad.gcode'), new File(['b'], 'good.gcode')];
    const parseExcerpt = vi.fn(async (excerpt: GcodeExcerpt) => {
      if (excerpt.fileName === 'bad.gcode') throw apiError('ERR_GCODE_PARSE_FAILED');
      return { jobs: [summaryJob(excerpt.fileName)] };
    });

    const result = await parseGcodeFilesFromExcerpts(run({ files, parseExcerpt }));

    expect(result.failedFiles).toEqual(['bad.gcode']);
    expect(result.jobs).toHaveLength(1);
  });

  it('shows one clear message when the only file has no slicer summary', async () => {
    const files = [new File(['a'], 'no-summary.gcode')];
    const parseExcerpt = vi.fn().mockRejectedValue(apiError('ERR_GCODE_PARSE_FAILED'));

    const failure = await parseGcodeFilesFromExcerpts(run({ files, parseExcerpt }))
      .catch((error: unknown) => error);

    expect(resolveGcodeParseError(failure, t)).toBe('T[apiErrors.ERR_GCODE_PARSE_FAILED]');
  });

  it('shows the file-reading reason when the browser rejects the file itself', async () => {
    const files = [new File(['a'], 'broken.gcode.3mf')];
    const buildExcerpt = vi.fn().mockRejectedValue(new GcodeExcerptError('ERR_GCODE_EXCERPT_INVALID'));

    const failure = await parseGcodeFilesFromExcerpts(run({ files, buildExcerpt }))
      .catch((error: unknown) => error);

    expect(resolveGcodeParseError(failure, t)).toBe('T[apiErrors.ERR_GCODE_EXCERPT_INVALID]');
  });

  it('falls back to the generic message when files fail for different reasons', async () => {
    const files = [new File(['a'], 'a.gcode'), new File(['b'], 'b.gcode')];
    const parseExcerpt = vi.fn()
      .mockRejectedValueOnce(apiError('ERR_GCODE_PARSE_FAILED'))
      .mockRejectedValueOnce(apiError('ERR_GCODE_EXCERPT_TOO_LARGE'));

    const failure = await parseGcodeFilesFromExcerpts(run({ files, parseExcerpt }))
      .catch((error: unknown) => error);

    expect(resolveGcodeParseError(failure, t)).toBe('T[profilePage.calculator.batchParseAllFailed]');
  });

  it('stops without parsing further files once the run is cancelled', async () => {
    const files = [new File(['a'], 'a.gcode'), new File(['b'], 'b.gcode')];
    const controller = new AbortController();
    const parseExcerpt = vi.fn(async (excerpt: GcodeExcerpt) => {
      controller.abort();
      return { jobs: [summaryJob(excerpt.fileName)] };
    });
    const ensureCurrent = vi.fn(() => {
      if (controller.signal.aborted) throw new DOMException('canceled', 'AbortError');
    });

    await expect(parseGcodeFilesFromExcerpts(run({
      files,
      signal: controller.signal,
      parseExcerpt,
      ensureCurrent,
    }))).rejects.toMatchObject({ name: 'AbortError' });
    expect(parseExcerpt).toHaveBeenCalledTimes(1);
    expect(resolveGcodeParseError(new DOMException('canceled', 'AbortError'), t)).toBeNull();
  });
});

describe('G-code operation progress fencing', () => {
  it('ignores progress, result, and finally work from an operation replaced by a newer one', () => {
    let visible = 'new run';
    const staleToken = 4;
    const currentToken = 5;

    expect(runForCurrentGcodeOperation(staleToken, currentToken, () => {
      visible = 'stale progress';
    })).toBe(false);
    expect(runForCurrentGcodeOperation(staleToken, currentToken, () => {
      visible = 'stale result';
    })).toBe(false);
    expect(runForCurrentGcodeOperation(staleToken, currentToken, () => {
      visible = 'stale finally';
    })).toBe(false);
    expect(visible).toBe('new run');

    expect(runForCurrentGcodeOperation(currentToken, currentToken, () => {
      visible = 'current result';
    })).toBe(true);
    expect(visible).toBe('current result');
  });

  it('treats cancellation as a generation change that fences late callbacks', () => {
    const runningToken = 8;
    const tokenAfterCancel = runningToken + 1;
    const callback = vi.fn();

    runForCurrentGcodeOperation(runningToken, tokenAfterCancel, callback);

    expect(callback).not.toHaveBeenCalled();
  });

  it('moves a file through reading, counting by bytes read, and analysis', () => {
    const progress = (
      phase: GcodeProcessingProgress['phase'],
      processedFiles: number,
      countedFraction?: number,
    ): GcodeProcessingProgress => ({
      phase,
      processedFiles,
      totalFiles: 4,
      currentFileName: 'one.gcode',
      countedFraction,
    });

    expect(getGcodeProcessingPercent(null)).toBeNull();
    expect(getGcodeProcessingPercent(progress('reading', 0))).toBe(0);
    expect(getGcodeProcessingPercent(progress('counting', 0, 0))).toBe(3);
    expect(getGcodeProcessingPercent(progress('counting', 0, 0.5))).toBe(13);
    expect(getGcodeProcessingPercent(progress('counting', 0, 1))).toBe(23);
    expect(getGcodeProcessingPercent(progress('counting', 0, 7))).toBe(23);
    expect(getGcodeProcessingPercent(progress('analyzing', 0))).toBe(23);
    expect(getGcodeProcessingPercent(progress('reading', 2))).toBe(50);
    expect(getGcodeProcessingPercent(progress('analyzing', 3))).toBe(98);
  });
});

describe('counting the parts of a file in the browser', () => {
  const countedRun = (overrides: Partial<GcodeBatchRun> & { files: File[] }) => run({
    buildToolpath: vi.fn(async () => '{"version":1}'),
    ...overrides,
  });

  it('sends the counted parts with the excerpt and reports each phase', async () => {
    const files = [new File(['a'], 'one.gcode')];
    const buildToolpath = vi.fn(async (
      _file: File,
      _signal: AbortSignal,
      onProgress: (fraction: number) => void,
    ) => {
      onProgress(0.5);
      return '{"version":1,"counted":true}';
    });
    const parseExcerpt = vi.fn(async (excerpt: GcodeExcerpt) => ({
      jobs: [{ ...summaryJob(excerpt.fileName), detail_level: 'full' as const }],
    }));
    const onProgress = vi.fn();

    const result = await parseGcodeFilesFromExcerpts(
      countedRun({ files, buildToolpath, parseExcerpt, onProgress }),
    );

    expect(parseExcerpt.mock.calls[0][0].toolpath).toBe('{"version":1,"counted":true}');
    expect(result.toolpathMissingFiles).toEqual([]);
    expect(onProgress.mock.calls.map(([progress]) => (
      `${progress.phase}:${progress.countedFraction ?? '-'}`
    ))).toEqual(['reading:-', 'counting:0', 'counting:0.5', 'analyzing:-']);
  });

  it('still sends the summary, and says so, when the parts cannot be counted', async () => {
    const files = [new File(['a'], 'one.gcode'), new File(['b'], 'two.gcode')];
    const buildToolpath = vi.fn()
      .mockRejectedValueOnce(new Error('worker_unsupported'))
      .mockResolvedValueOnce('{"version":1}');
    const parseExcerpt = vi.fn(async (excerpt: GcodeExcerpt) => ({
      jobs: [summaryJob(excerpt.fileName)],
    }));

    const result = await parseGcodeFilesFromExcerpts(countedRun({ files, buildToolpath, parseExcerpt }));

    expect(parseExcerpt.mock.calls.map(([excerpt]) => excerpt.toolpath)).toEqual([undefined, '{"version":1}']);
    expect(result.jobs).toHaveLength(2);
    expect(result.failedFiles).toEqual([]);
    expect(result.toolpathMissingFiles).toEqual(['one.gcode']);
  });

  it('retries without the counted parts when the server refuses them', async () => {
    const files = [new File(['a'], 'one.gcode')];
    const parseExcerpt = vi.fn()
      .mockRejectedValueOnce(apiError('ERR_GCODE_EXCERPT_INVALID'))
      .mockResolvedValueOnce({ jobs: [summaryJob('one.gcode')] });

    const result = await parseGcodeFilesFromExcerpts(countedRun({ files, parseExcerpt }));

    expect(parseExcerpt.mock.calls.map(([excerpt]) => excerpt.toolpath)).toEqual(['{"version":1}', undefined]);
    expect(result.jobs).toHaveLength(1);
    expect(result.toolpathMissingFiles).toEqual(['one.gcode']);
  });

  it('does not retry for a failure that has nothing to do with the counted parts', async () => {
    const files = [new File(['a'], 'one.gcode')];
    const parseExcerpt = vi.fn().mockRejectedValue(apiError('ERR_GCODE_PARSE_FAILED'));

    await expect(parseGcodeFilesFromExcerpts(countedRun({ files, parseExcerpt }))).rejects.toBeDefined();

    expect(parseExcerpt).toHaveBeenCalledTimes(1);
  });

  it('stops at once when cancelled while counting, without sending anything', async () => {
    const files = [new File(['a'], 'one.gcode')];
    const controller = new AbortController();
    const buildToolpath = vi.fn(async () => {
      controller.abort();
      throw new DOMException('canceled', 'AbortError');
    });
    const parseExcerpt = vi.fn();
    const ensureCurrent = vi.fn(() => {
      if (controller.signal.aborted) throw new DOMException('canceled', 'AbortError');
    });

    await expect(parseGcodeFilesFromExcerpts(countedRun({
      files,
      signal: controller.signal,
      buildToolpath,
      parseExcerpt,
      ensureCurrent,
    }))).rejects.toMatchObject({ name: 'AbortError' });
    expect(parseExcerpt).not.toHaveBeenCalled();
  });
});
