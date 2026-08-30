import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PrinterConnectionReview } from './PrinterConnectionReview';

const { pendingConnections, resolveConnection } = vi.hoisted(() => ({
  pendingConnections: vi.fn(), resolveConnection: vi.fn(),
}));
vi.mock('../api/client', () => ({ physicalPrintersAPI: { pendingConnections, resolveConnection } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('./Dropdown', () => ({ Dropdown: ({ value, options, onChange, placeholder }: {
  value: string; options: { value: string; label: string }[]; onChange: (value: string) => void; placeholder: string;
}) => <select aria-label={placeholder} value={value} onChange={(event) => onChange(event.target.value)}>
  <option value="">{placeholder}</option>{options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
</select> }));

describe('PrinterConnectionReview', () => {
  beforeEach(() => {
    pendingConnections.mockResolvedValue([{ id: 42, revision: 'a'.repeat(64), preset_name: 'Voron connection', candidate_printer_ids: [8] }]);
    resolveConnection.mockReset();
    resolveConnection.mockResolvedValue(undefined);
  });
  it.each([['8', 8], ['new', null]])('saves only an explicit selection: %s', async (choice, target) => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><PrinterConnectionReview printers={[{ id: 8, name: 'Workshop' } as never]} /></QueryClientProvider>);
    const button = await screen.findByText('printerConnections.confirm');
    expect(button).toBeDisabled();
    expect(resolveConnection).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole('combobox'), { target: { value: choice } });
    fireEvent.click(button);
    await waitFor(() => expect(resolveConnection).toHaveBeenCalledWith(42, target, 'a'.repeat(64)));
  });
});
