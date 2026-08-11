import { useCallback, useEffect, useState } from 'react';

interface HeadingReference {
  id: string;
}

interface WikiScrollState {
  activeId: string;
  progress: number;
}

export function useWikiScrollState(headings: readonly HeadingReference[]) {
  const [scrollState, setScrollState] = useState<WikiScrollState>({
    activeId: headings[0]?.id ?? '',
    progress: 0,
  });

  useEffect(() => {
    if (headings.length === 0) {
      setScrollState({ activeId: '', progress: 0 });
      return;
    }

    let animationFrame: number | null = null;

    const updateScrollState = () => {
      animationFrame = null;

      const scrollPosition = window.scrollY + 120;
      let activeId = headings[0].id;

      for (let index = headings.length - 1; index >= 0; index -= 1) {
        const heading = headings[index];
        const element = document.getElementById(heading.id);

        if (element && element.offsetTop <= scrollPosition) {
          activeId = heading.id;
          break;
        }
      }

      const documentHeight = document.documentElement.scrollHeight - window.innerHeight;
      const progress = Math.min(
        100,
        Math.max(0, documentHeight > 0 ? (window.scrollY / documentHeight) * 100 : 0),
      );

      setScrollState((current) => {
        if (current.activeId === activeId && current.progress === progress) {
          return current;
        }

        return { activeId, progress };
      });
    };

    const scheduleUpdate = () => {
      if (animationFrame === null) {
        animationFrame = window.requestAnimationFrame(updateScrollState);
      }
    };

    window.addEventListener('scroll', scheduleUpdate, { passive: true });
    window.addEventListener('resize', scheduleUpdate);
    scheduleUpdate();

    return () => {
      window.removeEventListener('scroll', scheduleUpdate);
      window.removeEventListener('resize', scheduleUpdate);

      if (animationFrame !== null) {
        window.cancelAnimationFrame(animationFrame);
      }
    };
  }, [headings]);

  const selectHeading = useCallback((activeId: string) => {
    setScrollState((current) =>
      current.activeId === activeId ? current : { ...current, activeId },
    );
  }, []);

  return { ...scrollState, selectHeading };
}
