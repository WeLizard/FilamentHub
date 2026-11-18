import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const getPluginDownloadsMock = vi.hoisted(() => vi.fn());
const translationState = vi.hoisted(() => ({ language: 'en', resolvedLanguage: 'en' }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: translationState,
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

// The page shows one way of connecting per section, chosen by the address.
const at = (path: string, page: ReactElement) => (
  <MemoryRouter initialEntries={[path]}>
    <Routes>
      <Route path="/download/:section?" element={page} />
    </Routes>
  </MemoryRouter>
);

describe('DownloadPage', () => {
  beforeEach(() => {
    translationState.language = 'en';
    translationState.resolvedLanguage = 'en';
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

    const octoprint = render(at('/download/octoprint', <DownloadPage />));

    expect(await screen.findByRole('link', { name: /downloadPage\.octoOpenReleases/ }))
      .toHaveAttribute(
        'href',
        'https://github.com/WeLizard/FilamentHub/releases/tag/octoprint-v0.1.1',
      );
    octoprint.unmount();
    render(at('/download', <DownloadPage />));
    expect(await screen.findByRole('link', { name: /downloadPage\.step1Nightly/ }))
      .toHaveAttribute(
        'href',
        'https://github.com/OrcaSlicer/OrcaSlicer/releases/tag/nightly-builds',
      );
  });

  it('selects the Russian overview video only for Russian and changes source with locale', async () => {
    const { DownloadPage } = await import('./DownloadPage');

    const { rerender } = render(at('/download', <DownloadPage />));
    let video = await screen.findByLabelText('downloadPage.videoTitle');
    expect(video).toHaveAttribute('src', '/download-media/filamenthub-overview-en.mp4');
    expect(video.querySelector('track')).toHaveAttribute(
      'src',
      '/download-media/filamenthub-overview-en.vtt',
    );
    expect(video.querySelector('track')).toHaveAttribute('srclang', 'en');

    translationState.language = 'ru';
    translationState.resolvedLanguage = 'ru';
    rerender(at('/download', <DownloadPage />));
    video = screen.getByLabelText('downloadPage.videoTitle');
    expect(video).toHaveAttribute('src', '/download-media/filamenthub-overview-ru.mp4');
    expect(video.querySelector('track')).toHaveAttribute(
      'src',
      '/download-media/filamenthub-overview-ru.vtt',
    );
    expect(video.querySelector('track')).toHaveAttribute('srclang', 'ru');

    translationState.language = 'zh';
    translationState.resolvedLanguage = 'zh';
    rerender(at('/download', <DownloadPage />));
    video = screen.getByLabelText('downloadPage.videoTitle');
    expect(video).toHaveAttribute('src', '/download-media/filamenthub-overview-en.mp4');
    expect(video.querySelector('track')).toHaveAttribute(
      'src',
      '/download-media/filamenthub-overview-en.vtt',
    );
    expect(video.querySelector('track')).toHaveAttribute('srclang', 'en');
  });
});
