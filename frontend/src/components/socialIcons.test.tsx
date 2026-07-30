import type { ReactElement } from 'react';
import { Globe, ShoppingBag } from 'lucide-react';
import { describe, expect, it } from 'vitest';
import {
  AmazonIcon,
  AppleIcon,
  DiscordIcon,
  ThreadsIcon,
  WildberriesIcon,
  YandexIcon,
} from './serviceIcons';
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

  it('keeps the shop fallback for an unknown marketplace hostname', () => {
    expect(shopIconFor('https://amazon.example').type).toBe(ShoppingBag);
  });
});
