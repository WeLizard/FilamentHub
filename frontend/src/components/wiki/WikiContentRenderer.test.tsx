import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { WikiContentRenderer } from './WikiContentRenderer';
import { extractHeadings } from './wikiHeadings';

const { getMediaBlobMock } = vi.hoisted(() => ({ getMediaBlobMock: vi.fn() }));

vi.mock('../../api/client', () => ({
  wikiAPI: {
    getMediaBlob: getMediaBlobMock,
  },
}));

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    run: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock('react-syntax-highlighter', () => ({
  Prism: ({ children }: { children: ReactNode }) => <pre>{children}</pre>,
}));

vi.mock('react-syntax-highlighter/dist/esm/styles/prism', () => ({
  vscDarkPlus: {},
}));

describe('WikiContentRenderer', () => {
  beforeEach(() => {
    window.localStorage.clear();
    getMediaBlobMock.mockReset();
  });

  it('preserves authored task state and persists a reader override', () => {
    const { unmount } = render(
      <WikiContentRenderer
        content={'- [x] Calibrated\n- [ ] Printed'}
        taskStorageKey="wiki-task-test"
      />,
    );

    const calibrated = screen.getByRole('checkbox', { name: 'Calibrated' });
    const printed = screen.getByRole('checkbox', { name: 'Printed' });
    expect(calibrated).toBeChecked();
    expect(printed).not.toBeChecked();

    fireEvent.click(printed);
    expect(printed).toBeChecked();
    unmount();

    render(
      <WikiContentRenderer
        content={'- [x] Calibrated\n- [ ] Printed'}
        taskStorageKey="wiki-task-test"
      />,
    );
    expect(screen.getByRole('checkbox', { name: 'Printed' })).toBeChecked();
  });

  it('keeps inline code inside a paragraph instead of rendering a block highlighter', () => {
    const { container } = render(
      <WikiContentRenderer content={'Choose `PLA` for the first print.'} />,
    );

    const code = screen.getByText('PLA');
    expect(code.tagName).toBe('CODE');
    expect(code.closest('p')).not.toBeNull();
    expect(container.querySelector('p pre')).toBeNull();
    expect(container.querySelector('p div')).toBeNull();
  });

  it('renders a plain fenced example with one stable code frame', () => {
    const { container } = render(
      <WikiContentRenderer content={'```text\nNorthLayer PETG Polar Blue\n```'} />,
    );

    const code = screen.getByText('NorthLayer PETG Polar Blue');
    expect(code.tagName).toBe('CODE');
    expect(code.closest('pre')).not.toBeNull();
    expect(container.querySelectorAll('pre')).toHaveLength(1);
    expect(container.querySelector('pre pre')).toBeNull();
  });

  it('loads staged managed media through the authenticated API in private previews', async () => {
    const objectUrl = 'blob:wiki-preview';
    getMediaBlobMock.mockResolvedValue(new Blob(['webp'], { type: 'image/webp' }));
    vi.spyOn(URL, 'createObjectURL').mockReturnValue(objectUrl);
    const revokeObjectUrl = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);

    const mediaUrl = `/api/v1/wiki/media/${'a'.repeat(32)}.webp`;
    const { unmount } = render(
      <WikiContentRenderer
        content={`![Print result](${mediaUrl})`}
        privateMedia
      />,
    );

    await waitFor(() => expect(screen.getByRole('img', { name: 'Print result' })).toHaveAttribute('src', objectUrl));
    expect(getMediaBlobMock).toHaveBeenCalledWith(mediaUrl);

    unmount();
    expect(revokeObjectUrl).toHaveBeenCalledWith(objectUrl);
  });

  it('assigns stable unique heading ids shared with the table of contents', () => {
    const content = '## Что это?\n\n## Что это?\n\n## 配置\n\n## 配置';
    const expectedIds = extractHeadings(content).map(({ id }) => id);
    const { container } = render(<WikiContentRenderer content={content} />);

    expect(expectedIds).toEqual(['что-это', 'что-это-2', '配置', '配置-2']);
    expect(
      Array.from(container.querySelectorAll('h2')).map((heading) => heading.id),
    ).toEqual(expectedIds);
  });

  it('ignores markdown-looking headings inside fenced code blocks', () => {
    const content = '```md\n## Not a heading\n```\n\nActual heading\n---';

    expect(extractHeadings(content)).toEqual([
      expect.objectContaining({ id: 'actual-heading', level: 2, sourceLine: 5 }),
    ]);
  });
});
