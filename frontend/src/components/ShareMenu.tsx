/** Компонент меню для шаринга в соцсети */

import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Share2, Copy, Check, MessageCircle, Send } from 'lucide-react';

// Иконки соцсетей (inline SVG для компактности)
const VKIcon = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
    <path d="M15.07 2H8.93C3.33 2 2 3.33 2 8.93v6.14C2 20.67 3.33 22 8.93 22h6.14c5.6 0 6.93-1.33 6.93-6.93V8.93C22 3.33 20.67 2 15.07 2zm3.08 14.27h-1.46c-.55 0-.72-.44-1.71-1.45-1.06-1-1.53-1.13-1.79-1.13-.36 0-.47.1-.47.6v1.33c0 .43-.14.68-1.28.68-1.89 0-3.99-1.15-5.47-3.28-2.22-3.12-2.83-5.46-2.83-5.94 0-.26.1-.5.6-.5h1.46c.45 0 .62.21.79.69.87 2.53 2.33 4.75 2.93 4.75.22 0 .33-.1.33-.67V8.29c-.07-1.17-.68-1.27-.68-1.69 0-.21.17-.43.45-.43h2.3c.38 0 .52.21.52.65v3.49c0 .38.17.52.28.52.22 0 .42-.14.84-.56 1.3-1.46 2.22-3.7 2.22-3.7.12-.26.33-.5.78-.5h1.46c.44 0 .54.23.44.54-.19.88-2.03 3.47-2.03 3.47-.16.26-.22.38 0 .67.16.22.7.67 1.07 1.08.67.74 1.18 1.36 1.32 1.79.14.43-.07.65-.51.65z"/>
  </svg>
);

const TelegramIcon = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
    <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
  </svg>
);

const WhatsAppIcon = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
  </svg>
);

const TwitterIcon = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
  </svg>
);

const OKIcon = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
    <path d="M14.505 17.44a11.04 11.04 0 0 0 2.168-1.072l2.404 2.404a1.535 1.535 0 0 1 0 2.172 1.535 1.535 0 0 1-2.172 0l-2.396-2.404a10.88 10.88 0 0 1-4.52.956 10.88 10.88 0 0 1-4.52-.956l-2.396 2.404a1.535 1.535 0 0 1-2.172 0 1.535 1.535 0 0 1 0-2.172l2.404-2.404a11.04 11.04 0 0 0 2.168 1.072l.004-.012c1.332.456 2.824.708 4.512.708s3.18-.252 4.512-.708l.004.012zM9.989 1.536c2.696 0 4.884 2.188 4.884 4.884s-2.188 4.884-4.884 4.884-4.884-2.188-4.884-4.884 2.188-4.884 4.884-4.884zm0 6.24a1.356 1.356 0 1 0 0-2.712 1.356 1.356 0 0 0 0 2.712z"/>
  </svg>
);

interface ShareMenuProps {
  url?: string;
  title: string;
  description?: string;
}

interface ShareOption {
  name: string;
  icon: React.ReactNode;
  color: string;
  getUrl: (url: string, title: string, description: string) => string;
}

export const ShareMenu: React.FC<ShareMenuProps> = ({
  url: propUrl,
  title,
  description = ''
}) => {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const url = propUrl || (typeof window !== 'undefined' ? window.location.href : '');

  const shareOptions: ShareOption[] = [
    {
      name: 'Telegram',
      icon: <TelegramIcon />,
      color: 'hover:bg-[#0088cc]/20 text-[#0088cc]',
      getUrl: (u, t) => `https://t.me/share/url?url=${encodeURIComponent(u)}&text=${encodeURIComponent(t)}`,
    },
    {
      name: t('shareMenu.vk'),
      icon: <VKIcon />,
      color: 'hover:bg-[#0077ff]/20 text-[#0077ff]',
      getUrl: (u, t) => `https://vk.com/share.php?url=${encodeURIComponent(u)}&title=${encodeURIComponent(t)}`,
    },
    {
      name: 'WhatsApp',
      icon: <WhatsAppIcon />,
      color: 'hover:bg-[#25D366]/20 text-[#25D366]',
      getUrl: (u, t) => `https://api.whatsapp.com/send?text=${encodeURIComponent(t + '\n' + u)}`,
    },
    {
      name: 'Twitter/X',
      icon: <TwitterIcon />,
      color: 'hover:bg-white/20 text-white',
      getUrl: (u, t) => `https://twitter.com/intent/tweet?url=${encodeURIComponent(u)}&text=${encodeURIComponent(t)}`,
    },
    {
      name: t('shareMenu.ok'),
      icon: <OKIcon />,
      color: 'hover:bg-[#ee8208]/20 text-[#ee8208]',
      getUrl: (u, t) => `https://connect.ok.ru/offer?url=${encodeURIComponent(u)}&title=${encodeURIComponent(t)}`,
    },
  ];

  // Закрытие по клику вне меню
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  // Закрытие по Escape
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
    }
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen]);

  const handleShare = (option: ShareOption) => {
    const shareUrl = option.getUrl(url, title, description);
    window.open(shareUrl, '_blank', 'width=600,height=400');
    setIsOpen(false);
  };

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const handleNativeShare = async () => {
    if (navigator.share) {
      try {
        await navigator.share({
          title,
          text: description,
          url,
        });
        setIsOpen(false);
      } catch (err) {
        // Пользователь отменил шаринг - это нормально
        if ((err as Error).name !== 'AbortError') {
          console.error('Share failed:', err);
        }
      }
    }
  };

  return (
    <div className="relative" ref={menuRef}>
      {/* Кнопка "Поделиться" */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-4 py-2 bg-white/10 hover:bg-white/15 text-white rounded-lg transition-colors"
        aria-expanded={isOpen}
        aria-haspopup="true"
      >
        <Share2 className="w-4 h-4" />
        <span className="hidden sm:inline">{t('shareMenu.share')}</span>
      </button>

      {/* Выпадающее меню */}
      {isOpen && (
        <div
          className="absolute right-0 mt-2 w-56 bg-gray-900 border border-white/20 rounded-xl shadow-xl z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200"
          role="menu"
        >
          {/* Нативный шаринг (если поддерживается) */}
          {typeof navigator !== 'undefined' && 'share' in navigator && (
            <button
              onClick={handleNativeShare}
              className="w-full flex items-center gap-3 px-4 py-3 text-left text-gray-200 hover:bg-white/10 transition-colors border-b border-white/10"
              role="menuitem"
            >
              <Send className="w-5 h-5 text-purple-400" />
              <span>{t('shareMenu.shareNative')}</span>
            </button>
          )}

          {/* Соцсети */}
          {shareOptions.map((option) => (
            <button
              key={option.name}
              onClick={() => handleShare(option)}
              className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors ${option.color}`}
              role="menuitem"
            >
              {option.icon}
              <span className="text-gray-200">{option.name}</span>
            </button>
          ))}

          {/* Разделитель */}
          <div className="border-t border-white/10" />

          {/* Копировать ссылку */}
          <button
            onClick={handleCopyLink}
            className="w-full flex items-center gap-3 px-4 py-3 text-left text-gray-200 hover:bg-white/10 transition-colors"
            role="menuitem"
          >
            {copied ? (
              <>
                <Check className="w-5 h-5 text-green-400" />
                <span className="text-green-400">{t('shareMenu.copied')}</span>
              </>
            ) : (
              <>
                <Copy className="w-5 h-5 text-gray-400" />
                <span>{t('shareMenu.copyLink')}</span>
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
};
