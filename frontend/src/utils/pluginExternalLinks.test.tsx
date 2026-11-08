import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

const bridgeSession = 'test-bridge-session-1234567890';
const externalUrl = 'https://example.org/docs?lang=en#page';

beforeEach(() => vi.resetModules());
afterEach(() => {
  cleanup();
  document.body.replaceChildren();
  document.documentElement.removeAttribute('data-fh-plugin-appearance');
  sessionStorage.clear();
  window.history.replaceState({}, '', '/');
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function setupDirectHost(capabilities?: string[]) {
  const bridge = await import('./pluginBridge');
  const postMessage = vi.fn();
  let deliver: ((message: unknown) => void) | undefined;
  vi.stubGlobal('orca', {
    postMessage,
    onMessage: (handler: (message: unknown) => void) => { deliver = handler; },
  });
  window.history.replaceState({}, '', `/embed/catalog#fh_bridge=${bridgeSession}`);
  const unsubscribe = bridge.subscribeToPluginCapabilities(vi.fn());
  bridge.requestPluginCapabilities();
  if (capabilities) {
    deliver?.({ source: 'filamenthub-host', type: 'plugin-capabilities', capabilities });
  }
  postMessage.mockClear();
  return { bridge, postMessage, deliver, unsubscribe };
}

function clickLink(href: string, {
  target = '', eventType = 'click', download = false, claimed = false, ...options
}: MouseEventInit & { target?: string; eventType?: string; download?: boolean; claimed?: boolean } = {}): boolean {
  const anchor = document.createElement('a');
  anchor.href = href;
  anchor.target = target;
  if (download) anchor.download = 'manual.pdf';
  if (claimed) anchor.addEventListener(eventType, (event) => event.preventDefault());
  const label = document.createElement('span');
  anchor.append(label);
  document.body.append(anchor);

  const event = new MouseEvent(eventType, { bubbles: true, cancelable: true, ...options });
  let prevented = false;
  // Observe the outcome after the document listener and skip jsdom navigation.
  window.addEventListener(eventType, (received) => {
    prevented = received.defaultPrevented;
    received.preventDefault();
  }, { once: true });
  label.dispatchEvent(event);
  anchor.remove();
  return prevented;
}

describe('external links in the direct Orca Pages bridge', () => {
  it('opens plain, blank-target, modified and middle clicks once without navigating the panel', async () => {
    const { bridge, postMessage, unsubscribe } = await setupDirectHost(['open-external-url']);
    const stopLinks = bridge.subscribeToPluginExternalLinks(vi.fn());
    const currentPage = window.location.href;
    try {
      for (const gesture of [
        {}, { target: '_blank' }, { ctrlKey: true }, { metaKey: true },
        { eventType: 'auxclick', button: 1 },
      ]) {
        postMessage.mockClear();
        expect(clickLink(externalUrl, gesture)).toBe(true);
        expect(postMessage).toHaveBeenCalledExactlyOnceWith({
          source: bridge.PLUGIN_MESSAGE_SOURCE,
          type: 'open-external-url',
          url: externalUrl,
          bridgeSession,
        });
        expect(window.location.href).toBe(currentPage);
      }
      postMessage.mockClear();
      expect(clickLink('https://example.org/manual.pdf')).toBe(true);
      expect(postMessage).toHaveBeenCalledTimes(1);
    } finally {
      stopLinks();
      unsubscribe();
    }
  });

  it('leaves app routes, anchors, downloads, other schemes and already handled clicks alone', async () => {
    const { bridge, postMessage, unsubscribe } = await setupDirectHost(['open-external-url']);
    const stopLinks = bridge.subscribeToPluginExternalLinks(vi.fn());
    try {
      for (const href of ['/catalog', '#help', 'blob:https://example.org/file', 'mailto:me@example.org']) {
        expect(clickLink(href)).toBe(false);
      }
      expect(clickLink(externalUrl, { download: true })).toBe(false);
      expect(clickLink(externalUrl, { claimed: true })).toBe(true);
      expect(clickLink(externalUrl, { eventType: 'auxclick', button: 2 })).toBe(false);
      expect(postMessage).not.toHaveBeenCalled();
    } finally {
      stopLinks();
      unsubscribe();
    }
  });

  it.each([undefined, ['open-external']])('preserves navigation when the host capability is %s', async (capabilities) => {
    const { bridge, postMessage, unsubscribe } = await setupDirectHost(capabilities);
    const stopLinks = bridge.subscribeToPluginExternalLinks(vi.fn());
    try {
      expect(clickLink(externalUrl, { target: '_blank' })).toBe(false);
      expect(postMessage).not.toHaveBeenCalled();
    } finally {
      stopLinks();
      unsubscribe();
    }
  });

  it.each(['/catalog', '/embed/catalog'])('preserves ordinary browser navigation at %s', async (path) => {
    const bridge = await import('./pluginBridge');
    window.history.replaceState({}, '', path);
    const stopLinks = bridge.subscribeToPluginExternalLinks(vi.fn());
    try {
      expect(clickLink(externalUrl, { target: '_blank' })).toBe(false);
      expect(bridge.openExternalUrlInBrowser(new URL(externalUrl))).toBe(false);
    } finally {
      stopLinks();
    }
  });

  it('keeps the panel in place and reports failed launches or a broken host transport', async () => {
    const { bridge, postMessage, deliver, unsubscribe } = await setupDirectHost(['open-external-url']);
    const onOpenFailed = vi.fn();
    const stopLinks = bridge.subscribeToPluginExternalLinks(onOpenFailed);
    const currentPage = window.location.href;
    try {
      expect(clickLink('https://name:secret@example.org/manual')).toBe(true);
      expect(postMessage).not.toHaveBeenCalled();
      expect(onOpenFailed).toHaveBeenCalledTimes(1);
      expect(window.location.href).toBe(currentPage);
      expect(clickLink(externalUrl)).toBe(true);
      deliver?.({ source: 'filamenthub-host', type: 'external-url-open-failed' });
      expect(onOpenFailed).toHaveBeenCalledTimes(2);
      postMessage.mockImplementationOnce(() => { throw new Error('transport unavailable'); });
      expect(clickLink(externalUrl)).toBe(true);
      expect(onOpenFailed).toHaveBeenCalledTimes(3);
    } finally {
      stopLinks();
      unsubscribe();
    }
  });

  it('shares a clean FilamentHub URL in the system browser', async () => {
    const { postMessage, unsubscribe } = await setupDirectHost(['open-external-url']);
    const { ShareMenu } = await import('../components/ShareMenu');
    const popup = vi.spyOn(window, 'open').mockReturnValue(null);
    try {
      render(<ShareMenu title="A guide" />);
      fireEvent.click(screen.getByRole('button', { name: 'shareMenu.share' }));
      fireEvent.click(screen.getByRole('menuitem', { name: 'Telegram' }));
      expect(popup).not.toHaveBeenCalled();
      expect(postMessage).toHaveBeenCalledTimes(1);
      const message = postMessage.mock.calls[0]?.[0];
      expect(message.bridgeSession).toBe(bridgeSession);
      expect(message.type).toBe('open-external-url');
      const url = new URL(message.url);
      expect(url.origin).toBe('https://t.me');
      expect(url.searchParams.get('url')).toBe(`${window.location.origin}/embed/catalog`);
    } finally {
      unsubscribe();
    }
  });
});
