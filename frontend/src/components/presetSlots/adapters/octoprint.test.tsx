import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  status: vi.fn(),
  issuePairingCode: vi.fn(),
  downloads: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));

vi.mock('../../../api/client', () => ({
  octoprintBridgeAPI: { status: mocks.status, issuePairingCode: mocks.issuePairingCode },
  downloadsAPI: { getPluginDownloads: mocks.downloads },
}));

vi.mock('../../Toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { octoprintAdapter } from './octoprint';
import type { AdapterViewContext } from './types';

const context = {
  printer: { id: 11, name: 'Workshop Prusa', connectors: [] },
  system: { id: 21, provider: 'octoprint', slots: [] },
  gates: [],
  spools: [],
  linkConfirmed: false,
} as unknown as AdapterViewContext;

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>{octoprintAdapter.renderSetup?.(context)}</QueryClientProvider>,
  );
}

describe('OctoPrint bridge setup', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.status.mockResolvedValue({ paired: false, pairing_expires_at: null });
    mocks.downloads.mockResolvedValue({ packages: [{
      plugin: 'octoprint', version: '1.2.0', filename: 'bridge.whl', download_url: '/downloads/bridge.whl',
    }] });
  });

  it('shows how to install before offering the code', async () => {
    show();

    const button = await screen.findByRole('button', { name: /presetSlots\.octoprint\.issueCodeInstalled/ });
    expect(screen.getByText('downloadPage.octoInstall1')).toBeInTheDocument();
    expect(screen.getByText('presetSlots.octoprint.afterInstall')).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: /downloadPage\.octoDownload/ })).toHaveAttribute('href', '/downloads/bridge.whl');
    expect(button).toBeEnabled();
  });

  it('offers a new code once the issued one has run out', async () => {
    mocks.issuePairingCode
      .mockResolvedValueOnce({ pairing_code: 'OLD-CODE-1', expires_at: '2020-01-01T00:00:00Z' })
      .mockResolvedValueOnce({ pairing_code: 'NEW-CODE-2', expires_at: '2999-01-01T00:00:00Z' });
    show();

    fireEvent.click(await screen.findByRole('button', { name: /presetSlots\.octoprint\.issueCodeInstalled/ }));

    expect(await screen.findByText('presetSlots.octoprint.codeExpired')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /presetSlots\.octoprint\.newCode/ }));
    expect(await screen.findByText('NEW-CODE-2')).toBeInTheDocument();
    expect(screen.queryByText('presetSlots.octoprint.codeExpired')).not.toBeInTheDocument();
  });

  it('shows how long a live code lasts and lets the person take a new one', async () => {
    mocks.issuePairingCode
      .mockResolvedValueOnce({ pairing_code: 'LIVE-CODE-1', expires_at: '2999-01-01T00:00:00Z' })
      .mockResolvedValueOnce({ pairing_code: 'LIVE-CODE-2', expires_at: '2999-01-01T00:10:00Z' });
    show();

    fireEvent.click(await screen.findByRole('button', { name: /presetSlots\.octoprint\.issueCodeInstalled/ }));

    expect(await screen.findByText('LIVE-CODE-1')).toBeInTheDocument();
    expect(screen.getByText('presetSlots.octoprint.codeExpires')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /presetSlots\.octoprint\.newCode/ }));
    expect(await screen.findByText('LIVE-CODE-2')).toBeInTheDocument();
    expect(mocks.issuePairingCode).toHaveBeenCalledTimes(2);
  });
});
