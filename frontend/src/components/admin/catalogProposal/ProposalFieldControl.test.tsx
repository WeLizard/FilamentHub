import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ProposalFieldControl } from './ProposalFieldControl';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

function Harness({ field, initial, onStore }: { field: string; initial: unknown; onStore: (value: unknown) => void }) {
  const [value, setValue] = useState<unknown>(initial);
  return <ProposalFieldControl sheet="filaments" field={field} value={value} disabled={false} label="Field"
    onChange={(next) => { setValue(next); onStore(next); }} />;
}

describe('ProposalFieldControl', () => {
  it('keeps "1.0" while typing and settles on the number when the field is left', () => {
    const stored = vi.fn();
    render(<Harness field="diameter" initial={null} onStore={stored} />);
    const input = screen.getByRole('textbox', { name: 'Field' });
    fireEvent.change(input, { target: { value: '1.0' } });
    expect(input).toHaveValue('1.0');
    fireEvent.change(input, { target: { value: '1.04' } });
    expect(input).toHaveValue('1.04');
    expect(stored).toHaveBeenLastCalledWith(1.04);
    fireEvent.change(input, { target: { value: '1.0' } });
    fireEvent.blur(input);
    expect(stored).toHaveBeenLastCalledWith(1);
    expect(input).toHaveValue('1');
  });

  it('stores typed decimals with leading zeros exactly', () => {
    const stored = vi.fn();
    render(<Harness field="diameter" initial={1.75} onStore={stored} />);
    const input = screen.getByRole('textbox', { name: 'Field' });
    fireEvent.change(input, { target: { value: '0.05' } });
    expect(stored).toHaveBeenLastCalledWith(0.05);
    fireEvent.change(input, { target: { value: '-5' } });
    expect(stored).toHaveBeenLastCalledWith(-5);
  });

  it('never writes a number field that was only focused', () => {
    const stored = vi.fn();
    render(<Harness field="diameter" initial={1.75} onStore={stored} />);
    fireEvent.blur(screen.getByRole('textbox', { name: 'Field' }));
    expect(stored).not.toHaveBeenCalled();
  });

  it('keeps an object field a textarea while the JSON is incomplete and never stores text', () => {
    const stored = vi.fn();
    render(<Harness field="orcaslicer_settings" initial={{ a: 1 }} onStore={stored} />);
    const area = screen.getByRole('textbox', { name: 'Field' });
    expect(area.tagName).toBe('TEXTAREA');
    fireEvent.change(area, { target: { value: '{"a": 1, ' } });
    expect(screen.getByRole('textbox', { name: 'Field' }).tagName).toBe('TEXTAREA');
    expect(screen.getByRole('textbox', { name: 'Field' })).toHaveValue('{"a": 1, ');
    expect(screen.getByRole('alert')).toHaveTextContent('adminCatalogImport.curation.invalidJson');
    expect(stored).not.toHaveBeenCalled();
    fireEvent.change(area, { target: { value: '{"a": 2}' } });
    expect(stored).toHaveBeenLastCalledWith({ a: 2 });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
