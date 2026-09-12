import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PrinterConnectionReview } from './PrinterConnectionReview';

const { getPrinter, pendingConnections, resolveConnection } = vi.hoisted(() => ({
  getPrinter: vi.fn(), pendingConnections: vi.fn(), resolveConnection: vi.fn(),
}));
vi.mock('../api/client', () => ({
  physicalPrintersAPI: { get: getPrinter, pendingConnections, resolveConnection },
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('./Dropdown', () => ({ Dropdown: ({ value, options, onChange, placeholder, disabled }: {
  value: string; options: { value: string; label: string }[]; onChange: (value: string) => void; placeholder: string;
  disabled?: boolean;
}) => <select aria-label={placeholder} value={value} disabled={disabled}
  onChange={(event) => onChange(event.target.value)}>
  <option value="">{placeholder}</option>{options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
</select> }));

describe('PrinterConnectionReview', () => {
  beforeEach(() => {
    pendingConnections.mockResolvedValue([{ id: 42, revision: 'a'.repeat(64), preset_name: 'Voron connection', candidate_printer_ids: [8] }]);
    resolveConnection.mockReset();
    resolveConnection.mockResolvedValue(undefined);
    getPrinter.mockReset();
    getPrinter.mockResolvedValue({ id: 8, name: 'Workshop' });
  });
  it.each([['8', 8], ['new', null]])('saves only an explicit selection: %s', async (choice, target) => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><PrinterConnectionReview printers={[{ id: 8, name: 'Workshop' } as never]} userId={1} /></QueryClientProvider>);
    const button = await screen.findByText('printerConnections.confirm');
    expect(button).toBeDisabled();
    expect(resolveConnection).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole('combobox'), { target: { value: choice } });
    fireEvent.click(button);
    await waitFor(() => expect(resolveConnection).toHaveBeenCalledWith(42, target, 'a'.repeat(64)));
  });

  it('blocks a separate-device choice while an existing candidate is still loading', async () => {
    pendingConnections.mockResolvedValueOnce([{
      id: 43,
      revision: 'b'.repeat(64),
      preset_name: 'Pending candidate',
      candidate_printer_ids: [9],
    }]);
    getPrinter.mockReturnValueOnce(new Promise(() => {}));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}>
      <PrinterConnectionReview printers={[]} userId={1} />
    </QueryClientProvider>);

    const choice = await screen.findByRole('combobox');
    expect(choice).toBeDisabled();
    expect(screen.getByText('printerConnections.confirm')).toBeDisabled();
    fireEvent.change(choice, { target: { value: 'new' } });
    fireEvent.click(screen.getByText('printerConnections.confirm'));
    expect(resolveConnection).not.toHaveBeenCalled();
  });

  it('keeps confirmation blocked on lookup failure and enables it only after retry resolves', async () => {
    pendingConnections.mockResolvedValueOnce([{
      id: 44,
      revision: 'c'.repeat(64),
      preset_name: 'Retry candidate',
      candidate_printer_ids: [10],
    }]);
    getPrinter
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue({ id: 10, name: 'Existing printer' });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}>
      <PrinterConnectionReview printers={[]} userId={1} />
    </QueryClientProvider>);

    const retry = await screen.findByText('printerConnections.retry');
    expect(screen.getByRole('combobox')).toBeDisabled();
    expect(screen.getByText('printerConnections.confirm')).toBeDisabled();
    fireEvent.click(retry);

    await waitFor(() => expect(screen.getByRole('combobox')).toBeEnabled());
    expect(screen.getByRole('option', { name: 'Existing printer · #10' })).toBeInTheDocument();
    expect(getPrinter).toHaveBeenCalledTimes(2);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'new' } });
    fireEvent.click(screen.getByText('printerConnections.confirm'));
    await waitFor(() => expect(resolveConnection).toHaveBeenCalledWith(44, null, 'c'.repeat(64)));
  });

  it('gates only the connection whose candidate lookup is unresolved', async () => {
    pendingConnections.mockResolvedValueOnce([
      { id: 45, revision: 'd'.repeat(64), preset_name: 'Known', candidate_printer_ids: [8] },
      { id: 46, revision: 'e'.repeat(64), preset_name: 'Unknown', candidate_printer_ids: [11] },
    ]);
    getPrinter.mockReturnValueOnce(new Promise(() => {}));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}>
      <PrinterConnectionReview printers={[{ id: 8, name: 'Workshop' } as never]} userId={1} />
    </QueryClientProvider>);

    const choices = await screen.findAllByRole('combobox');
    const confirms = screen.getAllByText('printerConnections.confirm');
    expect(choices[0]).toBeEnabled();
    expect(choices[1]).toBeDisabled();
    fireEvent.change(choices[0], { target: { value: '8' } });
    expect(confirms[0]).toBeEnabled();
    expect(confirms[1]).toBeDisabled();
  });
});
