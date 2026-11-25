import type { ReactElement } from 'react';
import { Globe, ShoppingBag } from 'lucide-react';
import { describe, expect, it } from 'vitest';
import {
  AmazonIcon,
  AppleIcon,
  DiscordIcon,
  OdnoklassnikiIcon,
  ServicePathIcon,
  ThreadsIcon,
  WhatsAppIcon,
  WildberriesIcon,
  YandexIcon,
} from './serviceIcons';
import { hasMetaNetworkLink } from '../utils/restrictedNetworks';
import { SocialIcon } from './socialIcons';

function iconFor(url: string): ReactElement {
  return SocialIcon({ url }) as ReactElement;
}

function shopIconFor(url: string): ReactElement {
  return SocialIcon({ url, kind: 'shop' }) as ReactElement;
}

describe('SocialIcon service matching', () => {
  it.each([
    ['https://discord.gg/filamenthub', DiscordIcon],
    ['https://www.threads.net/@filamenthub', ThreadsIcon],
    ['https://www.apple.com/filamenthub', AppleIcon],
    ['https://yandex.ru/company/filamenthub', YandexIcon],
    ['https://www.amazon.de/example', AmazonIcon],
    ['https://www.wildberries.ru/catalog/example', WildberriesIcon],
  ])('uses the reviewed service icon for %s', (url, icon) => {
    expect(iconFor(url).type).toBe(icon);
  });

  it.each([
    ['https://notapple.com', Globe],
    ['https://amazon.example', Globe],
    ['https://github.com.example.org', Globe],
    ['https://fake-yandex.ru.example.com', Globe],
  ])('does not classify an unrelated hostname as %s', (url, fallback) => {
    expect(iconFor(url).type).toBe(fallback);
  });

  it.each([
    ['https://www.tiktok.com/@brand', 'tiktok'],
    ['https://www.douyin.com/user/brand', 'tiktok'],
    // WeChat pages live under qq.com and must not be labelled as QQ.
    ['https://mp.weixin.qq.com/s/abc', 'wechat'],
    ['https://user.qzone.qq.com/1', 'qq'],
    ['https://space.bilibili.com/1', 'bilibili'],
    ['https://www.xiaohongshu.com/user/profile/1', 'xiaohongshu'],
    ['https://www.printables.com/@brand', 'printables'],
    ['https://makerworld.com/en/@brand', 'bambulab'],
    ['https://boosty.to/brand', 'boosty'],
  ])('labels %s with the mark of its service', (url, name) => {
    const icon = iconFor(url);

    expect(icon.type).toBe(ServicePathIcon);
    expect((icon.props as { name: string }).name).toBe(name);
  });

  it.each([
    ['https://ok.ru/brand', OdnoklassnikiIcon],
    ['https://wa.me/123', WhatsAppIcon],
  ])('labels %s with its existing icon', (url, icon) => {
    expect(iconFor(url).type).toBe(icon);
  });

  it.each([
    'https://tiktok.com.example.org',
    'https://notbilibili.com',
    'https://qq.com.evil.example',
  ])('gives a look-alike host %s no service mark', (url) => {
    expect(iconFor(url).type).toBe(Globe);
  });

  it('counts Messenger links as links to a Meta network', () => {
    expect(hasMetaNetworkLink(['https://m.me/brand'])).toBe(true);
    expect(hasMetaNetworkLink(['https://www.threads.com/@brand'])).toBe(true);
    expect(hasMetaNetworkLink(['https://wa.me/123', 'https://t.me/brand'])).toBe(false);
  });

  it('keeps the shop fallback for an unknown marketplace hostname', () => {
    expect(shopIconFor('https://amazon.example').type).toBe(ShoppingBag);
  });
});
