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
  OdnoklassnikiIcon,
  OzonIcon,
  RedditIcon,
  ServicePathIcon,
  TelegramIcon,
  ThreadsIcon,
  VkIcon,
  WhatsAppIcon,
  WildberriesIcon,
  XIcon,
  YandexIcon,
  YouTubeIcon,
} from './serviceIcons';
import type { ServiceIconKey } from './serviceIconPaths';

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
  threads: ['threads.net', 'threads.com'],
  whatsapp: ['whatsapp.com', 'wa.me'],
  odnoklassniki: ['ok.ru', 'odnoklassniki.ru'],
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
} as const;

// Services drawn from the shared path table, in the order they are tried.
// Hosts are listed exactly: a look-alike domain must not get a service's mark.
// WeChat comes before QQ because its public pages live under qq.com.
const PATH_SERVICES: readonly (readonly [ServiceIconKey, readonly string[]])[] = [
  ['tiktok', ['tiktok.com', 'douyin.com', 'iesdouyin.com']],
  ['pinterest', ['pinterest.com', 'pin.it', 'pinterest.co.uk', 'pinterest.de', 'pinterest.fr', 'pinterest.ru']],
  ['twitch', ['twitch.tv']],
  ['bluesky', ['bsky.app', 'bsky.social']],
  ['mastodon', ['mastodon.social', 'mastodon.online', 'mstdn.social', 'fosstodon.org']],
  ['snapchat', ['snapchat.com']],
  ['tumblr', ['tumblr.com']],
  ['messenger', ['messenger.com', 'm.me']],
  ['signal', ['signal.org', 'signal.me', 'signal.group']],
  ['viber', ['viber.com', 'vb.me']],
  ['line', ['line.me', 'lin.ee']],
  ['kakaotalk', ['kakao.com']],
  ['naver', ['naver.com']],
  ['zalo', ['zalo.me']],
  ['wechat', ['weixin.qq.com', 'wechat.com', 'weixin.com']],
  ['weibo', ['weibo.com', 'weibo.cn']],
  ['bilibili', ['bilibili.com', 'b23.tv']],
  ['xiaohongshu', ['xiaohongshu.com', 'xhslink.com']],
  ['qq', ['qq.com']],
  ['zhihu', ['zhihu.com']],
  ['kuaishou', ['kuaishou.com']],
  ['douban', ['douban.com']],
  ['baidu', ['baidu.com']],
  ['habr', ['habr.com']],
  ['livejournal', ['livejournal.com']],
  ['boosty', ['boosty.to']],
  ['patreon', ['patreon.com']],
  ['kofi', ['ko-fi.com']],
  ['medium', ['medium.com']],
  ['substack', ['substack.com']],
  ['behance', ['behance.net']],
  ['dribbble', ['dribbble.com']],
  ['vimeo', ['vimeo.com']],
  ['printables', ['printables.com']],
  ['thingiverse', ['thingiverse.com']],
  ['bambulab', ['makerworld.com', 'makerworld.com.cn', 'bambulab.com', 'bambulab.cn']],
  ['taobao', ['taobao.com']],
  ['alibaba', ['alibaba.com', '1688.com']],
  ['ebay', ['ebay.com', 'ebay.co.uk', 'ebay.de', 'ebay.fr', 'ebay.it', 'ebay.es', 'ebay.ca', 'ebay.com.au']],
  ['etsy', ['etsy.com']],
  ['shopee', ['shopee.com', 'shopee.sg', 'shopee.co.id', 'shopee.vn', 'shopee.co.th', 'shopee.ph', 'shopee.com.my', 'shopee.tw', 'shopee.com.br']],
];

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
  if (matchesHost(host, HOSTS.whatsapp)) return <WhatsAppIcon className={className} />;
  if (matchesHost(host, HOSTS.odnoklassniki)) return <OdnoklassnikiIcon className={className} />;
  if (matchesHost(host, HOSTS.apple)) return <AppleIcon className={className} />;
  if (matchesHost(host, HOSTS.yandex)) return <YandexIcon className={className} />;
  if (matchesHost(host, HOSTS.ozon)) return <OzonIcon className={className} />;
  if (matchesHost(host, HOSTS.wildberries)) return <WildberriesIcon className={className} />;
  if (matchesHost(host, HOSTS.aliexpress)) return <AliExpressIcon className={className} />;
  if (matchesHost(host, HOSTS.amazon)) return <AmazonIcon className={className} />;
  const service = PATH_SERVICES.find(([, domains]) => matchesHost(host, domains));
  if (service) return <ServicePathIcon name={service[0]} className={className} />;
  return fallback;
}
