import { useState, useEffect } from 'react';

/**
 * Хук для определения видимости header на странице.
 * Возвращает true, если header виден (верхняя часть header находится выше верхнего края viewport).
 */
export const useHeaderVisible = (): boolean => {
  const [isHeaderVisible, setIsHeaderVisible] = useState(true);

  useEffect(() => {
    const checkHeaderVisibility = () => {
      try {
        // Ищем header элемент
        const header = document.querySelector('header');
        if (!header) {
          // Если header не найден (например, в OrcaSlicer), считаем что его нет
          setIsHeaderVisible(false);
          return;
        }

        // Получаем позицию header относительно viewport
        const rect = header.getBoundingClientRect();
        // Header виден, если его верхняя часть находится выше или на верхнем краю viewport
        setIsHeaderVisible(rect.top >= 0 && rect.bottom > 0);
      } catch (error) {
        // В случае ошибки считаем что header не виден
        console.warn('Error checking header visibility:', error);
        setIsHeaderVisible(false);
      }
    };

    // Проверяем при монтировании с небольшой задержкой, чтобы дать время DOM отрендериться
    const timeoutId = setTimeout(checkHeaderVisibility, 0);

    // Проверяем при скролле и ресайзе
    window.addEventListener('scroll', checkHeaderVisibility, true);
    window.addEventListener('resize', checkHeaderVisibility);

    return () => {
      clearTimeout(timeoutId);
      window.removeEventListener('scroll', checkHeaderVisibility, true);
      window.removeEventListener('resize', checkHeaderVisibility);
    };
  }, []);

  return isHeaderVisible;
};

