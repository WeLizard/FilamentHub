import { Globe, ShoppingBag } from 'lucide-react';
import {
  AliExpressIcon,
  AmazonIcon,
  AppleIcon,
  DiscordIcon,
  FacebookIcon,
  GitHubIcon,
  InstagramIcon,
  LinkedInIcon,
  OzonIcon,
  RedditIcon,
  TelegramIcon,
  ThreadsIcon,
  VkIcon,
  WildberriesIcon,
  XIcon,
  YandexIcon,
  YouTubeIcon,
} from './serviceIcons';

const HOSTS = {
  telegram: ['t.me', 'telegram.me', 'telegram.org'],
  vk: ['vk.com', 'vk.ru', 'vk.cc'],
  instagram: ['instagram.com'],
  youtube: ['youtube.com', 'youtu.be'],
  facebook: ['facebook.com', 'fb.com', 'fb.me'],
  x: ['twitter.com', 'x.com'],
  linkedin: ['linkedin.com'],
  github: ['github.com'],
  reddit: ['reddit.com'],
  discord: ['discord.com', 'discord.gg'],
  threads: ['threads.net'],
  apple: ['apple.com'],
  yandex: [
    'ya.ru',
    'yandex.ru',
    'yandex.com',
    'yandex.by',
    'yandex.kz',
    'yandex.uz',
    'yandex.com.tr',
    'yandex.co.il',
    'yandex.eu',
    'yandex.de',
    'yandex.fr',
  ],
  ozon: ['ozon.ru', 'ozon.com'],
  wildberries: ['wildberries.ru', 'wildberries.by', 'wildberries.kz', 'wildberries.am', 'wildberries.uz', 'wb.ru'],
  aliexpress: ['aliexpress.com', 'aliexpress.ru'],
  amazon: [
    'amazon.com',
    'amazon.de',
    'amazon.co.uk',
    'amazon.fr',
    'amazon.it',
    'amazon.es',
    'amazon.nl',
    'amazon.pl',
    'amazon.se',
    'amazon.com.be',
    'amazon.ca',
    'amazon.com.mx',
    'amazon.com.br',
    'amazon.in',
    'amazon.co.jp',
    'amazon.com.au',
    'amazon.sg',
    'amazon.ae',
    'amazon.sa',
    'amazon.com.tr',
    'amazon.eg',
    'amazon.cn',
  ],
  etsy: ['etsy.com'],
} as const;

function matchesHost(host: string, domains: readonly string[]): boolean {
  return domains.some((domain) => host === domain || host.endsWith(`.${domain}`));
}

/** Иконка соцсети/магазина по URL. Для `kind="shop"` неизвестный хост → корзина, иначе глобус. */
export function SocialIcon({
  url,
  className = 'w-4 h-4',
  kind = 'social',
}: {
  url: string;
  className?: string;
  kind?: 'social' | 'shop';
}) {
  let host = '';
  try {
    host = new URL(url.startsWith('http') ? url : `https://${url}`).hostname.toLowerCase().replace(/^www\./, '');
  } catch {
    host = '';
  }
  const fallback = kind === 'shop' ? <ShoppingBag className={className} /> : <Globe className={className} />;
  if (!host) return fallback;
  if (matchesHost(host, HOSTS.telegram)) return <TelegramIcon className={className} />;
  if (matchesHost(host, HOSTS.vk)) return <VkIcon className={className} />;
  if (matchesHost(host, HOSTS.instagram)) return <InstagramIcon className={className} />;
  if (matchesHost(host, HOSTS.youtube)) return <YouTubeIcon className={className} />;
  if (matchesHost(host, HOSTS.facebook)) return <FacebookIcon className={className} />;
  if (matchesHost(host, HOSTS.x)) return <XIcon className={className} />;
  if (matchesHost(host, HOSTS.linkedin)) return <LinkedInIcon className={className} />;
  if (matchesHost(host, HOSTS.github)) return <GitHubIcon className={className} />;
  if (matchesHost(host, HOSTS.reddit)) return <RedditIcon className={className} />;
  if (matchesHost(host, HOSTS.discord)) return <DiscordIcon className={className} />;
  if (matchesHost(host, HOSTS.threads)) return <ThreadsIcon className={className} />;
  if (matchesHost(host, HOSTS.apple)) return <AppleIcon className={className} />;
  if (matchesHost(host, HOSTS.yandex)) return <YandexIcon className={className} />;
  if (matchesHost(host, HOSTS.ozon)) return <OzonIcon className={className} />;
  if (matchesHost(host, HOSTS.wildberries)) return <WildberriesIcon className={className} />;
  if (matchesHost(host, HOSTS.aliexpress)) return <AliExpressIcon className={className} />;
  if (matchesHost(host, HOSTS.amazon)) return <AmazonIcon className={className} />;
  if (matchesHost(host, HOSTS.etsy)) return <ShoppingBag className={className} />;
  return fallback;
}
