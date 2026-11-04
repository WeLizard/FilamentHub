import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FeedbackImages } from './FeedbackImages';
import { WikiContentRenderer } from './wiki/WikiContentRenderer';

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), account: 1 }));
vi.mock('../api/client', () => ({ getProtectedImageBlob: mocks.fetch }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: mocks.account } }) }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }) }));

function Surface({ kind, src = '/api/v1/wiki/media/a.webp' }: { kind: 'wiki' | 'feedback'; src?: string }) {
  return kind === 'wiki'
    ? <WikiContentRenderer privateMedia content={`![result](${src})`} />
    : <FeedbackImages attachments={[{ public_id: 'image', url: src, width: 200, height: 100 }]} />;
}

describe('protected images', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.account = 1;
    mocks.fetch.mockReset().mockResolvedValue(new Blob(['image']));
    let index = 0;
    vi.spyOn(URL, 'createObjectURL').mockImplementation(() => `blob:image-${++index}`);
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
  });

  it.each(['wiki', 'feedback'] as const)('%s recovers from HTTP and decoding failure only after a loaded retry', async (kind) => {
    mocks.fetch.mockRejectedValueOnce(new Error('HTTP 403'));
    const { container } = render(<Surface kind={kind} />);
    const retry = await screen.findByRole('button', { name: 'protectedImage.retry' });
    if (kind === 'wiki') expect(container.querySelector('p div')).toBeNull();
    fireEvent.click(retry);
    await waitFor(() => expect(container.querySelector('img')).toHaveAttribute('src', 'blob:image-1'));
    fireEvent.error(container.querySelector('img')!);
    fireEvent.click(await screen.findByRole('button', { name: 'protectedImage.retry' }));
    await waitFor(() => expect(container.querySelector('img')).toHaveAttribute('src', 'blob:image-2'));
    if (kind === 'feedback') expect(screen.getByRole('button', { name: 'feedbackImages.open' })).toBeDisabled();
    fireEvent.load(container.querySelector('img')!);
    expect(screen.queryByText('protectedImage.error')).toBeNull();
    if (kind === 'feedback') {
      const open = screen.getByRole('button', { name: 'feedbackImages.open' });
      expect(open).toBeEnabled();
      fireEvent.click(open);
      expect(screen.getByRole('button', { name: 'feedbackImages.close' })).toBeInTheDocument();
    } else expect(container.querySelector('p div')).toBeNull();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:image-1');
  });

  it('closes the feedback viewer across URL changes and ignores an old image event', async () => {
    const { container, rerender } = render(<Surface kind="feedback" />);
    await waitFor(() => expect(container.querySelector('img')).toHaveAttribute('src', 'blob:image-1'));
    const oldImage = container.querySelector('img')!;
    fireEvent.load(oldImage);
    fireEvent.click(screen.getByRole('button', { name: 'feedbackImages.open' }));
    expect(screen.getByRole('button', { name: 'feedbackImages.close' })).toBeInTheDocument();
    rerender(<Surface kind="feedback" src="/api/v1/feedback/attachments/other.webp" />);
    expect(screen.queryByRole('button', { name: 'feedbackImages.close' })).toBeNull();
    await waitFor(() => expect(container.querySelector('img')).toHaveAttribute('src', 'blob:image-2'));
    fireEvent.load(oldImage);
    expect(screen.getByRole('button', { name: 'feedbackImages.open' })).toBeDisabled();
    fireEvent.load(container.querySelector('img')!);
    expect(screen.queryByRole('button', { name: 'feedbackImages.close' })).toBeNull();
  });

  it('aborts stale fetches, ignores late responses and releases images across URL, account and unmount', async () => {
    let resolve!: (blob: Blob) => void;
    mocks.fetch.mockImplementationOnce(() => new Promise<Blob>((done) => { resolve = done; }));
    const { container, rerender, unmount } = render(<Surface kind="wiki" />);
    const signal = mocks.fetch.mock.calls[0][1] as AbortSignal;
    rerender(<Surface kind="wiki" src="/api/v1/wiki/media/b.webp" />);
    expect(signal.aborted).toBe(true);
    await act(async () => resolve(new Blob(['late'])));
    await waitFor(() => expect(container.querySelector('img')).toHaveAttribute('src', 'blob:image-1'));
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    mocks.account = 2;
    rerender(<Surface kind="wiki" src="/api/v1/wiki/media/b.webp" />);
    expect(container.querySelector('img')).not.toHaveAttribute('src');
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:image-1');
    await waitFor(() => expect(container.querySelector('img')).toHaveAttribute('src', 'blob:image-2'));
    unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:image-2');
    expect((mocks.fetch.mock.calls[2][1] as AbortSignal).aborted).toBe(true);
  });
});
