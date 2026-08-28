import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PrinterRecoveryModal } from './PrinterRecoveryModal';

const mocks = vi.hoisted(() => ({
  getPlan: vi.fn(),
  getLocal: vi.fn(),
  apply: vi.fn(),
  remove: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: { count?: number }) =>
      values?.count == null ? key : `${key}:${values.count}`,
  }),
}));

vi.mock('../api/client', () => ({
  physicalPrintersAPI: {
    getOrcaRecoveryPlan: (...args: unknown[]) => mocks.getPlan(...args),
  },
}));

vi.mock('../utils/pluginBridge', () => ({
  requestPrinterRecoveryState: (...args: unknown[]) => mocks.getLocal(...args),
  applyPrinterRecoveryInPlugin: (...args: unknown[]) => mocks.apply(...args),
  removePrinterRecoveryFromPlugin: (...args: unknown[]) => mocks.remove(...args),
}));

const context = {
  server_origin: 'https://filamenthub.ru',
  owner_user_id: 7,
  source_instance_id: 'source-instance-123456',
  account_id: '11111111-1111-4111-8111-111111111111',
};

const plan = {
  format: 'filamenthub.orcaslicer.printer-recovery',
  version: 1,
  scope: {
    owner_user_id: 7,
    source_instance_id: context.source_instance_id,
    account_id: context.account_id,
  },
  physical_printers: [{ id: 5, name: 'Workshop Voron' }],
  machine_profiles: [{
    id: 41,
    name: 'Voron 0.4',
    profile: { name: 'Voron 0.4', type: 'machine' },
    content_hash: 'a'.repeat(64),
    physical_printer_ids: [5],
    original_state: 'missing',
  }],
  process_profiles: [
    {
      id: 71,
      name: 'Existing process',
      profile: { name: 'Existing process', type: 'process' },
      content_hash: 'b'.repeat(64),
      physical_printer_ids: [5],
      original_state: 'present',
    },
    {
      id: 72,
      name: 'Unknown process',
      profile: { name: 'Unknown process', type: 'process' },
      content_hash: 'c'.repeat(64),
      physical_printer_ids: [5],
      original_state: 'unknown',
    },
  ],
};

describe('PrinterRecoveryModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getLocal.mockResolvedValue({ context, artifacts: [] });
    mocks.getPlan.mockResolvedValue(plan);
    mocks.apply.mockResolvedValue({
      status: 'success',
      message: 'written',
      results: [{ kind: 'machine', profileId: 41, state: 'written_restart_required' }],
    });
    mocks.remove.mockResolvedValue({ status: 'success', results: [] });
  });

  it('previews first, selects only a known missing original, and sends exact choices', async () => {
    render(<PrinterRecoveryModal ownerUserId={7} onClose={vi.fn()} />);

    const restore = await screen.findByRole('button', { name: 'printerRecovery.restoreSelected' });
    expect(mocks.getLocal).toHaveBeenCalledWith(7);
    expect(mocks.getPlan).toHaveBeenCalledWith(
      context.source_instance_id,
      context.account_id,
      undefined,
    );
    expect(mocks.apply).not.toHaveBeenCalled();

    const checkboxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    expect(checkboxes).toHaveLength(3);
    expect(checkboxes[0]).toBeChecked();
    expect(checkboxes[1]).toBeDisabled();
    expect(checkboxes[1]).not.toBeChecked();
    expect(checkboxes[2]).not.toBeChecked();

    fireEvent.click(restore);
    await waitFor(() => expect(mocks.apply).toHaveBeenCalledOnce());
    const sent = mocks.apply.mock.calls[0][0];
    expect(sent.machine_profiles.map((item: { id: number }) => item.id)).toEqual([41]);
    expect(sent.process_profiles).toEqual([]);
  });

  it('keeps offline local cleanup available when the server plan fails', async () => {
    mocks.getPlan.mockRejectedValue(new Error('export permission disabled'));
    mocks.getLocal.mockResolvedValue({
      context,
      artifacts: [{
        artifactKey: 'local-artifact',
        kind: 'process',
        profileId: 72,
        name: 'Managed process',
        contentHash: null,
        ownership: 'untracked',
        healthy: true,
      }],
    });
    mocks.remove.mockResolvedValue({
      status: 'success',
      message: 'removed',
      results: [{ artifactKey: 'local-artifact', kind: 'process', profileId: 72, state: 'removed_restart_required' }],
    });

    render(<PrinterRecoveryModal ownerUserId={7} onClose={vi.fn()} />);

    expect(await screen.findByText('export permission disabled')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'printerRecovery.removeLocal' }));
    await waitFor(() => expect(mocks.remove).toHaveBeenCalledWith(['local-artifact']));
    expect(await screen.findByText('removed')).toBeInTheDocument();
  });

  it('requires cleanup before replacing a foreign managed copy', async () => {
    mocks.getLocal.mockResolvedValue({
      context,
      artifacts: [{
        artifactKey: 'foreign-machine',
        kind: 'machine',
        profileId: 41,
        name: 'Voron 0.4',
        contentHash: 'a'.repeat(64),
        ownership: 'foreign',
        healthy: true,
      }],
    });

    render(<PrinterRecoveryModal ownerUserId={7} onClose={vi.fn()} />);

    const checkboxes = await screen.findAllByRole('checkbox') as HTMLInputElement[];
    expect(checkboxes[0]).toBeDisabled();
    expect(checkboxes[0]).not.toBeChecked();
    expect(screen.getByText(/printerRecovery\.managedConflict/)).toBeInTheDocument();
    expect(screen.getByRole('button', {
      name: 'printerRecovery.restoreSelected',
    })).toBeDisabled();
  });
});
