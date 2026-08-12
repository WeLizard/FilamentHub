import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { OrcaExportButton } from './OrcaExportButton';

const bridgeState = vi.hoisted(() => ({ available: true }));

vi.mock('../hooks/useOrcaBridgeCapability', () => ({
  useOrcaBridgeCapability: () => bridgeState.available,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe('OrcaExportButton', () => {
  beforeEach(() => {
    bridgeState.available = true;
    window.filamenthub = {};
  });

  it('runs the selected bridge capability and reports success', async () => {
    const exporter = vi.fn().mockResolvedValue({ message: 'queued' });
    const onExportComplete = vi.fn();
    window.filamenthub = { exportPrinterProfiles: exporter };

    const { unmount } = render(
      <OrcaExportButton
        capability="exportPrinterProfiles"
        translationPrefix="exportPrinterProfiles"
        successLabel="done"
        errorContext="Printer profiles"
        onExportComplete={onExportComplete}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'exportPrinterProfiles.button' }));

    await waitFor(() => expect(exporter).toHaveBeenCalledTimes(1));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'exportPrinterProfiles.done' })).toBeEnabled();
    });
    expect(onExportComplete).toHaveBeenCalledWith({ success: true, message: 'queued' });

    unmount();
  });

  it('keeps the hidden variant out of ordinary browser pages', () => {
    bridgeState.available = false;

    const { container } = render(
      <OrcaExportButton
        capability="exportFilamentPresets"
        translationPrefix="exportOrcaSlicer"
        successLabel="started"
        errorContext="Filament presets"
        hideWhenUnavailable
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('honours a disabled sync direction without invoking the bridge', () => {
    const exporter = vi.fn().mockResolvedValue({});
    window.filamenthub = { exportPrintProfiles: exporter };

    render(
      <OrcaExportButton
        capability="exportPrintProfiles"
        translationPrefix="exportPrintProfiles"
        successLabel="done"
        errorContext="Print profiles"
        disabled
      />,
    );

    const button = screen.getByRole('button', { name: 'exportPrintProfiles.button' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('title', 'exportPrintProfiles.disabled');
    fireEvent.click(button);
    expect(exporter).not.toHaveBeenCalled();
  });
});
