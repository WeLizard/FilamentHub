/** Страница для скачивания OrcaSlicer с интегрированным FilamentHub */

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Download, CheckCircle, Package, Code, Zap, Globe, Monitor, Smartphone, Terminal, Image as ImageIcon, Play, Loader2, ExternalLink } from 'lucide-react';
import { downloadsAPI } from '../api/client';
import type { DownloadVersion, DownloadVersionsResponse } from '../types/api';

export function DownloadPage() {
  const { t } = useTranslation();
  const [selectedPlatform, setSelectedPlatform] = useState<'windows' | 'macos' | 'linux'>('windows');
  const [selectedArch, setSelectedArch] = useState<'x64' | 'arm64'>('x64');
  const [downloadsData, setDownloadsData] = useState<DownloadVersionsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Загружаем данные с API
  useEffect(() => {
    const loadDownloads = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const data = await downloadsAPI.getOrcaSlicerDownloads();
        setDownloadsData(data);
      } catch (err) {
        console.error('Failed to load downloads:', err);
        setError(t('downloadPage.errorLoadFailed'));
      } finally {
        setIsLoading(false);
      }
    };

    loadDownloads();
  }, []);

  // Определяем доступность платформы из данных API
  const isPlatformAvailable = (platform: string) =>
    downloadsData?.versions.some(v => v.platform === platform && v.available) ?? false;

  // Находим версию (приоритет: installer, потом portable)
  const currentVersion = downloadsData?.versions.find(
    (v) => v.platform === selectedPlatform && 
           v.architecture === selectedArch &&
           (v.download_type === 'installer' || (!v.download_type && v.available))
  ) || downloadsData?.versions.find(
    (v) => v.platform === selectedPlatform && 
           v.architecture === selectedArch &&
           v.download_type === 'portable'
  ) || downloadsData?.versions.find(
    (v) => v.platform === selectedPlatform && v.architecture === selectedArch
  );
  const selectedPlatformHasAvailableBuild = isPlatformAvailable(selectedPlatform);
  const hasWindowsInstaller = Boolean(downloadsData?.versions.some(
    (v) => v.platform === 'windows' &&
           v.architecture === selectedArch &&
           v.download_type === 'installer' &&
           v.available
  ));
  const hasWindowsPortable = Boolean(downloadsData?.versions.some(
    (v) => v.platform === 'windows' &&
           v.architecture === selectedArch &&
           v.download_type === 'portable' &&
           v.available
  ));
  const hasWindowsRelease = hasWindowsInstaller && hasWindowsPortable;
  const showDetailedCard = Boolean(
    currentVersion && (
      selectedPlatform === 'windows'
        ? hasWindowsRelease
        : selectedPlatformHasAvailableBuild
    )
  );

  const handleDownload = (downloadType?: 'installer' | 'portable' | 'github') => {
    if (!downloadsData?.versions || downloadsData.versions.length === 0) {
      alert(t('downloadPage.alertLoading'));
      return;
    }

    // Если указан тип, ищем соответствующую версию
    if (downloadType) {
      const version = downloadsData.versions.find(
        (v) => v.platform === selectedPlatform && 
               v.architecture === selectedArch && 
               v.download_type === downloadType
      );
      
      if (version?.download_url && version.available) {
        window.open(version.download_url, '_blank');
        return;
      }
      
      if (downloadType === 'github') {
        // Ищем любую версию с github_url
        const githubVersion = downloadsData.versions.find(v => v.github_url);
        if (githubVersion?.github_url) {
          window.open(githubVersion.github_url, '_blank');
          return;
        }
        // Fallback на наш репозиторий
        window.open('https://github.com/WeLizard/OrcaSlicer/releases', '_blank');
        return;
      }
    }

    // По умолчанию используем текущую версию (если есть)
    if (currentVersion?.download_url && currentVersion.available) {
      window.open(currentVersion.download_url, '_blank');
    } else if (currentVersion?.github_url) {
      window.open(currentVersion.github_url, '_blank');
    } else {
      alert(t('downloadPage.alertNotAvailable'));
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 md:px-6 py-6 md:py-12">
      {/* Header */}
      <div className="text-center mb-8 md:mb-12">
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mb-4">
          <div className="w-12 h-12 md:w-16 md:h-16 bg-gradient-to-br from-purple-500 to-pink-500 rounded-xl md:rounded-2xl flex items-center justify-center shadow-lg shadow-purple-500/25">
            <Download className="w-6 h-6 md:w-8 md:h-8 text-white" />
          </div>
          <h1 className="text-2xl sm:text-3xl md:text-4xl font-bold text-white text-center">OrcaSlicer FilamentHub Edition</h1>
        </div>
        <p className="text-base md:text-xl text-gray-300 max-w-2xl mx-auto mb-4">
          {t('downloadPage.headerSubtitle')}
        </p>
        <div className="inline-flex items-center gap-2 px-3 py-1.5 md:px-4 md:py-2 bg-purple-600/20 border border-purple-500/30 rounded-lg text-purple-300 text-xs md:text-sm">
          <Zap className="w-3.5 h-3.5 md:w-4 md:h-4" />
          <span>{t('downloadPage.uniqueIntegration')}</span>
        </div>
      </div>

      {/* Screenshots Section */}
      <div className="mb-12 bg-white/5 backdrop-blur-sm rounded-2xl p-8 border border-white/10">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
          <ImageIcon className="w-6 h-6 text-purple-400" />
          {t('downloadPage.screenshotsTitle')}
        </h2>
        
        <div className="grid md:grid-cols-2 gap-6">
          {/* Screenshot 1: FilamentHub Tab */}
          <div className="bg-white/5 rounded-xl p-4 border border-white/10">
            <div className="aspect-video overflow-hidden rounded-lg border border-white/10 bg-black/20 mb-4">
              <img
                src="/downloads/orcaslicer-win-main.png"
                alt={t('downloadPage.screenshotTabAlt')}
                className="h-full w-full object-cover"
                loading="lazy"
              />
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">{t('downloadPage.screenshotTabTitle')}</h3>
            <p className="text-gray-300 text-sm">
              {t('downloadPage.screenshotTabDesc')}
            </p>
          </div>

          {/* Screenshot 2: Catalog in OrcaSlicer */}
          <div className="bg-white/5 rounded-xl p-4 border border-white/10">
            <div className="aspect-video bg-gradient-to-br from-gray-800 to-gray-900 rounded-lg flex items-center justify-center border-2 border-dashed border-white/20 mb-4">
              <div className="text-center">
                <ImageIcon className="w-12 h-12 text-gray-500 mx-auto mb-2" />
                <p className="text-sm text-gray-500">{t('downloadPage.screenshotCatalogAlt')}</p>
                <p className="text-xs text-gray-600 mt-1">{t('downloadPage.comingSoon')}</p>
              </div>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">{t('downloadPage.screenshotCatalogTitle')}</h3>
            <p className="text-gray-300 text-sm">
              {t('downloadPage.screenshotCatalogDesc')}
            </p>
          </div>

          {/* Screenshot 3: Sync Feature */}
          <div className="bg-white/5 rounded-xl p-4 border border-white/10">
            <div className="aspect-video bg-gradient-to-br from-gray-800 to-gray-900 rounded-lg flex items-center justify-center border-2 border-dashed border-white/20 mb-4">
              <div className="text-center">
                <ImageIcon className="w-12 h-12 text-gray-500 mx-auto mb-2" />
                <p className="text-sm text-gray-500">{t('downloadPage.screenshotSyncAlt')}</p>
                <p className="text-xs text-gray-600 mt-1">{t('downloadPage.comingSoon')}</p>
              </div>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">{t('downloadPage.screenshotSyncTitle')}</h3>
            <p className="text-gray-300 text-sm">
              {t('downloadPage.screenshotSyncDesc')}
            </p>
          </div>

          {/* Screenshot 4: Import Preset */}
          <div className="bg-white/5 rounded-xl p-4 border border-white/10">
            <div className="aspect-video bg-gradient-to-br from-gray-800 to-gray-900 rounded-lg flex items-center justify-center border-2 border-dashed border-white/20 mb-4">
              <div className="text-center">
                <ImageIcon className="w-12 h-12 text-gray-500 mx-auto mb-2" />
                <p className="text-sm text-gray-500">{t('downloadPage.screenshotImportAlt')}</p>
                <p className="text-xs text-gray-600 mt-1">{t('downloadPage.comingSoon')}</p>
              </div>
            </div>
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

      {/* Download Section */}
      <div className="bg-gradient-to-br from-purple-900/50 to-indigo-900/50 backdrop-blur-sm rounded-2xl p-8 border border-white/20 shadow-xl">
        <h2 className="text-2xl font-bold text-white mb-6">{t('downloadPage.selectPlatform')}</h2>

        {/* Platform Selection */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <button
            onClick={() => {
              if (!isLoading && !isPlatformAvailable('windows')) return;
              setSelectedPlatform('windows');
              setSelectedArch('x64');
            }}
            className={`flex flex-col items-center gap-2 p-3 rounded-xl border transition-all relative ${
              !isLoading && !isPlatformAvailable('windows') ? 'opacity-60 cursor-not-allowed' : ''
            } ${
              selectedPlatform === 'windows'
                ? 'bg-purple-600/30 border-purple-500 text-white'
                : 'bg-white/5 border-white/10 text-gray-300 hover:bg-white/10'
            }`}
            disabled={!isLoading && !isPlatformAvailable('windows')}
            title={!isLoading && !isPlatformAvailable('windows') ? t('downloadPage.buildInDev', { platform: 'Windows' }) : undefined}
          >
            <Monitor className="w-8 h-8" />
            <span className="font-medium">Windows</span>
            {!isLoading && (
              isPlatformAvailable('windows')
                ? <span className="absolute top-2 right-2 px-1.5 py-0.5 bg-green-500/30 border border-green-500/50 rounded text-xs text-green-300">{t('downloadPage.badgeAvailable')}</span>
                : <span className="absolute top-2 right-2 px-1.5 py-0.5 bg-yellow-500/30 border border-yellow-500/50 rounded text-xs text-yellow-300">{t('downloadPage.badgeSoon')}</span>
            )}
          </button>
          <button
            onClick={() => {
              if (!isLoading && !isPlatformAvailable('macos')) return;
              setSelectedPlatform('macos');
              setSelectedArch('x64');
            }}
            className={`flex flex-col items-center gap-2 p-3 rounded-xl border transition-all relative ${
              !isLoading && !isPlatformAvailable('macos') ? 'opacity-60 cursor-not-allowed' : ''
            } ${
              selectedPlatform === 'macos'
                ? 'bg-purple-600/30 border-purple-500 text-white'
                : 'bg-white/5 border-white/10 text-gray-300 hover:bg-white/10'
            }`}
            disabled={!isLoading && !isPlatformAvailable('macos')}
            title={!isLoading && !isPlatformAvailable('macos') ? t('downloadPage.buildInDev', { platform: 'macOS' }) : undefined}
          >
            <Smartphone className="w-8 h-8" />
            <span className="font-medium">macOS</span>
            {!isLoading && (
              isPlatformAvailable('macos')
                ? <span className="absolute top-2 right-2 px-1.5 py-0.5 bg-green-500/30 border border-green-500/50 rounded text-xs text-green-300">{t('downloadPage.badgeAvailable')}</span>
                : <span className="absolute top-2 right-2 px-1.5 py-0.5 bg-yellow-500/30 border border-yellow-500/50 rounded text-xs text-yellow-300">{t('downloadPage.badgeSoon')}</span>
            )}
          </button>
          <button
            onClick={() => {
              if (!isLoading && !isPlatformAvailable('linux')) return;
              setSelectedPlatform('linux');
              setSelectedArch('x64');
            }}
            className={`flex flex-col items-center gap-2 p-3 rounded-xl border transition-all relative ${
              !isLoading && !isPlatformAvailable('linux') ? 'opacity-60 cursor-not-allowed' : ''
            } ${
              selectedPlatform === 'linux'
                ? 'bg-purple-600/30 border-purple-500 text-white'
                : 'bg-white/5 border-white/10 text-gray-300 hover:bg-white/10'
            }`}
            disabled={!isLoading && !isPlatformAvailable('linux')}
            title={!isLoading && !isPlatformAvailable('linux') ? t('downloadPage.buildInDev', { platform: 'Linux' }) : undefined}
          >
            <Terminal className="w-8 h-8" />
            <span className="font-medium">Linux</span>
            {!isLoading && (
              isPlatformAvailable('linux')
                ? <span className="absolute top-2 right-2 px-1.5 py-0.5 bg-green-500/30 border border-green-500/50 rounded text-xs text-green-300">{t('downloadPage.badgeAvailable')}</span>
                : <span className="absolute top-2 right-2 px-1.5 py-0.5 bg-yellow-500/30 border border-yellow-500/50 rounded text-xs text-yellow-300">{t('downloadPage.badgeSoon')}</span>
            )}
          </button>
        </div>

        {/* Architecture Selection (for macOS) */}
        {selectedPlatform === 'macos' && (
          <div className="flex gap-3 mb-6">
            <button
              onClick={() => setSelectedArch('x64')}
              className={`px-4 py-2 rounded-lg border transition-all ${
                selectedArch === 'x64'
                  ? 'bg-purple-600/30 border-purple-500 text-white'
                  : 'bg-white/5 border-white/10 text-gray-300 hover:bg-white/10'
              }`}
            >
              Intel (x64)
            </button>
            <button
              onClick={() => setSelectedArch('arm64')}
              className={`px-4 py-2 rounded-lg border transition-all ${
                selectedArch === 'arm64'
                  ? 'bg-purple-600/30 border-purple-500 text-white'
                  : 'bg-white/5 border-white/10 text-gray-300 hover:bg-white/10'
              }`}
            >
              Apple Silicon (ARM64)
            </button>
          </div>
        )}

        {/* Download Info */}
        {isLoading ? (
          <div className="bg-white/5 rounded-xl p-6 border border-white/10 mb-6">
            <div className="flex items-center justify-center gap-3 py-8">
              <Loader2 className="w-6 h-6 animate-spin text-purple-400" />
              <span className="text-gray-300">{t('downloadPage.loadingBuilds')}</span>
            </div>
          </div>
        ) : error ? (
          <div className="bg-red-900/20 border border-red-500/30 rounded-xl p-6 mb-6">
            <p className="text-red-300">{error}</p>
          </div>
        ) : showDetailedCard && currentVersion ? (
          <div className="bg-white/5 rounded-xl p-6 border border-white/10 mb-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold text-white mb-2">
                  OrcaSlicer FilamentHub Edition {currentVersion.version}
                </h3>
                <p className="text-gray-300 text-sm">
                  {selectedPlatform === 'windows' && 'Windows 10/11'}
                  {selectedPlatform === 'macos' && `macOS ${selectedArch === 'arm64' ? '(Apple Silicon)' : '(Intel)'}`}
                  {selectedPlatform === 'linux' && 'Linux'}
                  {' · '}
                  {currentVersion.architecture.toUpperCase()}
                  {' · '}
                  {t('downloadPage.fileSize')}: {currentVersion.file_size || 'N/A'}
                </p>
              </div>
            </div>

            {/* Download Buttons */}
            <div className="space-y-3">
              {/* Для Windows показываем оба варианта */}
              {selectedPlatform === 'windows' && downloadsData?.versions ? (
                <>
                  {/* Установщик */}
                  {hasWindowsInstaller && (
                    <button
                      onClick={() => handleDownload('installer')}
                      className="w-full flex items-center justify-center gap-3 px-6 py-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white font-semibold rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-xl hover:shadow-purple-500/30"
                    >
                      <Download className="w-5 h-5" />
                      <span>{t('downloadPage.downloadInstaller')}</span>
                    </button>
                  )}

                  {/* Portable версия */}
                  {hasWindowsPortable && (
                    <button
                      onClick={() => handleDownload('portable')}
                      className="w-full flex items-center justify-center gap-3 px-6 py-4 bg-white/10 hover:bg-white/20 border border-white/20 text-white font-semibold rounded-xl transition-all"
                    >
                      <Package className="w-5 h-5" />
                      <span>{t('downloadPage.downloadPortable')}</span>
                    </button>
                  )}
                </>
              ) : (
                /* Для других платформ - основная кнопка */
                currentVersion.available && currentVersion.download_url ? (
                  <button
                    onClick={() => handleDownload()}
                    className="w-full flex items-center justify-center gap-3 px-6 py-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white font-semibold rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-xl hover:shadow-purple-500/30"
                  >
                    <Download className="w-5 h-5" />
                    <span>
                      {currentVersion.download_type === 'portable' ? t('downloadPage.downloadPortable') : t('downloadPage.downloadInstallerGeneric')}
                    </span>
                  </button>
                ) : null
              )}

              {/* Если нет доступных версий, показываем GitHub */}
              {selectedPlatform !== 'windows' && !currentVersion.available && currentVersion.github_url && (
                <button
                  onClick={() => handleDownload('github')}
                  className="w-full flex items-center justify-center gap-3 px-6 py-4 bg-white/10 hover:bg-white/20 border border-white/20 text-white font-semibold rounded-xl transition-all"
                >
                  <Globe className="w-5 h-5" />
                  <span>{t('downloadPage.downloadFromGithub')}</span>
                </button>
              )}
            </div>

            {currentVersion.checksum && (
              <p className="text-xs text-gray-400 mt-4 text-center">
                SHA256: {currentVersion.checksum}
              </p>
            )}

            {/* Информация о типах дистрибутивов */}
            {selectedPlatform === 'windows' && (
              <div className="mt-4 pt-4 border-t border-white/10">
                <p className="text-xs text-gray-400 mb-2">
                  <strong className="text-gray-300">{t('downloadPage.installerLabel')}:</strong> {t('downloadPage.installerDesc')}
                </p>
                <p className="text-xs text-gray-400 mb-3">
                  <strong className="text-gray-300">{t('downloadPage.portableLabel')}:</strong> {t('downloadPage.portableDesc')}
                </p>
                {/* GitHub ссылка */}
                <a
                  href="https://github.com/WeLizard/OrcaSlicer/releases"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-center gap-2 text-gray-300 hover:text-white transition-colors text-sm pt-2 border-t border-white/5"
                >
                  <Globe className="w-4 h-4" />
                  <span>{t('downloadPage.alsoOnGithub')}</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            )}
          </div>
        ) : (
          <div className="bg-yellow-900/20 border border-yellow-500/30 rounded-xl p-6 mb-6">
            <div className="flex items-start gap-4">
              <Package className="w-6 h-6 text-yellow-400 flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="text-lg font-semibold text-yellow-300 mb-2">
                  {t('downloadPage.buildInDev', { platform: selectedPlatform === 'windows' ? 'Windows' : selectedPlatform === 'macos' ? 'macOS' : 'Linux' })}
                </h3>
                <p className="text-gray-300 text-sm mb-2">
                  {t('downloadPage.buildNotReady', { platform: selectedPlatform === 'windows' ? 'Windows' : selectedPlatform === 'macos' ? 'macOS' : 'Linux' })}
                </p>
                <p className="text-gray-400 text-xs mb-3">
                  {t('downloadPage.buildFromSource')}
                </p>
                <button
                  onClick={() => handleDownload('github')}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-white/10 hover:bg-white/20 border border-white/20 text-white text-sm font-medium rounded-lg transition-all"
                >
                  <Globe className="w-4 h-4" />
                  <span>{t('downloadPage.downloadFromGithub')}</span>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Info */}
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <CheckCircle className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-blue-300">
              <p className="font-medium mb-1">{t('downloadPage.includedTitle')}</p>
              <ul className="list-disc list-inside space-y-1 text-xs">
                <li>{t('downloadPage.included1')}</li>
                <li>{t('downloadPage.included2')}</li>
                <li>{t('downloadPage.included3')}</li>
                <li>{t('downloadPage.included4')}</li>
                <li>{t('downloadPage.included5')}</li>
                <li>{t('downloadPage.included6')}</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      {/* Installation Instructions */}
      <div className="mt-12 bg-white/5 backdrop-blur-sm rounded-xl p-8 border border-white/10">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
          <Code className="w-6 h-6 text-purple-400" />
          {t('downloadPage.installTitle')}
        </h2>

        <div className="space-y-6">
          {selectedPlatform === 'windows' && (
            <div>
              <h3 className="text-lg font-semibold text-white mb-3">Windows</h3>
              <ol className="list-decimal list-inside space-y-2 text-gray-300">
                <li>{t('downloadPage.installWin1')}</li>
                <li>{t('downloadPage.installWin2')}</li>
                <li>{t('downloadPage.installWin3')}</li>
                <li>{t('downloadPage.installWin4')}</li>
              </ol>
            </div>
          )}

          {selectedPlatform === 'macos' && (
            <div>
              <h3 className="text-lg font-semibold text-white mb-3">{t('downloadPage.installMacTitle')}</h3>
              <div className="bg-yellow-900/20 border border-yellow-500/30 rounded-lg p-4 mb-3">
                <p className="text-yellow-300 text-sm">
                  {t('downloadPage.installMacNotice')}
                </p>
              </div>
              <p className="text-gray-400 text-sm mb-3">
                {t('downloadPage.installMacAfterRelease')}
              </p>
              <ol className="list-decimal list-inside space-y-2 text-gray-300 opacity-60">
                <li>{t('downloadPage.installMac1')}</li>
                <li>{t('downloadPage.installMac2')}</li>
                <li>{t('downloadPage.installMac3')}</li>
                <li>{t('downloadPage.installMac4')}</li>
                <li>{t('downloadPage.installMac5')}</li>
              </ol>
            </div>
          )}

          {selectedPlatform === 'linux' && (
            <div>
              <h3 className="text-lg font-semibold text-white mb-3">Linux</h3>
              <ol className="list-decimal list-inside space-y-2 text-gray-300">
                <li>{t('downloadPage.installLinux1')}</li>
                <li>{t('downloadPage.installLinux2Prefix')} <code className="bg-white/10 px-2 py-1 rounded text-purple-300">chmod +x OrcaSlicer*.AppImage</code></li>
                <li>{t('downloadPage.installLinux3Prefix')} <code className="bg-white/10 px-2 py-1 rounded text-purple-300">./OrcaSlicer*.AppImage</code></li>
                <li>{t('downloadPage.installLinux4')}</li>
                <li>{t('downloadPage.installLinux5')}</li>
              </ol>
              <div className="mt-4 bg-blue-900/20 border border-blue-500/30 rounded-lg p-3">
                <p className="text-blue-300 text-sm">
                  <strong>{t('downloadPage.note')}:</strong> {t('downloadPage.installLinuxNote')}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* FAQ */}
      <div className="mt-12 bg-white/5 backdrop-blur-sm rounded-xl p-8 border border-white/10">
        <h2 className="text-2xl font-bold text-white mb-6">{t('downloadPage.faqTitle')}</h2>
        
        <div className="space-y-6">
          <div>
            <h3 className="text-lg font-semibold text-white mb-2">
              {t('downloadPage.faq1Q')}
            </h3>
            <p className="text-gray-300 mb-2">
              {t('downloadPage.faq1A1_pre')}<strong className="text-white">{t('downloadPage.faq1A1_bold')}</strong>{t('downloadPage.faq1A1_post')}
            </p>
            <p className="text-gray-300">
              <strong className="text-white">{t('downloadPage.faq1A2_bold')}</strong> {t('downloadPage.faq1A2_text')}
            </p>
          </div>

          <div>
            <h3 className="text-lg font-semibold text-white mb-2">
              {t('downloadPage.faq2Q')}
            </h3>
            <p className="text-gray-300">
              <strong className="text-white">{t('downloadPage.faq2A_bold')}</strong> {t('downloadPage.faq2A_text')}
            </p>
          </div>

          <div>
            <h3 className="text-lg font-semibold text-white mb-2">
              {t('downloadPage.faq3Q')}
            </h3>
            <p className="text-gray-300">
              {t('downloadPage.faq3A')}
            </p>
          </div>

          <div>
            <h3 className="text-lg font-semibold text-white mb-2">
              {t('downloadPage.faq4Q')}
            </h3>
            <p className="text-gray-300 mb-2">
              <strong className="text-white">{t('downloadPage.faq4A1_bold')}</strong> {t('downloadPage.faq4A1_text')}
            </p>
            <p className="text-gray-300">
              {t('downloadPage.faq4A2')}
            </p>
          </div>

          <div>
            <h3 className="text-lg font-semibold text-white mb-2">
              {t('downloadPage.faq5Q')}
            </h3>
            <p className="text-gray-300">
              {t('downloadPage.faq5A')}
            </p>
          </div>

          <div>
            <h3 className="text-lg font-semibold text-white mb-2">
              {t('downloadPage.faq6Q')}
            </h3>
            <p className="text-gray-300 mb-2">
              {t('downloadPage.faq6A1_pre')}<strong className="text-white">Windows</strong>{t('downloadPage.faq6A1_mid')}<strong className="text-white">Linux</strong>{t('downloadPage.faq6A1_mid2')}<strong className="text-white">macOS</strong>{t('downloadPage.faq6A1_post')}
            </p>
            <p className="text-gray-300">
              <strong className="text-white">{t('downloadPage.faq6A2_bold')}</strong> {t('downloadPage.faq6A2_text')}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
