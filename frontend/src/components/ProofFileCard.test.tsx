import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ProofFileCard } from './ProofFileCard';
import { proofFilesAPI } from '../api/client';

vi.mock('../api/client', () => ({
  proofFilesAPI: {
    getObjectUrl: vi.fn(),
    download: vi.fn(),
  },
}));

class FakeIntersectionObserver {
  static instances: FakeIntersectionObserver[] = [];

  readonly observe = vi.fn();
  readonly disconnect = vi.fn();

  constructor(
    readonly callback: IntersectionObserverCallback,
    readonly options?: IntersectionObserverInit,
  ) {
    FakeIntersectionObserver.instances.push(this);
  }
}

describe('ProofFileCard', () => {
  beforeEach(() => {
    FakeIntersectionObserver.instances = [];
    vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver);
    vi.mocked(proofFilesAPI.getObjectUrl).mockReset();
    vi.mocked(proofFilesAPI.download).mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('waits until an image card approaches the viewport before downloading its preview', async () => {
    vi.mocked(proofFilesAPI.getObjectUrl).mockResolvedValue('blob:proof-preview');

    render(
      <ProofFileCard
        filePath="brand_requests/5/proof.png"
        fileName="proof.png"
        imageErrorText="Preview failed"
      />,
    );

    expect(proofFilesAPI.getObjectUrl).not.toHaveBeenCalled();
    expect(FakeIntersectionObserver.instances).toHaveLength(1);
    expect(FakeIntersectionObserver.instances[0].options).toEqual({ rootMargin: '240px 0px' });

    act(() => {
      FakeIntersectionObserver.instances[0].callback(
        [{ isIntersecting: true } as IntersectionObserverEntry],
        FakeIntersectionObserver.instances[0] as unknown as IntersectionObserver,
      );
    });

    await waitFor(() => {
      expect(proofFilesAPI.getObjectUrl).toHaveBeenCalledWith('brand_requests/5/proof.png');
    });
    expect(await screen.findByRole('img', { name: 'proof.png' })).toHaveAttribute(
      'src',
      'blob:proof-preview',
    );
  });

  it('does not observe or fetch non-image attachments', () => {
    render(
      <ProofFileCard
        filePath="brand_requests/5/proof.pdf"
        fileName="proof.pdf"
        imageErrorText="Preview failed"
      />,
    );

    expect(FakeIntersectionObserver.instances).toHaveLength(0);
    expect(proofFilesAPI.getObjectUrl).not.toHaveBeenCalled();
  });
});
