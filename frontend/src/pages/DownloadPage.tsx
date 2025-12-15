/** Страница для скачивания OrcaSlicer с интегрированным FilamentHub */

import { useState, useEffect } from 'react';
import { Download, CheckCircle, Package, Code, Zap, Globe, Monitor, Smartphone, Terminal, Image as ImageIcon, Play, Loader2, ExternalLink } from 'lucide-react';
import { downloadsAPI } from '../api/client';
import type { DownloadVersion, DownloadVersionsResponse } from '../types/api';

export function DownloadPage() {
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
        setError('Не удалось загрузить информацию о сборках');
      } finally {
        setIsLoading(false);
      }
    };

    loadDownloads();
  }, []);

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

  const handleDownload = (downloadType?: 'installer' | 'portable' | 'github') => {
    if (!downloadsData?.versions || downloadsData.versions.length === 0) {
      alert('Информация о сборках ещё загружается. Пожалуйста, подождите...');
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
        window.open('https://github.com/lizardjazz1/OrcaSlicer/releases', '_blank');
        return;
      }
    }

    // По умолчанию используем текущую версию (если есть)
    if (currentVersion?.download_url && currentVersion.available) {
      window.open(currentVersion.download_url, '_blank');
    } else if (currentVersion?.github_url) {
      window.open(currentVersion.github_url, '_blank');
    } else {
      alert('Сборка ещё не доступна. Скоро будет доступна для скачивания!');
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
          Единственная версия OrcaSlicer с интегрированным каталогом материалов
        </p>
        <div className="inline-flex items-center gap-2 px-3 py-1.5 md:px-4 md:py-2 bg-purple-600/20 border border-purple-500/30 rounded-lg text-purple-300 text-xs md:text-sm">
          <Zap className="w-3.5 h-3.5 md:w-4 md:h-4" />
          <span>Уникальная интеграция!</span>
        </div>
      </div>

      {/* Screenshots Section - скрыто на мобильных пока нет реальных скриншотов */}
      <div className="hidden md:block mb-8 md:mb-12 bg-white/5 backdrop-blur-sm rounded-xl md:rounded-2xl p-4 md:p-8 border border-white/10">
        <h2 className="text-xl md:text-2xl font-bold text-white mb-4 md:mb-6 flex items-center gap-2">
          <ImageIcon className="w-5 h-5 md:w-6 md:h-6 text-purple-400" />
          Как это выглядит
        </h2>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
          {/* Screenshot 1: FilamentHub Tab */}
          <div className="bg-white/5 rounded-lg md:rounded-xl p-3 md:p-4 border border-white/10">
            <div className="aspect-video bg-gradient-to-br from-gray-800 to-gray-900 rounded-lg flex items-center justify-center border-2 border-dashed border-white/20 mb-3 md:mb-4">
              <div className="text-center px-4">
                <ImageIcon className="w-8 h-8 md:w-12 md:h-12 text-gray-500 mx-auto mb-2" />
                <p className="text-xs md:text-sm text-gray-500">Вкладка FilamentHub</p>
              </div>
            </div>
            <h3 className="text-base md:text-lg font-semibold text-white mb-1 md:mb-2">Вкладка FilamentHub</h3>
            <p className="text-gray-300 text-xs md:text-sm">
              Новая вкладка прямо в главном окне OrcaSlicer — каталог материалов и синхронизация пресетов.
            </p>
          </div>

          {/* Screenshot 2: Catalog in OrcaSlicer */}
          <div className="bg-white/5 rounded-lg md:rounded-xl p-3 md:p-4 border border-white/10">
            <div className="aspect-video bg-gradient-to-br from-gray-800 to-gray-900 rounded-lg flex items-center justify-center border-2 border-dashed border-white/20 mb-3 md:mb-4">
              <div className="text-center px-4">
                <ImageIcon className="w-8 h-8 md:w-12 md:h-12 text-gray-500 mx-auto mb-2" />
                <p className="text-xs md:text-sm text-gray-500">Каталог материалов</p>
              </div>
            </div>
            <h3 className="text-base md:text-lg font-semibold text-white mb-1 md:mb-2">Каталог материалов</h3>
            <p className="text-gray-300 text-xs md:text-sm">
              Просматривайте настройки, фильтруйте и импортируйте пресеты.
            </p>
          </div>

          {/* Screenshot 3: Sync Feature */}
          <div className="bg-white/5 rounded-lg md:rounded-xl p-3 md:p-4 border border-white/10">
            <div className="aspect-video bg-gradient-to-br from-gray-800 to-gray-900 rounded-lg flex items-center justify-center border-2 border-dashed border-white/20 mb-3 md:mb-4">
              <div className="text-center px-4">
                <ImageIcon className="w-8 h-8 md:w-12 md:h-12 text-gray-500 mx-auto mb-2" />
                <p className="text-xs md:text-sm text-gray-500">Синхронизация</p>
              </div>
            </div>
            <h3 className="text-base md:text-lg font-semibold text-white mb-1 md:mb-2">Синхронизация пресетов</h3>
            <p className="text-gray-300 text-xs md:text-sm">
              Автоматическая синхронизация настроек между устройствами.
            </p>
          </div>

          {/* Screenshot 4: Import Preset */}
          <div className="bg-white/5 rounded-lg md:rounded-xl p-3 md:p-4 border border-white/10">
            <div className="aspect-video bg-gradient-to-br from-gray-800 to-gray-900 rounded-lg flex items-center justify-center border-2 border-dashed border-white/20 mb-3 md:mb-4">
              <div className="text-center px-4">
                <ImageIcon className="w-8 h-8 md:w-12 md:h-12 text-gray-500 mx-auto mb-2" />
                <p className="text-xs md:text-sm text-gray-500">Импорт одним кликом</p>
              </div>
            </div>
            <h3 className="text-base md:text-lg font-semibold text-white mb-1 md:mb-2">Импорт одним кликом</h3>
            <p className="text-gray-300 text-xs md:text-sm">
              Импортируйте пресет прямо в OrcaSlicer без ручного копирования.
            </p>
          </div>
        </div>
      </div>

      {/* Key Benefits */}
      <div className="bg-gradient-to-br from-purple-900/50 to-indigo-900/50 backdrop-blur-sm rounded-xl md:rounded-2xl p-4 md:p-8 border border-white/20 shadow-xl mb-8 md:mb-12">
        <h2 className="text-lg md:text-2xl font-bold text-white mb-4 md:mb-6 text-center">Почему FilamentHub Edition?</h2>
        
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 md:gap-6">
          <div className="flex items-start gap-3 md:gap-4">
            <div className="w-10 h-10 md:w-12 md:h-12 bg-yellow-500/20 rounded-lg md:rounded-xl flex items-center justify-center flex-shrink-0">
              <Zap className="w-5 h-5 md:w-6 md:h-6 text-yellow-400" />
            </div>
            <div>
              <h3 className="text-sm md:text-lg font-semibold text-white mb-1">Всё в одном месте</h3>
              <p className="text-gray-300 text-xs md:text-sm">
                Каталог материалов, поиск и импорт — прямо в OrcaSlicer.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-3 md:gap-4">
            <div className="w-10 h-10 md:w-12 md:h-12 bg-purple-500/20 rounded-lg md:rounded-xl flex items-center justify-center flex-shrink-0">
              <Package className="w-5 h-5 md:w-6 md:h-6 text-purple-400" />
            </div>
            <div>
              <h3 className="text-sm md:text-lg font-semibold text-white mb-1">Авто-синхронизация</h3>
              <p className="text-gray-300 text-xs md:text-sm">
                Пресеты синхронизируются между устройствами автоматически.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-3 md:gap-4">
            <div className="w-10 h-10 md:w-12 md:h-12 bg-blue-500/20 rounded-lg md:rounded-xl flex items-center justify-center flex-shrink-0">
              <Globe className="w-5 h-5 md:w-6 md:h-6 text-blue-400" />
            </div>
            <div>
              <h3 className="text-sm md:text-lg font-semibold text-white mb-1">Библиотека настроек</h3>
              <p className="text-gray-300 text-xs md:text-sm">
                Тысячи проверенных настроек от сообщества и производителей.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-3 md:gap-4">
            <div className="w-10 h-10 md:w-12 md:h-12 bg-green-500/20 rounded-lg md:rounded-xl flex items-center justify-center flex-shrink-0">
              <CheckCircle className="w-5 h-5 md:w-6 md:h-6 text-green-400" />
            </div>
            <div>
              <h3 className="text-sm md:text-lg font-semibold text-white mb-1">Проверенные настройки</h3>
              <p className="text-gray-300 text-xs md:text-sm">
                Настройки с высоким рейтингом и процентом успеха.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-3 md:gap-4">
            <div className="w-10 h-10 md:w-12 md:h-12 bg-pink-500/20 rounded-lg md:rounded-xl flex items-center justify-center flex-shrink-0">
              <Code className="w-5 h-5 md:w-6 md:h-6 text-pink-400" />
            </div>
            <div>
              <h3 className="text-sm md:text-lg font-semibold text-white mb-1">100% OrcaSlicer</h3>
              <p className="text-gray-300 text-xs md:text-sm">
                Полная версия слайсера — ничего не убрали.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-3 md:gap-4">
            <div className="w-10 h-10 md:w-12 md:h-12 bg-indigo-500/20 rounded-lg md:rounded-xl flex items-center justify-center flex-shrink-0">
              <Download className="w-5 h-5 md:w-6 md:h-6 text-indigo-400" />
            </div>
            <div>
              <h3 className="text-sm md:text-lg font-semibold text-white mb-1">Бесплатно</h3>
              <p className="text-gray-300 text-xs md:text-sm">
                Открытый исходный код, прозрачно и безопасно.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Download Section */}
      <div className="bg-gradient-to-br from-purple-900/50 to-indigo-900/50 backdrop-blur-sm rounded-xl md:rounded-2xl p-4 md:p-8 border border-white/20 shadow-xl">
        <h2 className="text-lg md:text-2xl font-bold text-white mb-4 md:mb-6">Выберите платформу</h2>

        {/* Platform Selection */}
        <div className="grid grid-cols-3 gap-2 md:gap-4 mb-4 md:mb-6">
          <button
            onClick={() => {
              setSelectedPlatform('windows');
              setSelectedArch('x64');
            }}
            className={`flex flex-col items-center gap-1.5 md:gap-2 p-2 md:p-3 rounded-lg md:rounded-xl border transition-all relative ${
              selectedPlatform === 'windows'
                ? 'bg-purple-600/30 border-purple-500 text-white'
                : 'bg-white/5 border-white/10 text-gray-300 hover:bg-white/10 active:bg-white/15'
            }`}
          >
            <Monitor className="w-6 h-6 md:w-8 md:h-8" />
            <span className="font-medium text-xs md:text-base">Windows</span>
            <span className="absolute top-1 right-1 md:top-2 md:right-2 px-1 md:px-1.5 py-0.5 bg-green-500/30 border border-green-500/50 rounded text-[10px] md:text-xs text-green-300">✓</span>
          </button>
          <button
            onClick={() => {
              setSelectedPlatform('macos');
              setSelectedArch('x64');
            }}
            className={`flex flex-col items-center gap-1.5 md:gap-2 p-2 md:p-3 rounded-lg md:rounded-xl border transition-all relative opacity-60 cursor-not-allowed ${
              selectedPlatform === 'macos'
                ? 'bg-purple-600/30 border-purple-500 text-white'
                : 'bg-white/5 border-white/10 text-gray-300'
            }`}
            disabled
          >
            <Smartphone className="w-6 h-6 md:w-8 md:h-8" />
            <span className="font-medium text-xs md:text-base">macOS</span>
            <span className="absolute top-1 right-1 md:top-2 md:right-2 px-1 md:px-1.5 py-0.5 bg-yellow-500/30 border border-yellow-500/50 rounded text-[10px] md:text-xs text-yellow-300">...</span>
          </button>
          <button
            onClick={() => {
              setSelectedPlatform('linux');
              setSelectedArch('x64');
            }}
            className={`flex flex-col items-center gap-1.5 md:gap-2 p-2 md:p-3 rounded-lg md:rounded-xl border transition-all relative opacity-60 cursor-not-allowed ${
              selectedPlatform === 'linux'
                ? 'bg-purple-600/30 border-purple-500 text-white'
                : 'bg-white/5 border-white/10 text-gray-300'
            }`}
            disabled
          >
            <Terminal className="w-6 h-6 md:w-8 md:h-8" />
            <span className="font-medium text-xs md:text-base">Linux</span>
            <span className="absolute top-1 right-1 md:top-2 md:right-2 px-1 md:px-1.5 py-0.5 bg-yellow-500/30 border border-yellow-500/50 rounded text-[10px] md:text-xs text-yellow-300">...</span>
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
          <div className="bg-white/5 rounded-lg md:rounded-xl p-4 md:p-6 border border-white/10 mb-4 md:mb-6">
            <div className="flex items-center justify-center gap-3 py-6 md:py-8">
              <Loader2 className="w-5 h-5 md:w-6 md:h-6 animate-spin text-purple-400" />
              <span className="text-gray-300 text-sm md:text-base">Загрузка...</span>
            </div>
          </div>
        ) : error ? (
          <div className="bg-red-900/20 border border-red-500/30 rounded-lg md:rounded-xl p-4 md:p-6 mb-4 md:mb-6">
            <p className="text-red-300 text-sm md:text-base">{error}</p>
          </div>
        ) : currentVersion ? (
          <div className="bg-white/5 rounded-lg md:rounded-xl p-4 md:p-6 border border-white/10 mb-4 md:mb-6">
            <div className="mb-3 md:mb-4">
              <h3 className="text-base md:text-lg font-semibold text-white mb-1 md:mb-2">
                FilamentHub Edition {currentVersion.version}
              </h3>
              <p className="text-gray-300 text-xs md:text-sm">
                {selectedPlatform === 'windows' && 'Windows 10/11'}
                {selectedPlatform === 'macos' && `macOS ${selectedArch === 'arm64' ? '(Apple Silicon)' : '(Intel)'}`}
                {selectedPlatform === 'linux' && 'Linux'}
                {' · '}
                {currentVersion.architecture.toUpperCase()}
                {currentVersion.file_size && ` · ${currentVersion.file_size}`}
              </p>
            </div>

            {/* Download Buttons */}
            <div className="space-y-2 md:space-y-3">
              {selectedPlatform === 'windows' && downloadsData?.versions ? (
                <>
                  {downloadsData.versions.find(
                    v => v.platform === 'windows' && 
                         v.architecture === selectedArch && 
                         v.download_type === 'installer' && 
                         v.available
                  ) && (
                    <button
                      onClick={() => handleDownload('installer')}
                      className="w-full flex items-center justify-center gap-2 md:gap-3 px-4 md:px-6 py-3 md:py-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 active:from-purple-800 active:to-pink-800 text-white font-semibold text-sm md:text-base rounded-lg md:rounded-xl transition-all shadow-lg shadow-purple-500/25"
                    >
                      <Download className="w-4 h-4 md:w-5 md:h-5" />
                      <span>Installer (.exe)</span>
                    </button>
                  )}

                  {downloadsData.versions.find(
                    v => v.platform === 'windows' && 
                         v.architecture === selectedArch && 
                         v.download_type === 'portable' && 
                         v.available
                  ) && (
                    <button
                      onClick={() => handleDownload('portable')}
                      className="w-full flex items-center justify-center gap-2 md:gap-3 px-4 md:px-6 py-3 md:py-4 bg-white/10 hover:bg-white/20 active:bg-white/25 border border-white/20 text-white font-semibold text-sm md:text-base rounded-lg md:rounded-xl transition-all"
                    >
                      <Package className="w-4 h-4 md:w-5 md:h-5" />
                      <span>Portable (ZIP)</span>
                    </button>
                  )}

                  <button
                    onClick={() => handleDownload('github')}
                    className="w-full flex items-center justify-center gap-2 md:gap-3 px-4 md:px-6 py-3 md:py-4 bg-white/10 hover:bg-white/20 active:bg-white/25 border border-white/20 text-white font-semibold text-sm md:text-base rounded-lg md:rounded-xl transition-all"
                  >
                    <Globe className="w-4 h-4 md:w-5 md:h-5" />
                    <span>GitHub</span>
                  </button>
                </>
              ) : (
                currentVersion.available && currentVersion.download_url ? (
                  <button
                    onClick={() => handleDownload()}
                    className="w-full flex items-center justify-center gap-2 md:gap-3 px-4 md:px-6 py-3 md:py-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 active:from-purple-800 active:to-pink-800 text-white font-semibold text-sm md:text-base rounded-lg md:rounded-xl transition-all shadow-lg shadow-purple-500/25"
                  >
                    <Download className="w-4 h-4 md:w-5 md:h-5" />
                    <span>Скачать</span>
                  </button>
                ) : null
              )}

              {!currentVersion.available && currentVersion.github_url && (
                <button
                  onClick={() => handleDownload('github')}
                  className="w-full flex items-center justify-center gap-2 md:gap-3 px-4 md:px-6 py-3 md:py-4 bg-white/10 hover:bg-white/20 active:bg-white/25 border border-white/20 text-white font-semibold text-sm md:text-base rounded-lg md:rounded-xl transition-all"
                >
                  <Globe className="w-4 h-4 md:w-5 md:h-5" />
                  <span>GitHub</span>
                </button>
              )}
            </div>

            {/* Информация о типах дистрибутивов */}
            {selectedPlatform === 'windows' && (
              <div className="mt-3 md:mt-4 pt-3 md:pt-4 border-t border-white/10 space-y-1.5 md:space-y-2">
                <p className="text-[10px] md:text-xs text-gray-400">
                  <strong className="text-gray-300">Installer:</strong> Установщик (.exe)
                </p>
                <p className="text-[10px] md:text-xs text-gray-400">
                  <strong className="text-gray-300">Portable:</strong> ZIP-архив без установки
                </p>
              </div>
            )}
          </div>
        ) : (
          <div className="bg-yellow-900/20 border border-yellow-500/30 rounded-xl p-6 mb-6">
            <div className="flex items-start gap-4">
              <Package className="w-6 h-6 text-yellow-400 flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="text-lg font-semibold text-yellow-300 mb-2">
                  Сборка в разработке
                </h3>
                <p className="text-gray-300 text-sm mb-2">
                  Сборка для {selectedPlatform === 'macos' ? 'macOS' : 'Linux'} ещё не готова. 
                  Для компиляции требуется соответствующая операционная система.
                </p>
                <p className="text-gray-400 text-xs">
                  Вы можете собрать версию самостоятельно из исходного кода. Инструкции будут доступны в репозитории после релиза для Windows.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Info */}
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg md:rounded-xl p-3 md:p-4">
          <div className="flex items-start gap-2 md:gap-3">
            <CheckCircle className="w-4 h-4 md:w-5 md:h-5 text-blue-400 flex-shrink-0 mt-0.5" />
            <div className="text-xs md:text-sm text-blue-300">
              <p className="font-medium mb-1">Что включено:</p>
              <ul className="list-disc list-inside space-y-0.5 md:space-y-1 text-[10px] md:text-xs">
                <li>Полная версия OrcaSlicer</li>
                <li>Вкладка FilamentHub в слайсере</li>
                <li>Каталог материалов с поиском</li>
                <li>Авто-синхронизация пресетов</li>
                <li>Импорт настроек одним кликом</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      {/* Installation Instructions - компактный вид */}
      <div className="mt-6 md:mt-12 bg-white/5 backdrop-blur-sm rounded-lg md:rounded-xl p-4 md:p-8 border border-white/10">
        <h2 className="text-base md:text-2xl font-bold text-white mb-3 md:mb-6 flex items-center gap-2">
          <Code className="w-4 h-4 md:w-6 md:h-6 text-purple-400" />
          Установка
        </h2>

        <div className="space-y-4 md:space-y-6">
          {selectedPlatform === 'windows' && (
            <div>
              <ol className="list-decimal list-inside space-y-1.5 md:space-y-2 text-gray-300 text-xs md:text-base">
                <li>Скачайте и запустите установщик</li>
                <li>Следуйте инструкциям установщика</li>
                <li>Откройте OrcaSlicer — вкладка FilamentHub появится автоматически</li>
                <li>Войдите в аккаунт через вкладку FilamentHub</li>
              </ol>
            </div>
          )}

          {selectedPlatform === 'macos' && (
            <div>
              <div className="bg-yellow-900/20 border border-yellow-500/30 rounded-lg p-3 md:p-4">
                <p className="text-yellow-300 text-xs md:text-sm">
                  Сборка для macOS в разработке.
                </p>
              </div>
            </div>
          )}

          {selectedPlatform === 'linux' && (
            <div>
              <div className="bg-yellow-900/20 border border-yellow-500/30 rounded-lg p-3 md:p-4">
                <p className="text-yellow-300 text-xs md:text-sm">
                  Сборка для Linux в разработке.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* FAQ - скрываем на мобильных для упрощения */}
      <div className="hidden md:block mt-6 md:mt-12 bg-white/5 backdrop-blur-sm rounded-lg md:rounded-xl p-4 md:p-8 border border-white/10">
        <h2 className="text-base md:text-2xl font-bold text-white mb-3 md:mb-6">FAQ</h2>
        
        <div className="space-y-4 md:space-y-6">
          <div>
            <h3 className="text-sm md:text-lg font-semibold text-white mb-1 md:mb-2">
              Чем отличается от обычной OrcaSlicer?
            </h3>
            <p className="text-gray-300 text-xs md:text-base">
              Это полная версия OrcaSlicer с дополнительной вкладкой FilamentHub. 
              Все функции сохранены — добавлен только доступ к каталогу материалов.
            </p>
          </div>

          <div>
            <h3 className="text-sm md:text-lg font-semibold text-white mb-1 md:mb-2">
              Нужен ли аккаунт?
            </h3>
            <p className="text-gray-300 text-xs md:text-base">
              Нет! Каталог доступен без регистрации. Аккаунт нужен только для синхронизации пресетов между устройствами.
            </p>
          </div>

          <div>
            <h3 className="text-sm md:text-lg font-semibold text-white mb-1 md:mb-2">
              Безопасно ли это?
            </h3>
            <p className="text-gray-300 text-xs md:text-base">
              Да! Открытый исходный код, все изменения доступны в репозитории. Интеграция через WebView, HTTPS соединение.
            </p>
          </div>

          <div>
            <h3 className="text-sm md:text-lg font-semibold text-white mb-1 md:mb-2">
              Можно ли использовать с обычной OrcaSlicer?
            </h3>
            <p className="text-gray-300 text-xs md:text-base">
              Да! Обе версии работают параллельно и не конфликтуют.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

