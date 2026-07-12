import { useEffect, useRef, useState } from 'react';
import { Info } from 'lucide-react';

interface InfoHintProps {
  /** Пояснение параметра (уже локализованный текст). */
  text: string;
  className?: string;
}

/**
 * Иконка-подсказка «i» рядом с полем формы. Поповер открывается по клику/тапу
 * (не hover — на мобильных hover недоступен), закрывается по клику вне и Escape.
 * Переиспользуемый компонент — один на весь проект (правило реюза).
 */
export const InfoHint: React.FC<InfoHintProps> = ({ text, className }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocPointer = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDocPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <span ref={ref} className={`relative inline-flex align-middle ${className ?? ''}`}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="text-gray-400 transition-colors hover:text-purple-300 focus:outline-none focus:text-purple-300"
        aria-label={text}
        aria-expanded={open}
      >
        <Info className="h-3.5 w-3.5" />
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute left-1/2 top-6 z-50 w-64 -translate-x-1/2 rounded-lg border border-white/15 bg-gray-900 px-3 py-2 text-xs font-normal leading-relaxed text-gray-200 shadow-xl"
        >
          {text}
        </span>
      )}
    </span>
  );
};
