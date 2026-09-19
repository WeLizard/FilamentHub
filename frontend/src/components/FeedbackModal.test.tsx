import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FeedbackModal } from './FeedbackModal';

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  readLog: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 7, username: 'maker', role: 'user' } }),
}));
vi.mock('../api/client', () => ({ feedbackAPI: { create: mocks.create } }));
vi.mock('../utils/pluginBridge', () => ({ requestPluginDiagnosticLog: mocks.readLog }));

const renderReport = () => render(
  <FeedbackModal
    isOpen
    onClose={vi.fn()}
    initialType="bug"
    initialSubject="Problem in the OrcaSlicer plugin"
    initialMessage="Sync did not fully complete"
    source="orca_plugin"
    attachPluginLog
  />,
);

describe('plugin problem report', () => {
  beforeEach(() => {
    mocks.create.mockReset().mockResolvedValue({});
    mocks.readLog.mockReset().mockResolvedValue('FilamentHub plugin 0.2.0\nsync done');
  });

  it('sends the plugin log with the report', async () => {
    renderReport();

    await screen.findByText('feedback.pluginLog.attached');
    fireEvent.click(screen.getByRole('button', { name: /feedback.send/ }));

    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({
      type: 'bug',
      source: 'orca_plugin',
      plugin_log: 'FilamentHub plugin 0.2.0\nsync done',
    })));
  });

  it('leaves the log out once the person removes it', async () => {
    renderReport();

    await screen.findByText('feedback.pluginLog.attached');
    fireEvent.click(screen.getByRole('button', { name: 'feedback.pluginLog.remove' }));
    fireEvent.click(screen.getByRole('button', { name: /feedback.send/ }));

    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({
      plugin_log: null,
    })));
  });
});
