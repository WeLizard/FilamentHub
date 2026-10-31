import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ErrorBoundary } from './ErrorBoundary';
import { StartupReady, reportStartupFailure } from './StartupReady';
import html from '../../index.html?raw';
import watchdog from '../../public/embed-startup.js?raw';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const markup = html.match(/<body>([\s\S]*)<\/body>/)?.[1] ?? '';
const startWatchdog = (host: Window = window) => new Function('window', 'document', watchdog)(host, document);
const startup = () => document.getElementById('fh-startup');
const code = () => document.getElementById('fh-startup-code');

function scriptError(src: string) {
  const script = document.createElement('script');
  script.src = src;
  document.head.appendChild(script);
  script.dispatchEvent(new Event('error'));
  script.remove();
}

describe('independent embed startup recovery', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    window.history.replaceState({}, '', '/embed/catalog?lng=en#fh_bridge=private-binding');
    document.documentElement.lang = 'en';
    document.body.innerHTML = markup;
  });

  afterEach(() => {
    window.dispatchEvent(new Event('fh:startup-ready'));
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
    document.body.innerHTML = '';
    window.history.replaceState({}, '', '/');
  });

  it('keeps the static panel hidden until the embed watchdog shows it', () => {
    expect(startup()).toHaveAttribute('hidden');
    startWatchdog();
    expect(startup()).not.toHaveAttribute('hidden');
    expect(document.getElementById('root')).toBeEmptyDOMElement();
  });

  it('uses external classic scripts compatible with the existing CSP', () => {
    const parsed = new DOMParser().parseFromString(html, 'text/html');
    const recoveryScript = parsed.querySelector('script[src="/embed-startup.js"]');
    expect(recoveryScript).toBeTruthy();
    expect(recoveryScript?.hasAttribute('type')).toBe(false);
    expect(recoveryScript?.hasAttribute('async')).toBe(false);
    expect(recoveryScript?.hasAttribute('defer')).toBe(false);
    expect(parsed.querySelector('link[rel="stylesheet"][href="/embed-startup.css"]')).toBeTruthy();
    expect(parsed.getElementById('fh-startup')?.contains(parsed.getElementById('root'))).toBe(false);
    expect([...parsed.scripts].filter((script) => !script.src && script.type !== 'application/ld+json'))
      .toHaveLength(0);
    expect(parsed.querySelector('[onclick], [onload], [onerror]')).toBeNull();
  });

  it('hides the fallback and does not monitor ordinary website routes', () => {
    window.history.replaceState({}, '', '/ru/profile');
    startWatchdog();
    expect(startup()).toHaveAttribute('hidden');
    expect(vi.getTimerCount()).toBe(0);
    scriptError('/assets/app.js');
    expect(code()).toBeEmptyDOMElement();
  });

  it('reports a failed application module without displaying its URL or session data', () => {
    startWatchdog();
    scriptError('/assets/app.js?token=private-token#fh_bridge=private-binding');
    expect(startup()).toHaveAttribute('role', 'alert');
    expect(code()).toHaveTextContent('FH-STARTUP-RESOURCE');
    expect(startup()).not.toHaveTextContent('private');
    expect(startup()).not.toHaveTextContent('/assets/');
    expect(screen.getByRole('button', { name: 'Reload' })).toBeVisible();
    expect(window.location.hash).toBe('#fh_bridge=private-binding');
  });

  it('ignores failed optional widgets and images before the app is ready', () => {
    startWatchdog();
    scriptError('https://www.google.com/recaptcha/api.js');
    scriptError('/rotor-settings.js');
    const image = document.createElement('img');
    image.src = '/assets/missing.png';
    document.body.appendChild(image);
    image.dispatchEvent(new Event('error'));
    expect(startup()).toHaveAttribute('data-state', 'loading');
    expect(code()).toBeEmptyDOMElement();
  });

  it('reloads the existing page without reconstructing or dropping its bridge binding', () => {
    const reload = vi.fn();
    const location = {
      pathname: window.location.pathname,
      search: window.location.search,
      hash: window.location.hash,
      protocol: window.location.protocol,
      host: window.location.host,
      reload,
    };
    const host = {
      location,
      addEventListener: window.addEventListener.bind(window),
      removeEventListener: window.removeEventListener.bind(window),
      setTimeout: window.setTimeout.bind(window),
      clearTimeout: window.clearTimeout.bind(window),
    } as unknown as Window;
    startWatchdog(host);
    reportStartupFailure();
    screen.getByRole('button', { name: 'Reload' }).click();
    expect(reload).toHaveBeenCalledOnce();
    expect(location.search).toBe('?lng=en');
    expect(location.hash).toBe('#fh_bridge=private-binding');
  });

  it('reports a pre-mount runtime failure without showing the exception contents', () => {
    startWatchdog();
    window.dispatchEvent(new ErrorEvent('error', {
      filename: window.location.origin + '/assets/app.js',
      message: 'failure containing private-token',
      error: new Error('private-token'),
    }));
    expect(code()).toHaveTextContent('FH-STARTUP-RUNTIME');
    expect(startup()).not.toHaveTextContent('private-token');
  });

  it.each([
    ['unhandledrejection', 'RUNTIME'],
    ['vite:preloadError', 'RESOURCE'],
  ])('reports %s while the app has not mounted', (eventName, expected) => {
    startWatchdog();
    window.dispatchEvent(new Event(eventName));
    expect(code()).toHaveTextContent('FH-STARTUP-' + expected);
  });

  it('reports a caught initialization failure and keeps the first useful code', () => {
    startWatchdog();
    reportStartupFailure();
    window.dispatchEvent(new Event('unhandledrejection'));
    vi.advanceTimersByTime(30000);
    expect(code()).toHaveTextContent('FH-STARTUP-INITIALIZATION');
  });

  it('shows a bounded timeout but recovers when React finally commits', () => {
    startWatchdog();
    vi.advanceTimersByTime(19999);
    expect(startup()).toHaveAttribute('data-state', 'loading');
    vi.advanceTimersByTime(1);
    expect(code()).toHaveTextContent('FH-STARTUP-TIMEOUT');
    render(<StartupReady><p>Catalog is ready</p></StartupReady>);
    expect(screen.getByText('Catalog is ready')).toBeVisible();
    expect(startup()).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('signals success only after a real React commit and detaches startup listeners', () => {
    startWatchdog();
    const committed = vi.fn(() => expect(screen.getByText('Ready screen')).toBeInTheDocument());
    window.addEventListener('fh:startup-ready', committed, { once: true });
    const element = <StartupReady><p>Ready screen</p></StartupReady>;
    expect(committed).not.toHaveBeenCalled();
    render(element);
    expect(committed).toHaveBeenCalledOnce();
    expect(startup()).toBeNull();
    act(() => {
      window.dispatchEvent(new Event('vite:preloadError'));
      window.dispatchEvent(new Event('unhandledrejection'));
      reportStartupFailure();
      vi.advanceTimersByTime(30000);
    });
    expect(startup()).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('also removes the static panel when the watchdog never loaded', () => {
    render(<StartupReady><p>Ready without watchdog</p></StartupReady>);
    expect(startup()).toBeNull();
    expect(screen.getByText('Ready without watchdog')).toBeVisible();
  });

  it('does not cover the React error boundary fallback after it commits', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    function BrokenChild(): never { throw new Error('broken child'); }
    startWatchdog();
    render(
      <StartupReady>
        <ErrorBoundary><BrokenChild /></ErrorBoundary>
      </StartupReady>,
    );
    expect(startup()).toBeNull();
    expect(screen.getByRole('heading', { name: 'errorBoundary.title' })).toBeVisible();
  });

  it.each([
    ['/embed/catalog?lng=ru_RU', 'Открываем FilamentHub…'],
    ['/zh/embed/catalog?lng=ru', '正在打开 FilamentHub…'],
    ['/embed/catalog?lng=zh-CN', '正在打开 FilamentHub…'],
    ['/embed/catalog?lng=%invalid', 'Opening FilamentHub…'],
  ])('localizes %s without needing the app translation chunks', (url, heading) => {
    window.history.replaceState({}, '', url);
    startWatchdog();
    expect(screen.getByRole('heading', { name: heading })).toBeVisible();
  });
});
