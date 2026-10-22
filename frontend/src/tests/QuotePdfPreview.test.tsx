import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import * as pluginBridge from '../utils/pluginBridge';
import { QuotePdfPreview } from '../components/QuotePdfPreview';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => ({
    'crmWorkspace.actions.pdfPreview': 'PDF preview',
    'crmWorkspace.actions.closePreview': 'Close preview',
    'crmWorkspace.actions.openInBrowser': 'Open in browser',
    'crmWorkspace.actions.openInBrowserFailed': 'Could not open',
  }[key] ?? key) }),
}));

describe('quote PDF preview', () => {
  it('keeps a visible close action above the PDF frame and returns through its callback', () => {
    const onClose = vi.fn();
    render(<QuotePdfPreview url="blob:quote-preview" title="QA quote" onClose={onClose} />);

    expect(screen.getByRole('heading', { name: 'PDF preview' })).toBeTruthy();
    expect(screen.getByTitle('QA quote PDF').getAttribute('src')).toBe('blob:quote-preview');
    fireEvent.click(screen.getByRole('button', { name: 'Close preview' }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('offers Open in browser only inside the plugin and reports a failed open', async () => {
    const onOpen = vi.fn().mockResolvedValue(false);
    const embed = vi.spyOn(pluginBridge, 'isPluginEmbed');

    embed.mockReturnValue(false);
    const outside = render(<QuotePdfPreview url="blob:q" title="Q" onClose={vi.fn()} printable onOpenInBrowser={onOpen} />);
    expect(screen.queryByRole('button', { name: 'Open in browser' })).toBeNull();
    outside.unmount();

    embed.mockReturnValue(true);
    render(<QuotePdfPreview url="blob:q" title="Q" onClose={vi.fn()} printable onOpenInBrowser={onOpen} />);
    fireEvent.click(screen.getByRole('button', { name: 'Open in browser' }));
    expect(onOpen).toHaveBeenCalledOnce();
    expect(await screen.findByRole('alert')).toBeTruthy();
    embed.mockRestore();
  });
});
