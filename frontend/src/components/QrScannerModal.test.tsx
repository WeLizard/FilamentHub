import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../utils/qrScanner', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../utils/qrScanner')>()),
  createQrFrameDecoder: async () => async () => null,
}));

import { QrScannerModal } from './QrScannerModal';

const original = Object.getOwnPropertyDescriptor(navigator, 'mediaDevices');

function setMediaDevices(value: unknown) {
  Object.defineProperty(navigator, 'mediaDevices', { value, configurable: true });
}

function renderScanner() {
  render(<QrScannerModal isOpen onClose={vi.fn()} onDetected={vi.fn()} />);
}

describe('QrScannerModal camera failures', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    if (original) Object.defineProperty(navigator, 'mediaDevices', original);
    else Reflect.deleteProperty(navigator, 'mediaDevices');
  });

  it('reports an unsupported browser when getUserMedia is missing', async () => {
    setMediaDevices(undefined);
    renderScanner();
    expect(await screen.findByText('qrScanner.camera.notSupported')).toBeInTheDocument();
  });

  it.each(['NotAllowedError', 'SecurityError'])('reports blocked access for %s', async (name) => {
    setMediaDevices({ getUserMedia: vi.fn().mockRejectedValue(Object.assign(new Error('x'), { name })) });
    renderScanner();
    expect(await screen.findByText('qrScanner.camera.permissionDenied')).toBeInTheDocument();
  });

  it.each(['NotFoundError', 'OverconstrainedError'])('reports a missing camera for %s', async (name) => {
    setMediaDevices({ getUserMedia: vi.fn().mockRejectedValue(Object.assign(new Error('x'), { name })) });
    renderScanner();
    expect(await screen.findByText('qrScanner.camera.noCamera')).toBeInTheDocument();
  });
});
