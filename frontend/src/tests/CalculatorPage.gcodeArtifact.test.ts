import { describe, expect, it, vi } from 'vitest';

import type { GcodeArtifact } from '../api/client';
import {
  getGcodeProcessingPercent,
  isRecoverableGcodeUploadError,
  resolveGcodeArtifactAttempt,
  runForCurrentGcodeOperation,
  uploadGcodeArtifactWithRecovery,
} from '../pages/CalculatorPage';

const readyArtifact = (artifactId: string): GcodeArtifact => ({
  artifact_id: artifactId,
  file_name: 'part.gcode',
  size_bytes: 3,
  sha256: 'abc',
  state: 'ready',
  expires_at: '2026-09-08T12:00:00Z',
});

describe('G-code artifact upload recovery', () => {
  it('recovers an ambiguous lost PUT response through GET with the same operation ID', async () => {
    const file = new File(['G1 X1'], 'part.gcode');
    const artifactId = 'artifact-stable-id';
    const uploadGcodeArtifact = vi.fn().mockRejectedValue({ request: {} });
    const getGcodeArtifact = vi.fn().mockResolvedValue(readyArtifact(artifactId));
    const onRestoring = vi.fn();

    const result = await uploadGcodeArtifactWithRecovery(
      { uploadGcodeArtifact, getGcodeArtifact },
      file,
      artifactId,
      vi.fn(),
      onRestoring,
      new AbortController().signal,
    );

    expect(uploadGcodeArtifact).toHaveBeenCalledWith(
      file,
      artifactId,
      expect.any(Function),
      expect.any(AbortSignal),
    );
    expect(getGcodeArtifact).toHaveBeenCalledWith(artifactId, expect.any(AbortSignal));
    expect(onRestoring).toHaveBeenCalledOnce();
    expect(result).toEqual({ artifact: readyArtifact(artifactId), restored: true });
  });

  it('recovers a completed idempotent PUT reported as a conflict', async () => {
    const artifactId = 'artifact-conflict-id';
    const error = {
      response: { data: { detail: { code: 'ERR_GCODE_ARTIFACT_CONFLICT' } } },
    };
    const transport = {
      uploadGcodeArtifact: vi.fn().mockRejectedValue(error),
      getGcodeArtifact: vi.fn().mockResolvedValue(readyArtifact(artifactId)),
    };

    await expect(uploadGcodeArtifactWithRecovery(
      transport,
      new File(['G1'], 'part.gcode'),
      artifactId,
      vi.fn(),
      vi.fn(),
      new AbortController().signal,
    )).resolves.toMatchObject({ restored: true });

    expect(transport.getGcodeArtifact).toHaveBeenCalledWith(
      artifactId,
      expect.any(AbortSignal),
    );
  });

  it('does not restore deterministic validation failures or cancelled uploads', async () => {
    const validationError = {
      response: { data: { detail: { code: 'ERR_GCODE_TOO_LARGE' } } },
    };
    expect(isRecoverableGcodeUploadError(validationError)).toBe(false);

    const validationTransport = {
      uploadGcodeArtifact: vi.fn().mockRejectedValue(validationError),
      getGcodeArtifact: vi.fn(),
    };
    await expect(uploadGcodeArtifactWithRecovery(
      validationTransport,
      new File(['G1'], 'part.gcode'),
      'validation-id',
      vi.fn(),
      vi.fn(),
      new AbortController().signal,
    )).rejects.toBe(validationError);
    expect(validationTransport.getGcodeArtifact).not.toHaveBeenCalled();

    const abortError = new DOMException('canceled', 'AbortError');
    const cancelledTransport = {
      uploadGcodeArtifact: vi.fn().mockRejectedValue(abortError),
      getGcodeArtifact: vi.fn(),
    };
    await expect(uploadGcodeArtifactWithRecovery(
      cancelledTransport,
      new File(['G1'], 'part.gcode'),
      'cancelled-id',
      vi.fn(),
      vi.fn(),
      new AbortController().signal,
    )).rejects.toBe(abortError);
    expect(cancelledTransport.getGcodeArtifact).not.toHaveBeenCalled();
  });

  it('treats a server failure after PUT as ambiguous and checks the same ID', async () => {
    const artifactId = 'artifact-server-error-id';
    const transport = {
      uploadGcodeArtifact: vi.fn().mockRejectedValue({ response: { status: 502 } }),
      getGcodeArtifact: vi.fn().mockResolvedValue(readyArtifact(artifactId)),
    };

    await expect(uploadGcodeArtifactWithRecovery(
      transport,
      new File(['G1'], 'part.gcode'),
      artifactId,
      vi.fn(),
      vi.fn(),
      new AbortController().signal,
    )).resolves.toMatchObject({ restored: true });
    expect(transport.getGcodeArtifact).toHaveBeenCalledWith(
      artifactId,
      expect.any(AbortSignal),
    );
  });

  it('reuses the preserved operation ID when an ambiguous upload is retried', () => {
    const createId = vi.fn(() => 'new-id');
    const pendingAttempt = { id: 'preserved-id', uploaded: false };

    const retryAttempt = resolveGcodeArtifactAttempt(pendingAttempt, createId);

    expect(retryAttempt).toEqual(pendingAttempt);
    expect(createId).not.toHaveBeenCalled();
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

  it('uses sent bytes for upload, file counts for analysis, and no fake restore percent', () => {
    expect(getGcodeProcessingPercent({
      phase: 'uploading',
      uploadedBytes: 250,
      totalBytes: 1000,
      processedFiles: 0,
      totalFiles: 4,
      currentFileName: 'one.gcode',
    })).toBe(25);
    expect(getGcodeProcessingPercent({
      phase: 'analyzing',
      uploadedBytes: 1000,
      totalBytes: 1000,
      processedFiles: 1,
      totalFiles: 4,
      currentFileName: 'two.gcode',
    })).toBe(25);
    expect(getGcodeProcessingPercent({
      phase: 'restoring',
      uploadedBytes: 250,
      totalBytes: 1000,
      processedFiles: 0,
      totalFiles: 1,
      currentFileName: 'one.gcode',
    })).toBeNull();
  });
});
