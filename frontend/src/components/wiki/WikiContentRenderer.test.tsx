import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { WikiContentRenderer } from './WikiContentRenderer';

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
  beforeEach(() => window.localStorage.clear());

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
});
