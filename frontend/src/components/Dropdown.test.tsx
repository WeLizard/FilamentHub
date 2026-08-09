import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import '../i18n';
import { Dropdown } from './Dropdown';

describe('Dropdown', () => {
  it('shows searchable options when the empty all-items option is selected', async () => {
    render(
      <Dropdown
        value=""
        options={[
          { value: '', label: 'Все бренды' },
          { value: 1, label: 'eSUN' },
          { value: 2, label: 'Polymaker' },
        ]}
        onChange={vi.fn()}
        placeholder="Все бренды"
        filterable
      />,
    );

    fireEvent.focus(screen.getByPlaceholderText('Все бренды'));

    const option = await screen.findByRole('button', { name: 'eSUN' });

    expect(option).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Polymaker' })).toBeInTheDocument();

    const scrollViewport = option.closest('.scrollbar-contained');
    expect(scrollViewport).toHaveClass('overflow-y-auto');
    expect(scrollViewport?.parentElement).toHaveClass('overflow-hidden', 'rounded-xl');
  });
});
