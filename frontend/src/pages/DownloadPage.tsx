/** Current FilamentHub integrations for official OrcaSlicer and OctoPrint. */

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Download, CheckCircle, Package, Code, Zap, Globe, Monitor, Image as ImageIcon, Play, ExternalLink, X, Server, ShieldCheck, RefreshCw } from 'lucide-react';
import { downloadsAPI } from '../api/client';
import type { PluginDownload } from '../types/api';
import { ModalOverlay } from '../components/ModalOverlay';
import { SEOHead } from '../components/SEOHead';

// Official OrcaSlicer entry points and the FilamentHub Plugin Hub page. The release
// link resolves to whatever is current so we never hardcode a version.
const ORCA_OFFICIAL_DOWNLOAD_URL = 'https://www.orcaslicer.com/download/';
const ORCA_RELEASES_LATEST_URL = 'https://github.com/OrcaSlicer/OrcaSlicer/releases/latest';
const FILAMENTHUB_PLUGIN_HUB_URL = 'https://cloud.orcaslicer.com/app/plugins/plugin-hub/34c1321c-7d46-4c5a-a8e9-f6c78fa9898e';
const PRINT_FARM_PLUGIN_HUB_URL = 'https://cloud.orcaslicer.com/app/plugins/plugin-hub/3d30ee0c-24ba-435e-ae23-6bbc76d8e949';
const FILAMENTHUB_PLUGIN_REPO = 'WeLizard/FilamentHub';
const FILAMENTHUB_RELEASES_URL = `https://github.com/${FILAMENTHUB_PLUGIN_REPO}/releases`;

type PluginReleaseAsset = {
  url: string;
  name: string;
};

type GitHubReleaseAsset = {
  name?: string;
  browser_download_url?: string;
};

const isOrcaPluginWheel = (asset: GitHubReleaseAsset) =>
  /^filamenthub-.*\.whl$/i.test(asset.name || '');

const isOctoPrintBridgeWheel = (asset: GitHubReleaseAsset) => {
  const name = (asset.name || '').toLowerCase().replaceAll('-', '_');
  return name.startsWith('octoprint_filamenthubbridge_') && name.endsWith('.whl');
};

const wheelPackageVersion = (assetName: string): string | null =>
  assetName.match(/^[A-Za-z0-9_]+-([^-]+)-/)?.[1] ?? null;

type DownloadScreenshotCardImageProps = {
  src: string;
  alt: string;
  comingSoonLabel: string;
  openPreviewLabel: string;
  onOpenPreview: (src: string, alt: string) => void;
  imageClassName?: string;
};

function DownloadScreenshotCardImage({
  src,
  alt,
  comingSoonLabel,
  openPreviewLabel,
  onOpenPreview,
  imageClassName = 'object-cover object-top',
}: DownloadScreenshotCardImageProps) {
  const [loadFailed, setLoadFailed] = useState(false);

  if (loadFailed) {
    return (
      <div className="aspect-video bg-gradient-to-br from-gray-800 to-gray-900 rounded-lg flex items-center justify-center border-2 border-dashed border-white/20 mb-4">
        <div className="text-center">
          <ImageIcon className="w-12 h-12 text-gray-500 mx-auto mb-2" />
          <p className="text-sm text-gray-500">{alt}</p>
          <p className="text-xs text-gray-600 mt-1">{comingSoonLabel}</p>
        </div>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onOpenPreview(src, alt)}
      className="group relative block aspect-video w-full overflow-hidden rounded-lg border border-white/10 bg-black/20 mb-4 text-left transition duration-300 hover:border-purple-400/40 hover:shadow-[0_16px_45px_rgba(123,97,255,0.18)]"
      aria-label={`${openPreviewLabel}: ${alt}`}
    >
      <img
        src={src}
        alt={alt}
        className={`h-full w-full transition duration-500 group-hover:scale-[1.02] ${imageClassName}`}
        loading="lazy"
        onError={() => setLoadFailed(true)}
      />

      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-black/80 via-black/45 to-transparent px-4 py-3 text-xs text-white/85 opacity-0 transition duration-300 group-hover:opacity-100">
        <span>{openPreviewLabel}</span>
        <span className="rounded-full border border-white/15 bg-white/10 px-2 py-0.5 text-[11px] text-white/80">
          Enter
        </span>
      </div>
    </button>
  );
}

export function DownloadPage() {
  const { t } = useTranslation();
  const [previewImage, setPreviewImage] = useState<{ src: string; alt: string } | null>(null);
  const [orcaRelease, setOrcaRelease] = useState<{ tag: string; url: string } | null>(null);
  const [pluginsReleaseUrl, setPluginsReleaseUrl] = useState(FILAMENTHUB_RELEASES_URL);
  const [orcaPluginWheel, setOrcaPluginWheel] = useState<PluginReleaseAsset | null>(null);
  const [octoPrintBridgeWheel, setOctoPrintBridgeWheel] = useState<PluginReleaseAsset | null>(null);

  // Latest official OrcaSlicer release for the dynamic "get OrcaSlicer" link.
  // Best-effort: if GitHub is unreachable we fall back to the releases/latest URL.
  useEffect(() => {
    const controller = new AbortController();
    fetch('https://api.github.com/repos/OrcaSlicer/OrcaSlicer/releases/latest', {
      headers: { Accept: 'application/vnd.github+json' },
      signal: controller.signal,
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data?.tag_name) return;
        setOrcaRelease({
          tag: data.tag_name,
          url: data.html_url || `https://github.com/OrcaSlicer/OrcaSlicer/releases/tag/${data.tag_name}`,
        });
      })
      .catch(() => {});
    return () => controller.abort();
  }, []);

  // Two independent ways to the same packages. Our own server answers first: it
  // stays reachable where GitHub is blocked or rate-limited. Reading the release
  // straight from GitHub remains as the fallback for when our API cannot answer.
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    const fromFilamentHub = async () => {
      try {
        const data = await downloadsAPI.getPluginDownloads(controller.signal);
        if (cancelled || !data.packages.length) return false;
        if (data.release_url) setPluginsReleaseUrl(data.release_url);
        const orca = data.packages.find((item: PluginDownload) => item.plugin === 'orcaslicer');
        const octoPrint = data.packages.find((item: PluginDownload) => item.plugin === 'octoprint');
        if (orca) setOrcaPluginWheel({ url: orca.download_url, name: orca.filename });
        if (octoPrint) {
          setOctoPrintBridgeWheel({ url: octoPrint.download_url, name: octoPrint.filename });
        }
        return Boolean(orca || octoPrint);
      } catch {
        return false;
      }
    };

    // Search recent releases instead of /latest so an unrelated application
    // release cannot hide the plugins.
    const fromGitHub = async () => {
      try {
        const response = await fetch(
          `https://api.github.com/repos/${FILAMENTHUB_PLUGIN_REPO}/releases?per_page=20`,
          { headers: { Accept: 'application/vnd.github+json' }, signal: controller.signal },
        );
        if (!response.ok) return;
        const data = await response.json();
        if (cancelled || !Array.isArray(data)) return;
        const release = data.find((candidate: { assets?: GitHubReleaseAsset[] }) =>
          (candidate.assets || []).some(
            (asset) => isOrcaPluginWheel(asset) || isOctoPrintBridgeWheel(asset),
          ),
        );
        if (!release) return;
        setPluginsReleaseUrl(release.html_url || FILAMENTHUB_RELEASES_URL);
        const assets = (release.assets || []) as GitHubReleaseAsset[];
        const orcaAsset = assets.find(isOrcaPluginWheel);
        const octoPrintAsset = assets.find(isOctoPrintBridgeWheel);
        if (orcaAsset?.browser_download_url && orcaAsset.name) {
          setOrcaPluginWheel({
            url: orcaAsset.browser_download_url,
            name: orcaAsset.name,
          });
        }
        if (octoPrintAsset?.browser_download_url && octoPrintAsset.name) {
          setOctoPrintBridgeWheel({
            url: octoPrintAsset.browser_download_url,
            name: octoPrintAsset.name,
          });
        }
      } catch {
        // Both ways failed; the releases link stays as the way out.
      }
    };

    void (async () => {
      const served = await fromFilamentHub();
      if (!served && !cancelled) await fromGitHub();
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, []);

  return (
    <>
      <SEOHead
        title={t('downloadPage.seoTitle')}
        description={t('downloadPage.seoDescription')}
        url="/download"
        type="website"
      />
      <div className="max-w-5xl mx-auto px-4 md:px-6 py-6 md:py-12">
      {/* Header — plugin-first */}
      <div className="text-center mb-8 md:mb-12">
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mb-4">
          <div className="w-12 h-12 md:w-16 md:h-16 bg-gradient-to-br from-purple-500 to-pink-500 rounded-xl md:rounded-2xl flex items-center justify-center shadow-lg shadow-purple-500/25">
            <Package className="w-6 h-6 md:w-8 md:h-8 text-white" />
          </div>
          <h1 className="text-2xl sm:text-3xl md:text-4xl font-bold text-white text-center">{t('downloadPage.pluginTitle')}</h1>
        </div>
        <p className="text-base md:text-xl text-gray-300 max-w-2xl mx-auto mb-4">
          {t('downloadPage.pluginSubtitle')}
        </p>
        <div className="inline-flex items-center gap-2 px-3 py-1.5 md:px-4 md:py-2 bg-purple-600/20 border border-purple-500/30 rounded-lg text-purple-300 text-xs md:text-sm">
          <Zap className="w-3.5 h-3.5 md:w-4 md:h-4" />
          <span>{t('downloadPage.pluginBadge')}</span>
        </div>
      </div>

      {/* Primary path — install the plugin in 3 steps */}
      <div className="mb-12 bg-white/5 backdrop-blur-sm rounded-2xl p-6 md:p-8 border border-white/10">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
          <Zap className="w-6 h-6 text-purple-400" />
          {t('downloadPage.stepsTitle')}
        </h2>
        <div className="grid md:grid-cols-3 gap-4 md:gap-6">
          {/* Step 1 — get official OrcaSlicer */}
          <div className="bg-white/5 rounded-xl p-5 border border-white/10 flex flex-col">
            <div className="flex items-center gap-3 mb-3 md:min-h-14">
              <span className="w-8 h-8 rounded-full bg-purple-600/30 border border-purple-500/40 text-purple-200 font-bold flex items-center justify-center">1</span>
              <h3 className="text-lg font-semibold text-white">{t('downloadPage.step1Title')}</h3>
            </div>
            <p className="text-gray-300 text-sm mb-4 md:min-h-[5rem]">{t('downloadPage.step1Desc')}</p>
            <DownloadScreenshotCardImage
              src="/download-media/step-download-orca.webp"
              alt={t('downloadPage.step1ShotAlt')}
              comingSoonLabel={t('downloadPage.comingSoon')}
              openPreviewLabel={t('downloadPage.openPreview')}
              onOpenPreview={(src, alt) => setPreviewImage({ src, alt })}
            />
            <div className="space-y-2">
              <a
                href={ORCA_OFFICIAL_DOWNLOAD_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex w-full items-center justify-center gap-2 px-4 py-2 bg-white/10 hover:bg-white/20 border border-white/20 text-white text-sm font-medium rounded-lg transition-all"
              >
                <Download className="w-4 h-4" />
                <span>{t('downloadPage.step1Cta')}</span>
                <ExternalLink className="w-3 h-3" />
              </a>
              <a
                href={orcaRelease?.url || ORCA_RELEASES_LATEST_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-purple-300 hover:text-purple-200 transition-colors"
              >
                <span>
                  {orcaRelease
                    ? t('downloadPage.step1Release', { tag: orcaRelease.tag })
                    : t('downloadPage.step1ReleaseFallback')}
                </span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </div>

          {/* Step 2 — subscribe to the plugin in the Plugin Hub */}
          <div className="bg-white/5 rounded-xl p-5 border border-white/10 flex flex-col">
            <div className="flex items-center gap-3 mb-3 md:min-h-14">
              <span className="w-8 h-8 rounded-full bg-purple-600/30 border border-purple-500/40 text-purple-200 font-bold flex items-center justify-center">2</span>
              <h3 className="text-lg font-semibold text-white">{t('downloadPage.step2Title')}</h3>
            </div>
            <p className="text-gray-300 text-sm mb-4 md:min-h-[5rem]">{t('downloadPage.step2Desc')}</p>
            <DownloadScreenshotCardImage
              src="/download-media/step-install-plugin.webp"
              alt={t('downloadPage.step2ShotAlt')}
              comingSoonLabel={t('downloadPage.comingSoon')}
              openPreviewLabel={t('downloadPage.openPreview')}
              onOpenPreview={(src, alt) => setPreviewImage({ src, alt })}
            />
            <div className="space-y-2">
              <a
                href={FILAMENTHUB_PLUGIN_HUB_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex w-full items-center justify-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white text-sm font-medium rounded-lg transition-all"
              >
                <Package className="w-4 h-4" />
                <span>{t('downloadPage.step2Cta')}</span>
                <ExternalLink className="w-3 h-3" />
              </a>
              {orcaPluginWheel && (
                <a
                  href={orcaPluginWheel.url}
                  download={orcaPluginWheel.name}
                  className="inline-flex items-center gap-1 text-xs text-purple-300 hover:text-purple-200 transition-colors"
                >
                  <Download className="w-3 h-3" />
                  <span>
                    {wheelPackageVersion(orcaPluginWheel.name)
                      ? t('downloadPage.step2WheelCta', {
                        version: wheelPackageVersion(orcaPluginWheel.name),
                      })
                      : t('downloadPage.step2WheelCtaPlain')}
                  </span>
                </a>
              )}
              <p className="text-gray-500 text-xs">{t('downloadPage.step2Sideload')}</p>
            </div>
          </div>

          {/* Step 3 — open FilamentHub */}
          <div className="bg-white/5 rounded-xl p-5 border border-white/10 flex flex-col">
            <div className="flex items-center gap-3 mb-3 md:min-h-14">
              <span className="w-8 h-8 rounded-full bg-purple-600/30 border border-purple-500/40 text-purple-200 font-bold flex items-center justify-center">3</span>
              <h3 className="text-lg font-semibold text-white">{t('downloadPage.step3Title')}</h3>
            </div>
            <p className="text-gray-300 text-sm mb-4 md:min-h-[5rem]">{t('downloadPage.step3Desc')}</p>
            <DownloadScreenshotCardImage
              src="/download-media/step-open-filamenthub.webp"
              alt={t('downloadPage.step3ShotAlt')}
              comingSoonLabel={t('downloadPage.comingSoon')}
              openPreviewLabel={t('downloadPage.openPreview')}
              onOpenPreview={(src, alt) => setPreviewImage({ src, alt })}
            />
          </div>
        </div>
      </div>

      {/* OctoPrint companion plugin */}
      <section className="relative mb-12 overflow-hidden rounded-2xl border border-cyan-400/20 bg-slate-950/45 shadow-[0_24px_80px_rgba(6,182,212,0.08)]">
        <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-cyan-400/10 blur-3xl" />
        <div className="relative grid gap-0 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="p-6 md:p-8">
            <div className="mb-5 flex flex-wrap items-center gap-3">
              <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl border border-cyan-300/20 bg-cyan-400/10 text-cyan-200">
                <Server className="h-6 w-6" />
              </span>
              <div>
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <h2 className="text-xl font-bold text-white md:text-2xl">
                    {t('downloadPage.octoTitle')}
                  </h2>
                  <span className="rounded-full border border-cyan-300/20 bg-cyan-400/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-cyan-200">
                    OctoPrint
                  </span>
                </div>
                <p className="text-sm text-slate-400">{t('downloadPage.octoTagline')}</p>
              </div>
            </div>

            <p className="max-w-2xl text-sm leading-6 text-slate-300 md:text-base">
              {t('downloadPage.octoDesc')}
            </p>

            <div className="mt-6 grid gap-3 sm:grid-cols-3">
              <div className="border-l-2 border-cyan-400/50 pl-3">
                <ShieldCheck className="mb-2 h-4 w-4 text-cyan-300" />
                <p className="text-xs leading-5 text-slate-300">{t('downloadPage.octoFeatureOutbound')}</p>
              </div>
              <div className="border-l-2 border-purple-400/50 pl-3">
                <RefreshCw className="mb-2 h-4 w-4 text-purple-300" />
                <p className="text-xs leading-5 text-slate-300">{t('downloadPage.octoFeatureSync')}</p>
              </div>
              <div className="border-l-2 border-emerald-400/50 pl-3">
                <CheckCircle className="mb-2 h-4 w-4 text-emerald-300" />
                <p className="text-xs leading-5 text-slate-300">{t('downloadPage.octoFeatureUsage')}</p>
              </div>
            </div>
          </div>

          <div className="border-t border-white/10 bg-white/[0.035] p-6 md:p-8 lg:border-l lg:border-t-0">
            <p className="mb-4 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
              {t('downloadPage.octoInstallTitle')}
            </p>
            <ol className="mb-6 space-y-3 text-sm text-slate-300">
              <li className="flex gap-3">
                <span className="text-cyan-300">01</span>
                <span>{t('downloadPage.octoInstall1')}</span>
              </li>
              <li className="flex gap-3">
                <span className="text-cyan-300">02</span>
                <span>{t('downloadPage.octoInstall2')}</span>
              </li>
              <li className="flex gap-3">
                <span className="text-cyan-300">03</span>
                <span>{t('downloadPage.octoInstall3')}</span>
              </li>
            </ol>

            <a
              href={octoPrintBridgeWheel?.url || pluginsReleaseUrl}
              download={octoPrintBridgeWheel?.name}
              target={octoPrintBridgeWheel ? undefined : '_blank'}
              rel={octoPrintBridgeWheel ? undefined : 'noopener noreferrer'}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-500 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-300/70"
            >
              <Download className="h-4 w-4" />
              <span>
                {octoPrintBridgeWheel
                  ? t('downloadPage.octoDownload', {
                    version: wheelPackageVersion(octoPrintBridgeWheel.name),
                  })
                  : t('downloadPage.octoOpenReleases')}
              </span>
              {!octoPrintBridgeWheel && <ExternalLink className="h-3.5 w-3.5" />}
            </a>
            <p className="mt-3 break-all text-center text-[11px] text-slate-500">
              {octoPrintBridgeWheel?.name || t('downloadPage.octoReleasePending')}
            </p>
          </div>
        </div>
      </section>

      {/* Independent plugin from the same team — not part of the FilamentHub setup path. */}
      <section className="mb-12 overflow-hidden rounded-2xl border border-emerald-300/20 bg-emerald-950/20">
        <div className="flex flex-col gap-6 p-6 md:p-8 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex max-w-2xl gap-4">
            <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-emerald-300/20 bg-emerald-400/10 text-emerald-200">
              <Monitor className="h-6 w-6" />
            </span>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-[0.14em] text-emerald-300">
                {t('downloadPage.printFarmEyebrow')}
              </p>
              <h2 className="text-xl font-bold text-white md:text-2xl">Print Farm</h2>
              <p className="mt-2 text-sm leading-6 text-slate-300 md:text-base">
                {t('downloadPage.printFarmDesc')}
              </p>
              <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-300">
                {['Moonraker / Klipper', 'OctoPrint', 'Bambu Lab LAN'].map((provider) => (
                  <span key={provider} className="rounded-full border border-white/10 bg-white/5 px-3 py-1">
                    {provider}
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div className="flex shrink-0 flex-col gap-3 lg:items-end">
            <p className="text-xs text-slate-400">{t('downloadPage.printFarmIndependent')}</p>
            <a
              href={PRINT_FARM_PLUGIN_HUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-500 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 focus:outline-none focus:ring-2 focus:ring-emerald-300/70"
            >
              <Package className="h-4 w-4" />
              <span>{t('downloadPage.printFarmCta')}</span>
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>
      </section>

      {/* Screenshots Section */}
      <div className="mb-12 bg-white/5 backdrop-blur-sm rounded-2xl p-8 border border-white/10">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
          <ImageIcon className="w-6 h-6 text-purple-400" />
          {t('downloadPage.screenshotsTitle')}
        </h2>
        
        <div className="grid md:grid-cols-2 gap-6">
          {/* Screenshot 1: FilamentHub Tab */}
          <div className="bg-white/5 rounded-xl p-4 border border-white/10">
            <DownloadScreenshotCardImage
              src="/download-media/orcaslicer-win-main.webp"
              alt={t('downloadPage.screenshotTabAlt')}
              comingSoonLabel={t('downloadPage.comingSoon')}
              openPreviewLabel={t('downloadPage.openPreview')}
              onOpenPreview={(src, alt) => setPreviewImage({ src, alt })}
              imageClassName="object-cover"
            />
            <h3 className="text-lg font-semibold text-white mb-2">{t('downloadPage.screenshotTabTitle')}</h3>
            <p className="text-gray-300 text-sm">
              {t('downloadPage.screenshotTabDesc')}
            </p>
          </div>

          {/* Screenshot 2: Catalog in OrcaSlicer */}
          <div className="bg-white/5 rounded-xl p-4 border border-white/10">
            <DownloadScreenshotCardImage
              src="/download-media/catalog-presets.webp"
              alt={t('downloadPage.screenshotCatalogAlt')}
              comingSoonLabel={t('downloadPage.comingSoon')}
              openPreviewLabel={t('downloadPage.openPreview')}
              onOpenPreview={(src, alt) => setPreviewImage({ src, alt })}
            />
            <h3 className="text-lg font-semibold text-white mb-2">{t('downloadPage.screenshotCatalogTitle')}</h3>
            <p className="text-gray-300 text-sm">
              {t('downloadPage.screenshotCatalogDesc')}
            </p>
          </div>

          {/* Screenshot 3: Sync Feature */}
          <div className="bg-white/5 rounded-xl p-4 border border-white/10">
            <DownloadScreenshotCardImage
              src="/download-media/presets-sync.webp"
              alt={t('downloadPage.screenshotSyncAlt')}
              comingSoonLabel={t('downloadPage.comingSoon')}
              openPreviewLabel={t('downloadPage.openPreview')}
              onOpenPreview={(src, alt) => setPreviewImage({ src, alt })}
            />
            <h3 className="text-lg font-semibold text-white mb-2">{t('downloadPage.screenshotSyncTitle')}</h3>
            <p className="text-gray-300 text-sm">
              {t('downloadPage.screenshotSyncDesc')}
            </p>
          </div>

          {/* Screenshot 4: Import Preset */}
          <div className="bg-white/5 rounded-xl p-4 border border-white/10">
            <DownloadScreenshotCardImage
              src="/download-media/import-one-click.webp"
              alt={t('downloadPage.screenshotImportAlt')}
              comingSoonLabel={t('downloadPage.comingSoon')}
              openPreviewLabel={t('downloadPage.openPreview')}
              onOpenPreview={(src, alt) => setPreviewImage({ src, alt })}
            />
            <h3 className="text-lg font-semibold text-white mb-2">{t('downloadPage.screenshotImportTitle')}</h3>
            <p className="text-gray-300 text-sm">
              {t('downloadPage.screenshotImportDesc')}
            </p>
          </div>
        </div>

        {/* Video placeholder (optional) */}
        <div className="mt-6 bg-gradient-to-br from-purple-900/50 to-indigo-900/50 rounded-xl p-6 border border-purple-500/30">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 bg-purple-600/30 rounded-lg flex items-center justify-center">
                <Play className="w-6 h-6 text-purple-300" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-white mb-1">{t('downloadPage.videoTitle')}</h3>
                <p className="text-sm text-gray-300">{t('downloadPage.videoDesc')}</p>
              </div>
            </div>
            <div className="aspect-video w-48 bg-gradient-to-br from-gray-800 to-gray-900 rounded-lg flex items-center justify-center border-2 border-dashed border-white/20">
              <div className="text-center">
                <ImageIcon className="w-8 h-8 text-gray-500 mx-auto mb-1" />
                <p className="text-xs text-gray-500">{t('downloadPage.videoLabel')}</p>
                <p className="text-xs text-gray-600">{t('downloadPage.comingSoon')}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {previewImage && (
        <ModalOverlay
          onClose={() => setPreviewImage(null)}
          className="bg-slate-950/85 backdrop-blur-md"
        >
          <div className="relative w-full max-w-6xl rounded-[28px] border border-white/10 bg-slate-900/92 p-3 shadow-[0_25px_120px_rgba(15,23,42,0.65)] md:p-5">
            <button
              type="button"
              onClick={() => setPreviewImage(null)}
              className="absolute right-3 top-3 z-10 inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-black/50 text-white/80 transition hover:border-white/20 hover:bg-black/70 hover:text-white"
              aria-label={t('downloadPage.closePreview')}
            >
              <X className="h-5 w-5" />
            </button>

            <div className="overflow-hidden rounded-[22px] border border-white/10 bg-black/40">
              <img
                src={previewImage.src}
                alt={previewImage.alt}
                className="max-h-[82vh] w-full object-contain"
              />
            </div>
          </div>
        </ModalOverlay>
      )}

      {/* Key Benefits */}
      <div className="bg-gradient-to-br from-purple-900/50 to-indigo-900/50 backdrop-blur-sm rounded-2xl p-8 border border-white/20 shadow-xl mb-12">
        <h2 className="text-2xl font-bold text-white mb-6 text-center">{t('downloadPage.whyTitle')}</h2>
        
        <div className="grid md:grid-cols-2 gap-6">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 bg-yellow-500/20 rounded-xl flex items-center justify-center flex-shrink-0">
              <Zap className="w-6 h-6 text-yellow-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-2">{t('downloadPage.benefitAllInOneTitle')}</h3>
              <p className="text-gray-300 text-sm">
                {t('downloadPage.benefitAllInOneDesc')}
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4">
            <div className="w-12 h-12 bg-purple-500/20 rounded-xl flex items-center justify-center flex-shrink-0">
              <Package className="w-6 h-6 text-purple-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-2">{t('downloadPage.benefitSyncTitle')}</h3>
              <p className="text-gray-300 text-sm">
                {t('downloadPage.benefitSyncDesc')}
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4">
            <div className="w-12 h-12 bg-blue-500/20 rounded-xl flex items-center justify-center flex-shrink-0">
              <Globe className="w-6 h-6 text-blue-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-2">{t('downloadPage.benefitLibraryTitle')}</h3>
              <p className="text-gray-300 text-sm">
                {t('downloadPage.benefitLibraryDesc')}
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4">
            <div className="w-12 h-12 bg-green-500/20 rounded-xl flex items-center justify-center flex-shrink-0">
              <CheckCircle className="w-6 h-6 text-green-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-2">{t('downloadPage.benefitVerifiedTitle')}</h3>
              <p className="text-gray-300 text-sm">
                {t('downloadPage.benefitVerifiedDesc')}
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4">
            <div className="w-12 h-12 bg-pink-500/20 rounded-xl flex items-center justify-center flex-shrink-0">
              <Code className="w-6 h-6 text-pink-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-2">{t('downloadPage.benefitFullTitle')}</h3>
              <p className="text-gray-300 text-sm">
                {t('downloadPage.benefitFullDesc')}
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4">
            <div className="w-12 h-12 bg-indigo-500/20 rounded-xl flex items-center justify-center flex-shrink-0">
              <Download className="w-6 h-6 text-indigo-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-2">{t('downloadPage.benefitFreeTitle')}</h3>
              <p className="text-gray-300 text-sm">
                {t('downloadPage.benefitFreeDesc')}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
    </>
  );
}
