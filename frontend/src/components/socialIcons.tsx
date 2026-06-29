import type { SVGProps } from 'react';
import { Globe, Instagram, Youtube, Facebook, Linkedin, Github } from 'lucide-react';

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

/** Иконка соцсети/магазина по URL; для неизвестного хоста — глобус. */
export function SocialIcon({ url, className = 'w-4 h-4' }: { url: string; className?: string }) {
  let host = '';
  try {
    host = new URL(url.startsWith('http') ? url : `https://${url}`).hostname.toLowerCase().replace(/^www\./, '');
  } catch {
    host = '';
  }
  if (!host) return <Globe className={className} />;
  const h = (s: string) => host.includes(s);
  if (h('t.me') || h('telegram')) return <TelegramGlyph className={className} />;
  if (h('vk.com') || h('vk.ru') || host === 'vk.cc') return <VkGlyph className={className} />;
  if (h('instagram')) return <Instagram className={className} />;
  if (h('youtube') || h('youtu.be')) return <Youtube className={className} />;
  if (h('facebook') || h('fb.com') || h('fb.me')) return <Facebook className={className} />;
  if (h('twitter') || host === 'x.com') return <XGlyph className={className} />;
  if (h('linkedin')) return <Linkedin className={className} />;
  if (h('github')) return <Github className={className} />;
  return <Globe className={className} />;
}
