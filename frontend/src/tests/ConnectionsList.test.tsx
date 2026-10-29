import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import type { PhysicalPrinter } from '../api/client';

const revokeConnector = vi.hoisted(() => vi.fn());
vi.mock('../api/client', () => ({ physicalPrintersAPI: { revokeConnector } }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));
vi.mock('../components/Toast', () => ({ toast: { error: vi.fn() } }));

const printer = {
  id: 5,
  contact_channels: [
    { kind: 'native_spoolman', source: 'moonraker', connector_id: null, material_system_id: 9, last_contact_at: null, state: 'unknown', basis: 'websocket_lease' },
    { kind: 'connector', source: 'bambu:orca_plugin_lan', connector_id: 31, material_system_id: 9, last_contact_at: '2026-10-29T09:00:00Z', state: 'live', basis: 'heartbeat' },
    { kind: 'connector', source: 'bambu:orca_plugin_lan', connector_id: 32, material_system_id: 9, last_contact_at: '2026-10-29T09:00:00Z', state: 'live', basis: 'heartbeat' },
  ],
} as unknown as PhysicalPrinter;

describe('ConnectionsList', () => {
  it('lists each channel and revokes only the chosen helper after confirmation', async () => {
    revokeConnector.mockResolvedValue(printer);
    const { ConnectionsList } = await import('../components/presetSlots/ConnectionsList');
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ConnectionsList printer={printer} systemId={9} />
      </QueryClientProvider>,
    );

    expect(screen.getByText('connections.native')).toBeInTheDocument();
    expect(screen.getAllByText('connections.channel.orca')).toHaveLength(2);
    expect(screen.getByText('connections.state.unknown')).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('button', { name: 'connections.revoke' })[1]);
    expect(revokeConnector).not.toHaveBeenCalled();
    const confirm = screen.getAllByRole('button', { name: 'connections.revoke' });
    fireEvent.click(confirm[confirm.length - 1]);
    await waitFor(() => expect(revokeConnector).toHaveBeenCalledWith(5, 32));
  });
});
