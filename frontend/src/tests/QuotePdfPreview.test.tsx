import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { QuotePdfPreview } from '../components/QuotePdfPreview';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => ({
    'crmWorkspace.actions.pdfPreview': 'PDF preview',
    'crmWorkspace.actions.closePreview': 'Close preview',
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
});
