import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { WikiMarkdownEditor } from './WikiMarkdownEditor';

const { uploadMediaMock } = vi.hoisted(() => ({ uploadMediaMock: vi.fn() }));

vi.mock('../../api/client', () => ({
  wikiAPI: {
    uploadMedia: uploadMediaMock,
  },
}));

vi.mock('../Toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

function EditorHarness({ initialValue = 'selected text' }: { initialValue?: string }) {
  const [value, setValue] = useState(initialValue);
  return <WikiMarkdownEditor value={value} onChange={setValue} placeholder="Article body" />;
}

describe('WikiMarkdownEditor', () => {
  beforeEach(() => {
    uploadMediaMock.mockReset();
  });

  it('wraps the selected text with Markdown formatting', () => {
    render(<EditorHarness />);
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    textarea.setSelectionRange(0, textarea.value.length);

    fireEvent.click(screen.getByRole('button', { name: 'wikiAuthoring.toolbar.bold' }));

    expect(textarea.value).toBe('**selected text**');
  });

  it('indents selected lines without deleting their contents', () => {
    render(<EditorHarness initialValue={'first line\nsecond line'} />);
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    textarea.setSelectionRange(0, textarea.value.length);

    fireEvent.keyDown(textarea, { key: 'Tab' });

    expect(textarea.value).toBe('  first line\n  second line');
  });

  it('adds line-based formatting at the beginning of the current line', () => {
    render(<EditorHarness initialValue="hello world" />);
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    textarea.setSelectionRange(6, textarea.value.length);

    fireEvent.click(screen.getByRole('button', { name: 'wikiAuthoring.toolbar.heading2' }));

    expect(textarea.value).toBe('## hello world');
  });

  it('uploads a selected image and inserts the managed Markdown URL', async () => {
    uploadMediaMock.mockResolvedValue({
      id: 'a'.repeat(32),
      url: `/api/v1/wiki/media/${'a'.repeat(32)}.webp`,
      mime_type: 'image/webp',
      width: 1200,
      height: 800,
      size_bytes: 12345,
    });
    render(<EditorHarness initialValue="Intro" />);
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);

    fireEvent.click(screen.getByRole('button', { name: 'wikiAuthoring.toolbar.image' }));
    const input = screen.getByLabelText('wikiAuthoring.imageFileInput');
    const file = new File(['image'], 'print-result.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(textarea.value).toContain(
        `![print-result](/api/v1/wiki/media/${'a'.repeat(32)}.webp)`,
      );
    });
    expect(uploadMediaMock).toHaveBeenCalledWith(file);
  });

  it('rejects an oversized image before sending it to the API', () => {
    render(<EditorHarness />);
    fireEvent.click(screen.getByRole('button', { name: 'wikiAuthoring.toolbar.image' }));
    const input = screen.getByLabelText('wikiAuthoring.imageFileInput');
    const file = new File([new Uint8Array(8 * 1024 * 1024 + 1)], 'huge.png', {
      type: 'image/png',
    });
    fireEvent.change(input, { target: { files: [file] } });

    expect(uploadMediaMock).not.toHaveBeenCalled();
  });
});
