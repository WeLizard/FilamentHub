import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { WikiMarkdownEditor } from './WikiMarkdownEditor';


vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

function EditorHarness({ initialValue = 'selected text' }: { initialValue?: string }) {
  const [value, setValue] = useState(initialValue);
  return <WikiMarkdownEditor value={value} onChange={setValue} placeholder="Article body" />;
}

describe('WikiMarkdownEditor', () => {
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
});
