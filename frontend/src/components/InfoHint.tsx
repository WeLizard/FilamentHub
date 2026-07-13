import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Info } from 'lucide-react';

interface InfoHintProps {
  /** Пояснение параметра (уже локализованный текст). */
  text: string;
  className?: string;
}

/**
 * Иконка-подсказка «i» рядом с полем/чекбоксом. Поповер открывается по клику/тапу
 * (не hover — на мобильных hover недоступен) и рендерится порталом в body, чтобы
 * быть поверх модалки и не обрезаться её overflow. Закрывается по клику вне
 * иконки/поповера, Escape и при скролле. Переиспользуемый — один на весь проект.
 */
export const InfoHint: React.FC<InfoHintProps> = ({ text, className }) => {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!open || !btnRef.current) return;
    const r = btnRef.current.getBoundingClientRect();
    setPos({ top: r.bottom + 6, left: r.left + r.width / 2 });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (btnRef.current?.contains(target) || popRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    const onScroll = () => setOpen(false);
    document.addEventListener('mousedown', onDown, true);
    document.addEventListener('keydown', onKey);
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', onScroll);
    return () => {
      document.removeEventListener('mousedown', onDown, true);
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('resize', onScroll);
    };
  }, [open]);

  return (
    <span className={`inline-flex align-middle ${className ?? ''}`}>
      <button
        ref={btnRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="text-gray-400 transition-colors hover:text-purple-300 focus:outline-none focus:text-purple-300"
        aria-label={text}
        aria-expanded={open}
      >
        <Info className="h-3.5 w-3.5" />
      </button>
      {open && pos && createPortal(
        <div
          ref={popRef}
          role="tooltip"
          style={{ position: 'fixed', top: pos.top, left: pos.left, transform: 'translateX(-50%)' }}
          className="z-[10000] w-64 max-w-[80vw] rounded-lg border border-white/15 bg-gray-900 px-3 py-2 text-xs font-normal leading-relaxed text-gray-200 shadow-xl"
        >
          {text}
        </div>,
        document.body,
      )}
    </span>
  );
};
