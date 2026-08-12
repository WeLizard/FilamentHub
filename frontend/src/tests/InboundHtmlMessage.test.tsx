import { render, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { InboundHtmlMessage } from '../components/admin/AdminCommunications';
import { adminCommunicationsAPI } from '../api/client';
import type { EmailAttachment } from '../types/api';

const LETTER = '<p>Hi</p><blockquote>quoted</blockquote><script>document.title="XSS"</script>';

const inlineImage: EmailAttachment = {
  index: 0,
  filename: 'signature.png',
  content_type: 'application/octet-stream',
  size: 12,
  downloadable: true,
  content_id: 'img001',
  inline: true,
};

describe('InboundHtmlMessage', () => {
  it('renders the letter inside a frame', async () => {
    const { container } = render(<InboundHtmlMessage html={LETTER} />);
    const frame = container.querySelector('iframe');

    expect(frame).not.toBeNull();
    expect(frame?.getAttribute('srcdoc')).toContain('quoted');
    await waitFor(() => expect(frame?.style.height).toBe('24px'));
  });

  it('never lets a letter run scripts', async () => {
    const { container } = render(<InboundHtmlMessage html={LETTER} />);
    const frame = container.querySelector('iframe');
    const sandbox = frame?.getAttribute('sandbox');

    // Mail comes from strangers. Granting allow-scripts here would turn every
    // received letter into arbitrary code running in the admin panel.
    expect(sandbox).toBeDefined();
    expect(sandbox).not.toContain('allow-scripts');
    expect(sandbox).not.toContain('allow-top-navigation');
    await waitFor(() => expect(frame?.style.height).toBe('24px'));
  });

  it('shows an image the letter refers to by its internal name', async () => {
    const download = vi
      .spyOn(adminCommunicationsAPI, 'downloadEmailAttachment')
      .mockResolvedValue(new Blob(['image-bytes'], { type: 'image/png' }));

    const { container } = render(
      <InboundHtmlMessage
        html={'<p>Look</p><img src="cid:img001">'}
        threadId={7}
        messageId={11}
        attachments={[inlineImage]}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('iframe')?.getAttribute('srcdoc')).toContain(
        'src="data:image/png;base64,',
      );
    });
    expect(download).toHaveBeenCalledWith(7, 11, 0);
    download.mockRestore();
  });

  it('leaves the letter readable when the image cannot be fetched', async () => {
    const download = vi
      .spyOn(adminCommunicationsAPI, 'downloadEmailAttachment')
      .mockRejectedValue(new Error('gone'));

    const { container } = render(
      <InboundHtmlMessage
        html={'<p>Look</p><img src="cid:img001">'}
        threadId={7}
        messageId={11}
        attachments={[inlineImage]}
      />,
    );

    await waitFor(() => expect(download).toHaveBeenCalled());
    expect(container.querySelector('iframe')?.getAttribute('srcdoc')).toContain('Look');
    download.mockRestore();
  });

  it('does not reuse an inline image after switching to another message', async () => {
    const download = vi
      .spyOn(adminCommunicationsAPI, 'downloadEmailAttachment')
      .mockResolvedValue(new Blob(['image-bytes'], { type: 'image/png' }));

    const { container, rerender } = render(
      <InboundHtmlMessage
        html={'<p>Look</p><img src="cid:img001">'}
        threadId={7}
        messageId={11}
        attachments={[inlineImage]}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('iframe')?.getAttribute('srcdoc')).toContain(
        'src="data:image/png;base64,',
      );
    });

    rerender(
      <InboundHtmlMessage
        html={'<p>Look</p><img src="cid:img001">'}
        threadId={7}
        messageId={12}
        attachments={[]}
      />,
    );

    expect(container.querySelector('iframe')?.getAttribute('srcdoc')).toContain(
      'src="cid:img001"',
    );
    download.mockRestore();
  });

  it('does not embed a downloaded inline file that is not a safe raster image', async () => {
    const download = vi
      .spyOn(adminCommunicationsAPI, 'downloadEmailAttachment')
      .mockResolvedValue(new Blob(['<svg></svg>'], { type: 'image/svg+xml' }));

    const { container } = render(
      <InboundHtmlMessage
        html={'<p>Look</p><img src="cid:img001">'}
        threadId={7}
        messageId={11}
        attachments={[inlineImage]}
      />,
    );

    await waitFor(() => expect(download).toHaveBeenCalled());
    expect(container.querySelector('iframe')?.getAttribute('srcdoc')).toContain(
      'src="cid:img001"',
    );
    download.mockRestore();
  });
});
