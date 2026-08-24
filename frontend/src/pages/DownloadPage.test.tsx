import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const getPluginDownloadsMock = vi.hoisted(() => vi.fn());

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { tag?: string; version?: string | null }) =>
      options?.tag || options?.version ? `${key}:${options.tag || options.version}` : key,
  }),
}));

vi.mock('../components/SEOHead', () => ({
  SEOHead: () => null,
}));

vi.mock('../api/client', () => ({
  downloadsAPI: {
    getPluginDownloads: getPluginDownloadsMock,
  },
}));

describe('DownloadPage', () => {
  beforeEach(() => {
    getPluginDownloadsMock.mockResolvedValue({
      release_url: 'https://github.com/WeLizard/FilamentHub/releases/tag/v0.1.3',
      packages: [
        {
          plugin: 'orcaslicer',
          filename: 'filamenthub-0.1.3-py3-none-any.whl',
          version: '0.1.3',
          file_size: '1 MB',
          checksum: null,
          download_url: '/api/v1/downloads/plugins/orcaslicer',
          github_url: 'https://github.com/WeLizard/FilamentHub/releases/tag/v0.1.3',
        },
        {
          plugin: 'octoprint',
          filename: 'octoprint_filamenthubbridge-0.1.1-py3-none-any.whl',
          version: '0.1.1',
          file_size: '1 MB',
          checksum: null,
          download_url: '/api/v1/downloads/plugins/octoprint',
          github_url: 'https://github.com/WeLizard/FilamentHub/releases/tag/octoprint-v0.1.1',
        },
        {
          plugin: 'print_farm',
          filename: 'print_farm-0.1.0-py3-none-any.whl',
          version: '0.1.0',
          file_size: '1 MB',
          checksum: null,
          download_url: '/api/v1/downloads/plugins/print_farm',
          github_url: 'https://github.com/WeLizard/orca-plugins/releases/tag/v0.1.0',
        },
      ],
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        tag_name: 'v2.4.2',
        html_url: 'https://github.com/OrcaSlicer/OrcaSlicer/releases/tag/v2.4.2',
      }),
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('keeps OctoPrint and OrcaSlicer release paths independent', async () => {
    const { DownloadPage } = await import('./DownloadPage');

    render(<DownloadPage />);

    expect(await screen.findByRole('link', { name: /downloadPage\.octoOpenReleases/ }))
      .toHaveAttribute(
        'href',
        'https://github.com/WeLizard/FilamentHub/releases/tag/octoprint-v0.1.1',
      );
    expect(screen.getByRole('link', { name: /downloadPage\.step1Nightly/ }))
      .toHaveAttribute(
        'href',
        'https://github.com/OrcaSlicer/OrcaSlicer/releases/tag/nightly-builds',
      );
  });
});
