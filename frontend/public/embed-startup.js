/* Keep this classic script independent of the application bundle and its syntax.
 * The static panel also stays readable if this file itself cannot be loaded. */
(function () {
  'use strict';

  var panel = document.getElementById('fh-startup');
  if (!panel) return;
  var path = window.location.pathname;
  if (!/^\/(?:(?:en|ru|zh)\/)?embed(?:\/|$)/i.test(path)) {
    panel.hidden = true;
    return;
  }

  var translations = {
    en: {
      loading: 'Opening FilamentHub…',
      waiting: 'The catalog is loading.',
      failed: 'FilamentHub could not start',
      resource: 'Some files needed by the catalog could not be loaded.',
      runtime: 'The embedded page stopped before it was ready.',
      initialization: 'The catalog could not finish starting.',
      timeout: 'The catalog is taking longer than expected to start.',
      help: 'Reload this tab. If the problem continues, try the other server in the FilamentHub plugin settings and restart OrcaSlicer. Include the code below and your exact OrcaSlicer build when reporting the problem.',
      retry: 'Reload',
      code: 'Diagnostic code',
    },
    ru: {
      loading: 'Открываем FilamentHub…',
      waiting: 'Загружается каталог.',
      failed: 'Не удалось запустить FilamentHub',
      resource: 'Не удалось загрузить некоторые файлы каталога.',
      runtime: 'Встроенная страница остановилась до завершения загрузки.',
      initialization: 'Не удалось завершить запуск каталога.',
      timeout: 'Запуск каталога занимает больше времени, чем ожидалось.',
      help: 'Перезагрузите вкладку. Если проблема повторится, выберите другой сервер в настройках плагина FilamentHub и перезапустите OrcaSlicer. При обращении в поддержку укажите код ниже и точную сборку OrcaSlicer.',
      retry: 'Перезагрузить',
      code: 'Код диагностики',
    },
    zh: {
      loading: '正在打开 FilamentHub…',
      waiting: '正在加载目录。',
      failed: 'FilamentHub 无法启动',
      resource: '无法加载目录所需的部分文件。',
      runtime: '嵌入页面在准备就绪前停止运行。',
      initialization: '目录未能完成启动。',
      timeout: '目录启动时间比预期更长。',
      help: '请重新加载此标签页。如果问题仍然存在，请在 FilamentHub 插件设置中选择另一个服务器，然后重启 OrcaSlicer。报告问题时请附上下方代码和准确的 OrcaSlicer 构建版本。',
      retry: '重新加载',
      code: '诊断代码',
    },
  };
  var pathLocale = path.match(/^\/(en|ru|zh)(?:\/|$)/i);
  var queryLocale = window.location.search.match(/(?:^|[?&])lng=([^&]*)/i);
  var locale = pathLocale ? pathLocale[1] : document.documentElement.lang;
  if (!pathLocale && queryLocale) {
    try {
      locale = decodeURIComponent(queryLocale[1]);
    } catch (_) {
      // A malformed language hint must never break the recovery screen.
    }
  }
  locale = String(locale || 'en').toLowerCase().split(/[-_]/)[0];
  var copy = translations[locale] || translations.en;
  var title = document.getElementById('fh-startup-title');
  var message = document.getElementById('fh-startup-message');
  var help = document.getElementById('fh-startup-help');
  var diagnostic = document.getElementById('fh-startup-code');
  var retry = document.getElementById('fh-startup-retry');
  var finished = false;
  var failed = false;
  var timer;

  title.textContent = copy.loading;
  message.textContent = copy.waiting;
  help.textContent = copy.help;
  help.hidden = true;
  retry.textContent = copy.retry;
  panel.hidden = false;
  panel.setAttribute('data-state', 'loading');

  function fail(kind) {
    if (finished || failed) return;
    failed = true;
    window.clearTimeout(timer);
    panel.setAttribute('data-state', 'error');
    panel.setAttribute('role', 'alert');
    title.textContent = copy.failed;
    message.textContent = copy[kind];
    help.hidden = false;
    retry.hidden = false;
    // Only a fixed code is displayed. Error messages, resource URLs and the
    // page's fragment can contain session bindings or other private data.
    diagnostic.textContent = copy.code + ': FH-STARTUP-' + kind.toUpperCase();
    diagnostic.hidden = false;
  }

  function appAsset(rawUrl) {
    if (!rawUrl) return false;
    var url = document.createElement('a');
    url.href = rawUrl;
    return url.protocol === window.location.protocol
      && url.host === window.location.host
      && (/^\/assets\/.*\.(?:m?js|css)$/.test(url.pathname)
        || /^\/src\/.*\.(?:[jt]sx?|css)$/.test(url.pathname));
  }

  function onError(event) {
    var target = event.target;
    if (target && (target.tagName === 'SCRIPT' || target.tagName === 'LINK')) {
      // Images, optional third-party widgets and the prerender helper are not
      // prerequisites for a usable catalog.
      if ((target.tagName === 'SCRIPT' && appAsset(target.src))
        || (target.tagName === 'LINK' && appAsset(target.href))) {
        fail('resource');
      }
    } else if (appAsset(event.filename)) {
      fail('runtime');
    }
  }

  function onRejection() { fail('runtime'); }
  function onPreloadError() { fail('resource'); }
  function onInitializationError() { fail('initialization'); }
  function reload() {
    // Reload the exact URL: constructing a new one would lose fh_bridge.
    window.location.reload();
  }

  function complete() {
    if (finished) return;
    finished = true;
    window.clearTimeout(timer);
    window.removeEventListener('error', onError, true);
    window.removeEventListener('unhandledrejection', onRejection);
    window.removeEventListener('vite:preloadError', onPreloadError);
    window.removeEventListener('fh:startup-failed', onInitializationError);
    window.removeEventListener('fh:startup-ready', complete);
    retry.removeEventListener('click', reload);
    if (panel.parentNode) panel.parentNode.removeChild(panel);
  }

  window.addEventListener('error', onError, true);
  window.addEventListener('unhandledrejection', onRejection);
  window.addEventListener('vite:preloadError', onPreloadError);
  window.addEventListener('fh:startup-failed', onInitializationError);
  window.addEventListener('fh:startup-ready', complete);
  retry.addEventListener('click', reload);
  timer = window.setTimeout(function () { fail('timeout'); }, 20000);
})();
