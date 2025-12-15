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

      {/* Screenshots Section */}
      <div className="mb-12 bg-white/5 backdrop-blur-sm rounded-2xl p-8 border border-white/10">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
          <ImageIcon className="w-6 h-6 text-purple-400" />
          Как это выглядит
        </h2>
        
        <div className="grid md:grid-cols-2 gap-6">
          {/* Screenshot 1: FilamentHub Tab */}
          <div className="bg-white/5 rounded-xl p-4 border border-white/10">
            <div className="aspect-video bg-gradient-to-br from-gray-800 to-gray-900 rounded-lg flex items-center justify-center border-2 border-dashed border-white/20 mb-4">
              <div className="text-center">
                <ImageIcon className="w-12 h-12 text-gray-500 mx-auto mb-2" />
                <p className="text-sm text-gray-500">Скриншот: Вкладка FilamentHub в OrcaSlicer</p>
                <p className="text-xs text-gray-600 mt-1">(Будет добавлено)</p>
              </div>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Вкладка FilamentHub</h3>
            <p className="text-gray-300 text-sm">
              Новая вкладка прямо в главном окне OrcaSlicer — каталог материалов, поиск настроек и синхронизация пресетов без переключения между приложениями.
            </p>
          </div>

          {/* Screenshot 2: Catalog in OrcaSlicer */}
          <div className="bg-white/5 rounded-xl p-4 border border-white/10">
            <div className="aspect-video bg-gradient-to-br from-gray-800 to-gray-900 rounded-lg flex items-center justify-center border-2 border-dashed border-white/20 mb-4">
              <div className="text-center">
                <ImageIcon className="w-12 h-12 text-gray-500 mx-auto mb-2" />
                <p className="text-sm text-gray-500">Скриншот: Каталог материалов внутри OrcaSlicer</p>
                <p className="text-xs text-gray-600 mt-1">(Будет добавлено)</p>
              </div>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Каталог материалов</h3>
            <p className="text-gray-300 text-sm">
              Полноценный каталог материалов FilamentHub прямо в слайсере — просматривайте настройки, фильтруйте по принтерам и сразу импортируйте пресеты.
            </p>
          </div>

          {/* Screenshot 3: Sync Feature */}
          <div className="bg-white/5 rounded-xl p-4 border border-white/10">
            <div className="aspect-video bg-gradient-to-br from-gray-800 to-gray-900 rounded-lg flex items-center justify-center border-2 border-dashed border-white/20 mb-4">
              <div className="text-center">
                <ImageIcon className="w-12 h-12 text-gray-500 mx-auto mb-2" />
                <p className="text-sm text-gray-500">Скриншот: Синхронизация пресетов</p>
                <p className="text-xs text-gray-600 mt-1">(Будет добавлено)</p>
              </div>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Синхронизация пресетов</h3>
            <p className="text-gray-300 text-sm">
              Автоматическая синхронизация ваших пресетов между FilamentHub и OrcaSlicer — работайте на любом устройстве, настройки всегда актуальны.
            </p>
          </div>

          {/* Screenshot 4: Import Preset */}
          <div className="bg-white/5 rounded-xl p-4 border border-white/10">
            <div className="aspect-video bg-gradient-to-br from-gray-800 to-gray-900 rounded-lg flex items-center justify-center border-2 border-dashed border-white/20 mb-4">
              <div className="text-center">
                <ImageIcon className="w-12 h-12 text-gray-500 mx-auto mb-2" />
                <p className="text-sm text-gray-500">Скриншот: Импорт пресета одним кликом</p>
                <p className="text-xs text-gray-600 mt-1">(Будет добавлено)</p>
              </div>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Импорт одним кликом</h3>
            <p className="text-gray-300 text-sm">
              Нашли нужные настройки? Импортируйте пресет прямо в OrcaSlicer одним кликом — без ручного копирования файлов и поиска папок.
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
                <h3 className="text-lg font-semibold text-white mb-1">Видео-обзор FilamentHub Edition</h3>
                <p className="text-sm text-gray-300">Посмотрите как работает интеграция FilamentHub в OrcaSlicer</p>
              </div>
            </div>
            <div className="aspect-video w-48 bg-gradient-to-br from-gray-800 to-gray-900 rounded-lg flex items-center justify-center border-2 border-dashed border-white/20">
              <div className="text-center">
                <ImageIcon className="w-8 h-8 text-gray-500 mx-auto mb-1" />
                <p className="text-xs text-gray-500">Видео</p>
                <p className="text-xs text-gray-600">(Будет добавлено)</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Key Benefits */}
      <div className="bg-gradient-to-br from-purple-900/50 to-indigo-900/50 backdrop-blur-sm rounded-2xl p-8 border border-white/20 shadow-xl mb-12">
        <h2 className="text-2xl font-bold text-white mb-6 text-center">Почему FilamentHub Edition?</h2>
        
        <div className="grid md:grid-cols-2 gap-6">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 bg-yellow-500/20 rounded-xl flex items-center justify-center flex-shrink-0">
              <Zap className="w-6 h-6 text-yellow-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-2">Всё в одном месте</h3>
              <p className="text-gray-300 text-sm">
                Не нужно открывать браузер, искать настройки и вручную копировать файлы. Каталог материалов, поиск и импорт — прямо в OrcaSlicer.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4">
            <div className="w-12 h-12 bg-purple-500/20 rounded-xl flex items-center justify-center flex-shrink-0">
              <Package className="w-6 h-6 text-purple-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-2">Автоматическая синхронизация</h3>
              <p className="text-gray-300 text-sm">
                Ваши пресеты синхронизируются между FilamentHub и OrcaSlicer автоматически. Работайте на разных компьютерах — настройки всегда актуальны.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4">
            <div className="w-12 h-12 bg-blue-500/20 rounded-xl flex items-center justify-center flex-shrink-0">
              <Globe className="w-6 h-6 text-blue-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-2">Библиотека настроек</h3>
              <p className="text-gray-300 text-sm">
                Доступ к тысячам проверенных настроек от сообщества и производителей. Фильтрация по принтеру, материалу и рейтингу — найдите идеальные параметры.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4">
            <div className="w-12 h-12 bg-green-500/20 rounded-xl flex items-center justify-center flex-shrink-0">
              <CheckCircle className="w-6 h-6 text-green-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-2">Проверенные настройки</h3>
              <p className="text-gray-300 text-sm">
                Используйте настройки с высоким рейтингом и процентом успеха от других пользователей. Экономьте время на калибровке — печатайте качественно сразу.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4">
            <div className="w-12 h-12 bg-pink-500/20 rounded-xl flex items-center justify-center flex-shrink-0">
              <Code className="w-6 h-6 text-pink-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-2">100% функционал OrcaSlicer</h3>
              <p className="text-gray-300 text-sm">
                Это полная версия OrcaSlicer со всеми функциями. Мы только добавили интеграцию с FilamentHub — ничего не убрали и не изменили в слайсере.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4">
            <div className="w-12 h-12 bg-indigo-500/20 rounded-xl flex items-center justify-center flex-shrink-0">
              <Download className="w-6 h-6 text-indigo-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-2">Бесплатно и открыто</h3>
              <p className="text-gray-300 text-sm">
                FilamentHub Edition полностью бесплатна и основана на открытом исходном коде. Все изменения доступны в нашем репозитории — прозрачно и безопасно.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Download Section */}
      <div className="bg-gradient-to-br from-purple-900/50 to-indigo-900/50 backdrop-blur-sm rounded-2xl p-8 border border-white/20 shadow-xl">
        <h2 className="text-2xl font-bold text-white mb-6">Выберите платформу</h2>

        {/* Platform Selection */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <button
            onClick={() => {
              setSelectedPlatform('windows');
              setSelectedArch('x64');
            }}
            className={`flex flex-col items-center gap-2 p-3 rounded-xl border transition-all relative ${
              selectedPlatform === 'windows'
                ? 'bg-purple-600/30 border-purple-500 text-white'
                : 'bg-white/5 border-white/10 text-gray-300 hover:bg-white/10'
            }`}
          >
            <Monitor className="w-8 h-8" />
            <span className="font-medium">Windows</span>
            <span className="absolute top-2 right-2 px-1.5 py-0.5 bg-green-500/30 border border-green-500/50 rounded text-xs text-green-300">Доступно</span>
          </button>
          <button
            onClick={() => {
              setSelectedPlatform('macos');
              setSelectedArch('x64');
            }}
            className={`flex flex-col items-center gap-2 p-3 rounded-xl border transition-all relative opacity-60 cursor-not-allowed ${
              selectedPlatform === 'macos'
                ? 'bg-purple-600/30 border-purple-500 text-white'
                : 'bg-white/5 border-white/10 text-gray-300'
            }`}
            disabled
            title="Сборка для macOS в разработке"
          >
            <Smartphone className="w-8 h-8" />
            <span className="font-medium">macOS</span>
            <span className="absolute top-2 right-2 px-1.5 py-0.5 bg-yellow-500/30 border border-yellow-500/50 rounded text-xs text-yellow-300">Скоро</span>
          </button>
          <button
            onClick={() => {
              setSelectedPlatform('linux');
              setSelectedArch('x64');
            }}
            className={`flex flex-col items-center gap-2 p-3 rounded-xl border transition-all relative opacity-60 cursor-not-allowed ${
              selectedPlatform === 'linux'
                ? 'bg-purple-600/30 border-purple-500 text-white'
                : 'bg-white/5 border-white/10 text-gray-300'
            }`}
            disabled
            title="Сборка для Linux в разработке"
          >
            <Terminal className="w-8 h-8" />
            <span className="font-medium">Linux</span>
            <span className="absolute top-2 right-2 px-1.5 py-0.5 bg-yellow-500/30 border border-yellow-500/50 rounded text-xs text-yellow-300">Скоро</span>
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
              <span className="text-gray-300">Загрузка информации о сборках...</span>
            </div>
          </div>
        ) : error ? (
          <div className="bg-red-900/20 border border-red-500/30 rounded-xl p-6 mb-6">
            <p className="text-red-300">{error}</p>
          </div>
        ) : currentVersion ? (
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
                  Размер: {currentVersion.file_size || 'N/A'}
                </p>
              </div>
            </div>

            {/* Download Buttons */}
            <div className="space-y-3">
              {/* Для Windows показываем оба варианта */}
              {selectedPlatform === 'windows' && downloadsData?.versions ? (
                <>
                  {/* Установщик */}
                  {downloadsData.versions.find(
                    v => v.platform === 'windows' && 
                         v.architecture === selectedArch && 
                         v.download_type === 'installer' && 
                         v.available
                  ) && (
                    <button
                      onClick={() => handleDownload('installer')}
                      className="w-full flex items-center justify-center gap-3 px-6 py-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white font-semibold rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-xl hover:shadow-purple-500/30"
                    >
                      <Download className="w-5 h-5" />
                      <span>Скачать Installer (.exe)</span>
                    </button>
                  )}

                  {/* Portable версия */}
                  {downloadsData.versions.find(
                    v => v.platform === 'windows' && 
                         v.architecture === selectedArch && 
                         v.download_type === 'portable' && 
                         v.available
                  ) && (
                    <button
                      onClick={() => handleDownload('portable')}
                      className="w-full flex items-center justify-center gap-3 px-6 py-4 bg-white/10 hover:bg-white/20 border border-white/20 text-white font-semibold rounded-xl transition-all"
                    >
                      <Package className="w-5 h-5" />
                      <span>Скачать Portable (ZIP)</span>
                    </button>
                  )}

                  {/* GitHub ссылка */}
                  <button
                    onClick={() => handleDownload('github')}
                    className="w-full flex items-center justify-center gap-3 px-6 py-4 bg-white/10 hover:bg-white/20 border border-white/20 text-white font-semibold rounded-xl transition-all"
                  >
                    <Globe className="w-5 h-5" />
                    <span>Скачать с GitHub Releases</span>
                  </button>
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
                      Скачать {currentVersion.download_type === 'portable' ? 'Portable' : 'Installer'} 
                      {currentVersion.download_type === 'portable' && ' (ZIP)'}
                    </span>
                  </button>
                ) : null
              )}

              {/* Если нет доступных версий, показываем GitHub */}
              {!currentVersion.available && currentVersion.github_url && (
                <button
                  onClick={() => handleDownload('github')}
                  className="w-full flex items-center justify-center gap-3 px-6 py-4 bg-white/10 hover:bg-white/20 border border-white/20 text-white font-semibold rounded-xl transition-all"
                >
                  <Globe className="w-5 h-5" />
                  <span>Скачать с GitHub Releases</span>
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
                  <strong className="text-gray-300">Installer:</strong> Установщик для Windows (.exe)
                </p>
                <p className="text-xs text-gray-400 mb-3">
                  <strong className="text-gray-300">Portable:</strong> Портативная версия в ZIP архиве — не требует установки
                </p>
                {/* GitHub ссылка */}
                <a
                  href="https://github.com/lizardjazz1/OrcaSlicer/releases"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-center gap-2 text-gray-300 hover:text-white transition-colors text-sm pt-2 border-t border-white/5"
                >
                  <Globe className="w-4 h-4" />
                  <span>Также доступно на GitHub Releases</span>
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
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <CheckCircle className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-blue-300">
              <p className="font-medium mb-1">Что включено в FilamentHub Edition:</p>
              <ul className="list-disc list-inside space-y-1 text-xs">
                <li>Полная версия OrcaSlicer со всеми функциями — ничего не урезано</li>
                <li>Новая вкладка "FilamentHub" в главном окне слайсера</li>
                <li>Встроенный каталог материалов с поиском и фильтрами</li>
                <li>Автоматическая синхронизация пресетов между FilamentHub и OrcaSlicer</li>
                <li>Импорт настроек одним кликом прямо из каталога</li>
                <li>Управление пресетами из слайсера — создание, редактирование, экспорт</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      {/* Installation Instructions */}
      <div className="mt-12 bg-white/5 backdrop-blur-sm rounded-xl p-8 border border-white/10">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
          <Code className="w-6 h-6 text-purple-400" />
          Инструкции по установке
        </h2>

        <div className="space-y-6">
          {selectedPlatform === 'windows' && (
            <div>
              <h3 className="text-lg font-semibold text-white mb-3">Windows</h3>
              <ol className="list-decimal list-inside space-y-2 text-gray-300">
                <li>Скачайте установщик (.exe файл)</li>
                <li>Запустите установщик и следуйте инструкциям</li>
                <li>После установки откройте OrcaSlicer — вкладка FilamentHub будет доступна в главном окне</li>
                <li>Войдите в свой аккаунт FilamentHub через вкладку FilamentHub</li>
              </ol>
            </div>
          )}

          {selectedPlatform === 'macos' && (
            <div>
              <h3 className="text-lg font-semibold text-white mb-3">macOS (в разработке)</h3>
              <div className="bg-yellow-900/20 border border-yellow-500/30 rounded-lg p-4 mb-3">
                <p className="text-yellow-300 text-sm">
                  Сборка для macOS в разработке. Для компиляции требуется macOS с Xcode.
                </p>
              </div>
              <p className="text-gray-400 text-sm mb-3">
                После релиза инструкции будут такими:
              </p>
              <ol className="list-decimal list-inside space-y-2 text-gray-300 opacity-60">
                <li>Скачайте .dmg файл</li>
                <li>Откройте .dmg файл и перетащите OrcaSlicer в папку Applications</li>
                <li>При первом запуске macOS может запросить разрешение — нажмите "Открыть" в настройках безопасности</li>
                <li>Откройте OrcaSlicer — вкладка FilamentHub будет доступна в главном окне</li>
                <li>Войдите в свой аккаунт FilamentHub через вкладку FilamentHub</li>
              </ol>
            </div>
          )}

          {selectedPlatform === 'linux' && (
            <div>
              <h3 className="text-lg font-semibold text-white mb-3">Linux (в разработке)</h3>
              <div className="bg-yellow-900/20 border border-yellow-500/30 rounded-lg p-4 mb-3">
                <p className="text-yellow-300 text-sm">
                  Сборка для Linux в разработке. Для компиляции требуется Linux система с установленными зависимостями.
                </p>
              </div>
              <p className="text-gray-400 text-sm mb-3">
                После релиза инструкции будут такими:
              </p>
              <ol className="list-decimal list-inside space-y-2 text-gray-300 opacity-60">
                <li>Скачайте .AppImage файл</li>
                <li>Сделайте файл исполняемым: <code className="bg-white/10 px-2 py-1 rounded text-purple-300">chmod +x OrcaSlicer*.AppImage</code></li>
                <li>Запустите файл: <code className="bg-white/10 px-2 py-1 rounded text-purple-300">./OrcaSlicer*.AppImage</code></li>
                <li>Откройте OrcaSlicer — вкладка FilamentHub будет доступна в главном окне</li>
                <li>Войдите в свой аккаунт FilamentHub через вкладку FilamentHub</li>
              </ol>
            </div>
          )}
        </div>
      </div>

      {/* FAQ */}
      <div className="mt-12 bg-white/5 backdrop-blur-sm rounded-xl p-8 border border-white/10">
        <h2 className="text-2xl font-bold text-white mb-6">Часто задаваемые вопросы</h2>
        
        <div className="space-y-6">
          <div>
            <h3 className="text-lg font-semibold text-white mb-2">
              Чем отличается FilamentHub Edition от обычной OrcaSlicer?
            </h3>
            <p className="text-gray-300 mb-2">
              FilamentHub Edition — это <strong className="text-white">полная версия OrcaSlicer</strong> с дополнительной вкладкой FilamentHub. 
              Все функции оригинального слайсера сохранены без изменений — мы только добавили удобный доступ к каталогу материалов прямо в интерфейсе.
            </p>
            <p className="text-gray-300">
              <strong className="text-white">Преимущества:</strong> Не нужно переключаться между браузером и слайсером, 
              все настройки доступны в одном окне. Автоматическая синхронизация пресетов экономит время, а доступ к библиотеке 
              проверенных настроек помогает печатать качественнее с первого раза.
            </p>
          </div>

          <div>
            <h3 className="text-lg font-semibold text-white mb-2">
              Нужен ли аккаунт FilamentHub для использования?
            </h3>
            <p className="text-gray-300">
              <strong className="text-white">Нет, не обязателен!</strong> Вы можете просматривать каталог материалов и импортировать 
              настройки без регистрации. Аккаунт нужен только если вы хотите синхронизировать свои пресеты между устройствами, 
              сохранять избранные материалы и делиться своими настройками с сообществом. Регистрация бесплатна и займёт меньше минуты.
            </p>
          </div>

          <div>
            <h3 className="text-lg font-semibold text-white mb-2">
              Можно ли обновлять FilamentHub Edition отдельно?
            </h3>
            <p className="text-gray-300">
              Да! FilamentHub Edition обновляется независимо и включает все обновления оригинального OrcaSlicer плюс улучшения интеграции. 
              Мы следим за новыми версиями OrcaSlicer и регулярно выпускаем обновления FilamentHub Edition. 
              Уведомления о новых версиях появляются прямо в слайсере.
            </p>
          </div>

          <div>
            <h3 className="text-lg font-semibold text-white mb-2">
              Безопасно ли это?
            </h3>
            <p className="text-gray-300 mb-2">
              <strong className="text-white">Абсолютно безопасно!</strong> FilamentHub Edition основана на открытом исходном коде OrcaSlicer. 
              Все наши изменения доступны в открытом репозитории — вы можете проверить каждый строку кода.
            </p>
            <p className="text-gray-300">
              Мы добавляем только безопасную интеграцию через WebView — никаких изменений в ядре слайсера, 
              никаких внешних зависимостей, никаких сомнительных модификаций. Все коммуникации с FilamentHub идут через HTTPS, 
              токены хранятся локально в зашифрованном виде.
            </p>
          </div>

          <div>
            <h3 className="text-lg font-semibold text-white mb-2">
              Что делать если у меня уже установлена обычная OrcaSlicer?
            </h3>
            <p className="text-gray-300">
              FilamentHub Edition может быть установлена параллельно с обычной OrcaSlicer — они не конфликтуют. 
              Все ваши пресеты и настройки OrcaSlicer останутся на месте. FilamentHub Edition просто добавит вкладку 
              с каталогом материалов, не затрагивая существующую конфигурацию. Вы можете использовать обе версии одновременно!
            </p>
          </div>

          <div>
            <h3 className="text-lg font-semibold text-white mb-2">
              Работает ли это на всех платформах?
            </h3>
            <p className="text-gray-300 mb-2">
              FilamentHub Edition будет доступна для <strong className="text-white">Windows</strong> (10/11), 
              <strong className="text-white"> macOS</strong> (Intel и Apple Silicon) и <strong className="text-white">Linux</strong> (x64). 
            </p>
            <p className="text-gray-300">
              <strong className="text-white">Статус сборок:</strong> Сейчас доступна сборка для Windows. 
              Сборки для macOS и Linux появятся позже (для сборки требуются соответствующие системы и настройка CI/CD). 
              Вы также можете собрать версию для своей платформы самостоятельно из исходного кода — инструкции будут в репозитории.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
