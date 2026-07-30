/** Компонент меню для шаринга в соцсети */

import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Share2, Copy, Check, Send } from 'lucide-react';
import {
  OdnoklassnikiIcon,
  TelegramIcon,
  VkIcon,
  WhatsAppIcon,
  XIcon,
} from './serviceIcons';

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
      icon: <TelegramIcon className="w-5 h-5" />,
      color: 'hover:bg-[#0088cc]/20 text-[#0088cc]',
      getUrl: (u, t) => `https://t.me/share/url?url=${encodeURIComponent(u)}&text=${encodeURIComponent(t)}`,
    },
    {
      name: t('shareMenu.vk'),
      icon: <VkIcon className="w-5 h-5" />,
      color: 'hover:bg-[#0077ff]/20 text-[#0077ff]',
      getUrl: (u, t) => `https://vk.com/share.php?url=${encodeURIComponent(u)}&title=${encodeURIComponent(t)}`,
    },
    {
      name: 'WhatsApp',
      icon: <WhatsAppIcon className="w-5 h-5" />,
      color: 'hover:bg-[#25D366]/20 text-[#25D366]',
      getUrl: (u, t) => `https://api.whatsapp.com/send?text=${encodeURIComponent(t + '\n' + u)}`,
    },
    {
      name: 'Twitter/X',
      icon: <XIcon className="w-5 h-5" />,
      color: 'hover:bg-white/20 text-white',
      getUrl: (u, t) => `https://twitter.com/intent/tweet?url=${encodeURIComponent(u)}&text=${encodeURIComponent(t)}`,
    },
    {
      name: t('shareMenu.ok'),
      icon: <OdnoklassnikiIcon className="w-5 h-5" />,
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
