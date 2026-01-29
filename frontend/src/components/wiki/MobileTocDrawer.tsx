/** Мобильная шторка с оглавлением для Wiki */

import { useState, useEffect, useCallback } from 'react';
import { List, X, ChevronRight } from 'lucide-react';
import { TocItem, extractHeadings } from './TableOfContents';

interface MobileTocDrawerProps {
  content: string;
  articleTitle: string;
}

export function MobileTocDrawer({ content, articleTitle }: MobileTocDrawerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [headings, setHeadings] = useState<TocItem[]>([]);
  const [activeId, setActiveId] = useState<string>('');

  // Извлекаем заголовки
  useEffect(() => {
    const extracted = extractHeadings(content);
    setHeadings(extracted);
    if (extracted.length > 0) {
      setActiveId(extracted[0].id);
    }
  }, [content]);

  // Отслеживаем скролл
  useEffect(() => {
    const handleScroll = () => {
      const scrollPosition = window.scrollY + 120;

      for (let i = headings.length - 1; i >= 0; i--) {
        const heading = headings[i];
        const element = document.getElementById(heading.id);

        if (element && element.offsetTop <= scrollPosition) {
          setActiveId(heading.id);
          break;
        }
      }
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, [headings]);

  // Блокируем скролл body когда шторка открыта
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }

    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  // Закрытие по Escape
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };

    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, []);

  const scrollToHeading = useCallback((id: string) => {
    setIsOpen(false);

    // Небольшая задержка чтобы шторка закрылась
    setTimeout(() => {
      const element = document.getElementById(id);
      if (element) {
        const offset = 100;
        const elementPosition = element.getBoundingClientRect().top;
        const offsetPosition = elementPosition + window.pageYOffset - offset;

        window.scrollTo({
          top: offsetPosition,
          behavior: 'smooth',
        });

        setActiveId(id);
      }
    }, 150);
  }, []);

  if (headings.length === 0) {
    return null;
  }

  // Находим текущий заголовок для отображения
  const currentHeading = headings.find((h) => h.id === activeId);

  return (
    <>
      {/* Floating Action Button */}
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-40 lg:hidden flex items-center gap-2 px-4 py-3 bg-purple-600/90 hover:bg-purple-600 backdrop-blur-sm text-white font-medium text-sm rounded-full shadow-lg shadow-purple-500/30 transition-all duration-200 hover:scale-105 active:scale-95"
      >
        <List className="w-5 h-5" />
        <span className="hidden sm:inline">Содержание</span>
      </button>

      {/* Backdrop */}
      <div
        className={`fixed inset-0 z-50 bg-black/60 backdrop-blur-sm transition-opacity duration-300 lg:hidden ${
          isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
        onClick={() => setIsOpen(false)}
      />

      {/* Drawer */}
      <div
        className={`fixed inset-y-0 right-0 z-50 w-full max-w-xs lg:hidden bg-gray-900/95 backdrop-blur-md border-l border-white/10 transform transition-transform duration-300 ease-out flex flex-col ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-purple-500/20 rounded-lg flex items-center justify-center">
              <List className="w-4 h-4 text-purple-400" />
            </div>
            <div>
              <h3 className="text-white font-semibold text-sm">Содержание</h3>
              <p className="text-gray-500 text-xs truncate max-w-[180px]">
                {articleTitle}
              </p>
            </div>
          </div>
          <button
            onClick={() => setIsOpen(false)}
            className="p-2 hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        {/* Current Section Indicator */}
        {currentHeading && (
          <div className="px-4 py-3 bg-purple-500/10 border-b border-white/10">
            <div className="text-xs text-gray-500 mb-1">Сейчас читаете</div>
            <div className="text-sm text-purple-300 font-medium truncate">
              {currentHeading.text}
            </div>
          </div>
        )}

        {/* Headings List */}
        <div className="flex-1 overflow-y-auto py-2">
          <nav className="px-2">
            <ul className="space-y-0.5">
              {headings.map((heading) => {
                const isActive = activeId === heading.id;
                const indent = (heading.level - 1) * 16;

                return (
                  <li key={heading.id}>
                    <button
                      onClick={() => scrollToHeading(heading.id)}
                      className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all flex items-center gap-2 ${
                        isActive
                          ? 'bg-purple-500/20 text-purple-300'
                          : 'text-gray-400 hover:bg-white/5 hover:text-white'
                      }`}
                      style={{ paddingLeft: `${12 + indent}px` }}
                    >
                      {isActive && (
                        <ChevronRight className="w-4 h-4 text-purple-400 flex-shrink-0" />
                      )}
                      <span
                        className={`line-clamp-2 ${heading.level === 1 ? 'font-medium' : ''} ${heading.level === 3 ? 'text-xs' : ''}`}
                      >
                        {heading.text}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </nav>
        </div>

        {/* Footer with progress */}
        <div className="p-4 border-t border-white/10">
          <MobileReadingProgress />
        </div>
      </div>
    </>
  );
}

function MobileReadingProgress() {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const updateProgress = () => {
      const scrollTop = window.scrollY;
      const docHeight = document.documentElement.scrollHeight - window.innerHeight;
      const scrollPercent = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
      setProgress(Math.min(100, Math.max(0, scrollPercent)));
    };

    window.addEventListener('scroll', updateProgress, { passive: true });
    updateProgress();

    return () => window.removeEventListener('scroll', updateProgress);
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between text-xs text-gray-500 mb-2">
        <span>Прогресс чтения</span>
        <span className="text-purple-400 font-medium">{Math.round(progress)}%</span>
      </div>
      <div className="h-2 bg-white/10 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-purple-500 to-pink-500 rounded-full transition-all duration-150"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}

export default MobileTocDrawer;
