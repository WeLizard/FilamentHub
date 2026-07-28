import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { InboundHtmlMessage } from '../components/admin/AdminCommunications';

const LETTER = '<p>Hi</p><blockquote>quoted</blockquote><script>document.title="XSS"</script>';

describe('InboundHtmlMessage', () => {
  it('renders the letter inside a frame', () => {
    const { container } = render(<InboundHtmlMessage html={LETTER} />);
    const frame = container.querySelector('iframe');

    expect(frame).not.toBeNull();
    expect(frame?.getAttribute('srcdoc')).toContain('quoted');
  });

  it('never lets a letter run scripts', () => {
    const { container } = render(<InboundHtmlMessage html={LETTER} />);
    const sandbox = container.querySelector('iframe')?.getAttribute('sandbox');

    // Mail comes from strangers. Granting allow-scripts here would turn every
    // received letter into arbitrary code running in the admin panel.
    expect(sandbox).toBeDefined();
    expect(sandbox).not.toContain('allow-scripts');
    expect(sandbox).not.toContain('allow-top-navigation');
  });
});
