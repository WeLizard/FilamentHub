/** Универсальный хук для обработки клика вне элемента */

import { useEffect, RefObject } from 'react';

interface UseClickOutsideOptions {
  ref: RefObject<HTMLElement | null>;
  isOpen: boolean;
  onClose: () => void;
  enabled?: boolean; // Опционально: включить/выключить обработчик
}

export const useClickOutside = ({
  ref,
  isOpen,
  onClose,
  enabled = true,
}: UseClickOutsideOptions): void => {
  useEffect(() => {
    if (!enabled || !isOpen) return;

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (ref.current && !ref.current.contains(target)) {
        onClose();
      }
    };

    // Используем capture phase для более раннего перехвата
    document.addEventListener('mousedown', handleClickOutside, true);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside, true);
    };
  }, [ref, isOpen, onClose, enabled]);
};

