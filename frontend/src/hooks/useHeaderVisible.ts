import { useState, useEffect } from 'react';

/**
 * Хук для определения видимости header на странице.
 * Возвращает true, если header виден (верхняя часть header находится выше верхнего края viewport).
 */
export const useHeaderVisible = (): boolean => {
  const [isHeaderVisible, setIsHeaderVisible] = useState(true);

  useEffect(() => {
    let observer: IntersectionObserver | null = null;
    const frameId = window.requestAnimationFrame(() => {
      const header = document.querySelector('header');
      if (!header) {
        setIsHeaderVisible(false);
        return;
      }
      observer = new IntersectionObserver(([entry]) => {
        setIsHeaderVisible(entry.isIntersecting);
      });
      observer.observe(header);
    });

    return () => {
      window.cancelAnimationFrame(frameId);
      observer?.disconnect();
    };
  }, []);

  return isHeaderVisible;
};

