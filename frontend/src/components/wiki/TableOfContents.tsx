/** Компонент оглавления для Wiki статей */

import { useState, useEffect, useCallback } from 'react';
import { List, ChevronRight } from 'lucide-react';

export interface TocItem {
  id: string;
  text: string;
  level: number;
}

interface TableOfContentsProps {
  content: string;
  className?: string;
}

/**
 * Извлекает заголовки из markdown контента
 */
export function extractHeadings(content: string): TocItem[] {
  const headings: TocItem[] = [];
  const lines = content.split('\n');

  for (const line of lines) {
    // Проверяем заголовки markdown (## Heading)
    const match = line.match(/^(#{1,3})\s+(.+)$/);
    if (match) {
      const level = match[1].length;
      const text = match[2].trim();
      // Генерируем ID из текста (slug)
      const id = text
        .toLowerCase()
        .replace(/[^\w\sа-яё-]/gi, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .trim();

      headings.push({ id, text, level });
    }
  }

  return headings;
}

/**
 * Генерирует ID для заголовка (используется в ReactMarkdown)
 */
export function generateHeadingId(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\sа-яё-]/gi, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .trim();
}

export function TableOfContents({ content, className }: TableOfContentsProps) {
  const [headings, setHeadings] = useState<TocItem[]>([]);
  const [activeId, setActiveId] = useState<string>('');

  // Извлекаем заголовки при изменении контента
  useEffect(() => {
    const extracted = extractHeadings(content);
    setHeadings(extracted);

    // Устанавливаем первый заголовок как активный
    if (extracted.length > 0 && !activeId) {
      setActiveId(extracted[0].id);
    }
  }, [content]);

  // Отслеживаем скролл для подсветки активной секции
  useEffect(() => {
    const handleScroll = () => {
      const scrollPosition = window.scrollY + 120; // offset для header

      // Находим текущую секцию
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
    handleScroll(); // Вызываем сразу для инициализации

    return () => window.removeEventListener('scroll', handleScroll);
  }, [headings]);

  // Плавная прокрутка к секции
  const scrollToHeading = useCallback((id: string) => {
    const element = document.getElementById(id);
    if (element) {
      const offset = 100; // Отступ от верха для header
      const elementPosition = element.getBoundingClientRect().top;
      const offsetPosition = elementPosition + window.pageYOffset - offset;

      window.scrollTo({
        top: offsetPosition,
        behavior: 'smooth',
      });

      setActiveId(id);
    }
  }, []);

  if (headings.length === 0) {
    return null;
  }

  return (
    <nav className={`space-y-1 ${className || ''}`}>
      {/* Заголовок */}
      <div className="flex items-center gap-2 text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3 px-3">
        <List className="w-4 h-4" />
        <span>Содержание</span>
      </div>

      {/* Список заголовков */}
      <ul className="space-y-0.5">
        {headings.map((heading) => {
          const isActive = activeId === heading.id;
          const indent = (heading.level - 1) * 12; // Отступ для вложенности

          return (
            <li key={heading.id}>
              <button
                onClick={() => scrollToHeading(heading.id)}
                className={`group w-full text-left px-3 py-2 rounded-lg text-sm transition-all duration-200 hover:bg-white/5 hover:text-white ${
                  isActive
                    ? 'bg-purple-500/20 text-purple-300 border-l-2 border-purple-500'
                    : 'text-gray-400 border-l-2 border-transparent'
                }`}
                style={{ paddingLeft: `${12 + indent}px` }}
              >
                <span className="flex items-center gap-2">
                  {isActive && (
                    <ChevronRight className="w-3 h-3 text-purple-400 flex-shrink-0" />
                  )}
                  <span
                    className={`line-clamp-2 ${heading.level === 1 ? 'font-medium' : ''} ${heading.level === 2 ? 'font-normal' : ''} ${heading.level === 3 ? 'text-xs' : ''}`}
                  >
                    {heading.text}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      {/* Прогресс чтения */}
      <ReadingProgress />
    </nav>
  );
}

/**
 * Индикатор прогресса чтения статьи
 */
function ReadingProgress() {
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
    <div className="mt-4 px-3">
      <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
        <span>Прогресс</span>
        <span>{Math.round(progress)}%</span>
      </div>
      <div className="h-1 bg-white/10 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-purple-500 to-pink-500 rounded-full transition-all duration-150"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}

export default TableOfContents;
