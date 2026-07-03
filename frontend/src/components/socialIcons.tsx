import type { SVGProps } from 'react';
import { Globe, Instagram, Youtube, Facebook, Linkedin, Github, ShoppingBag } from 'lucide-react';

// Брендовые SVG, которых нет в lucide (берём по образцу ShareMenu).
const TelegramGlyph = (p: SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" fill="currentColor" {...p}>
    <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z" />
  </svg>
);

const VkGlyph = (p: SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" fill="currentColor" {...p}>
    <path d="M15.07 2H8.93C3.33 2 2 3.33 2 8.93v6.14C2 20.67 3.33 22 8.93 22h6.14c5.6 0 6.93-1.33 6.93-6.93V8.93C22 3.33 20.68 2 15.07 2zm3.07 14.27h-1.45c-.55 0-.72-.44-1.71-1.43-.86-.83-1.24-.94-1.45-.94-.3 0-.38.08-.38.49v1.31c0 .35-.11.56-1.04.56-1.54 0-3.24-.93-4.44-2.66-1.81-2.54-2.31-4.45-2.31-4.84 0-.21.08-.4.49-.4h1.45c.37 0 .51.17.65.56.71 2.06 1.91 3.86 2.4 3.86.18 0 .27-.08.27-.55v-2.13c-.06-.98-.58-1.06-.58-1.41 0-.17.14-.34.37-.34h2.28c.31 0 .42.17.42.53v2.87c0 .31.14.42.23.42.18 0 .33-.11.66-.44 1.02-1.14 1.75-2.9 1.75-2.9.1-.21.27-.4.64-.4h1.45c.44 0 .53.22.44.53-.18.85-1.97 3.37-1.97 3.37-.15.25-.21.36 0 .64.15.21.65.64.98 1.03.61.69 1.07 1.27 1.2 1.67.12.4-.08.6-.49.6z" />
  </svg>
);

const XGlyph = (p: SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" fill="currentColor" {...p}>
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
  </svg>
);

const RedditGlyph = (p: SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" fill="currentColor" {...p}>
    <path d="M12 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm5.01 4.744c.688 0 1.25.561 1.25 1.249a1.25 1.25 0 0 1-2.498.056l-2.597-.547-.8 3.747c1.824.07 3.48.632 4.674 1.488.308-.309.73-.491 1.207-.491.968 0 1.754.786 1.754 1.754 0 .716-.435 1.333-1.01 1.614a3.111 3.111 0 0 1 .042.52c0 2.694-3.13 4.87-6.99 4.87-3.86 0-6.99-2.176-6.99-4.87 0-.183.015-.366.043-.534A1.748 1.748 0 0 1 4.028 12c0-.968.786-1.754 1.754-1.754.463 0 .898.196 1.207.49 1.207-.883 2.878-1.43 4.744-1.487l.885-4.182a.342.342 0 0 1 .14-.197.35.35 0 0 1 .238-.042l2.906.617a1.214 1.214 0 0 1 1.108-.701zM9.25 12C8.561 12 8 12.562 8 13.25c0 .687.561 1.248 1.25 1.248.687 0 1.248-.561 1.248-1.249 0-.688-.561-1.249-1.249-1.249zm5.5 0c-.687 0-1.248.561-1.248 1.25 0 .687.561 1.248 1.249 1.248.688 0 1.249-.561 1.249-1.249 0-.687-.562-1.249-1.25-1.249zm-5.466 3.99a.327.327 0 0 0-.231.094.33.33 0 0 0 0 .463c.842.842 2.484.913 2.961.913.477 0 2.105-.056 2.961-.913a.361.361 0 0 0 .029-.463.33.33 0 0 0-.464 0c-.547.533-1.684.73-2.512.73-.828 0-1.979-.196-2.512-.73a.326.326 0 0 0-.232-.095z" />
  </svg>
);

// Маркетплейсы — узнаваемые брендовые бейджи (буква на фирменном цвете).
const OzonGlyph = (p: SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" {...p}>
    <rect width="24" height="24" rx="5" fill="#005BFF" />
    <text x="12" y="17" textAnchor="middle" fontSize="14" fontWeight="700" fill="#fff" fontFamily="Arial, sans-serif">O</text>
  </svg>
);

const WbGlyph = (p: SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" {...p}>
    <rect width="24" height="24" rx="5" fill="#CB11AB" />
    <text x="12" y="16" textAnchor="middle" fontSize="10" fontWeight="700" fill="#fff" fontFamily="Arial, sans-serif">WB</text>
  </svg>
);

const AliGlyph = (p: SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" {...p}>
    <rect width="24" height="24" rx="5" fill="#E62E04" />
    <text x="12" y="17" textAnchor="middle" fontSize="14" fontWeight="700" fill="#fff" fontFamily="Arial, sans-serif">A</text>
  </svg>
);

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
  const h = (s: string) => host.includes(s);
  if (h('t.me') || h('telegram')) return <TelegramGlyph className={className} />;
  if (h('vk.com') || h('vk.ru') || host === 'vk.cc') return <VkGlyph className={className} />;
  if (h('instagram')) return <Instagram className={className} />;
  if (h('youtube') || h('youtu.be')) return <Youtube className={className} />;
  if (h('facebook') || h('fb.com') || h('fb.me')) return <Facebook className={className} />;
  if (h('twitter') || host === 'x.com') return <XGlyph className={className} />;
  if (h('linkedin')) return <Linkedin className={className} />;
  if (h('github')) return <Github className={className} />;
  if (h('reddit')) return <RedditGlyph className={className} />;
  // Маркетплейсы.
  if (h('ozon')) return <OzonGlyph className={className} />;
  if (h('wildberries') || h('wb.ru')) return <WbGlyph className={className} />;
  if (h('aliexpress')) return <AliGlyph className={className} />;
  if (h('amazon') || h('etsy')) return <ShoppingBag className={className} />;
  return fallback;
}
