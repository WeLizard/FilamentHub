import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useDebounce } from '../hooks/useDebounce';

function DebounceProbe({ delay = 200 }: { delay?: number }) {
  const [value, setValue] = React.useState('');
  const debounced = useDebounce(value, delay);

  return React.createElement(
    'div',
    null,
    React.createElement('input', {
      'aria-label': 'value-input',
      value,
      onChange: (e: React.ChangeEvent<HTMLInputElement>) => setValue(e.target.value),
    }),
    React.createElement('div', { 'data-testid': 'raw-value' }, value),
    React.createElement('div', { 'data-testid': 'debounced-value' }, debounced)
  );
}

describe('useDebounce', () => {
  it('updates value only after delay', () => {
    vi.useFakeTimers();

    render(React.createElement(DebounceProbe, { delay: 300 }));

    fireEvent.change(screen.getByLabelText('value-input'), { target: { value: 'hello' } });

    expect(screen.getByTestId('raw-value')).toHaveTextContent('hello');
    expect(screen.getByTestId('debounced-value')).toHaveTextContent('');

    act(() => {
      vi.advanceTimersByTime(299);
    });

    expect(screen.getByTestId('debounced-value')).toHaveTextContent('');

    act(() => {
      vi.advanceTimersByTime(1);
    });

    expect(screen.getByTestId('debounced-value')).toHaveTextContent('hello');
  });

  it('skips intermediate updates during rapid changes', () => {
    vi.useFakeTimers();

    render(React.createElement(DebounceProbe, { delay: 200 }));

    fireEvent.change(screen.getByLabelText('value-input'), { target: { value: 'a' } });
    act(() => {
      vi.advanceTimersByTime(100);
    });

    fireEvent.change(screen.getByLabelText('value-input'), { target: { value: 'ab' } });
    act(() => {
      vi.advanceTimersByTime(100);
    });

    fireEvent.change(screen.getByLabelText('value-input'), { target: { value: 'abc' } });

    expect(screen.getByTestId('debounced-value')).toHaveTextContent('');

    act(() => {
      vi.advanceTimersByTime(199);
    });

    expect(screen.getByTestId('debounced-value')).toHaveTextContent('');

    act(() => {
      vi.advanceTimersByTime(1);
    });

    expect(screen.getByTestId('debounced-value')).toHaveTextContent('abc');
  });
});
