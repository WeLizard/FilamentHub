import { useEffect, useRef, useState, type ReactNode } from 'react';

interface OffscreenSectionProps {
  children: ReactNode;
  /** Applied only while the children are mounted; a spacer needs no grid. */
  className?: string;
}

/**
 * Drops its children from the DOM once the section is far outside the viewport
 * and puts them back before it returns, in either scroll direction.
 *
 * A long catalogue keeps every loaded card in the page, and past roughly a
 * hundred cards a modest machine starts dropping frames while scrolling. The
 * section is measured before its children are removed, so the placeholder holds
 * exactly the same height: total page height never changes, and the scrollbar
 * cannot jump under the reader's hand.
 */
export function OffscreenSection({ children, className }: OffscreenSectionProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const heightRef = useRef<number | null>(null);
  const mountedRef = useRef(true);
  const [mounted, setMounted] = useState(true);

  useEffect(() => {
    const element = ref.current;
    if (!element || typeof IntersectionObserver === 'undefined') return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          mountedRef.current = true;
          setMounted(true);
          return;
        }
        mountedRef.current = false;
        setMounted(false);
      },
      // Roughly two screens of lead time, so a section is back in place well
      // before it is looked at.
      { rootMargin: '150% 0px' },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const element = ref.current;
    if (!mounted || !element || typeof ResizeObserver === 'undefined') return;
    // Cards keep growing after they first render — previews and badges arrive
    // late — so the height is kept current while the section is on screen
    // rather than measured once at the moment it leaves.
    const observer = new ResizeObserver(() => {
      const height = element.getBoundingClientRect().height;
      if (height > 0) heightRef.current = height;
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [mounted]);

  useEffect(() => {
    // A measured height belongs to one viewport width. After a resize it is a
    // guess, so the section goes back to rendering and measures itself again.
    const onResize = () => {
      heightRef.current = null;
      mountedRef.current = true;
      setMounted(true);
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  return (
    <div
      ref={ref}
      className={mounted ? className : undefined}
      style={mounted ? undefined : { height: heightRef.current ?? undefined }}
      aria-hidden={mounted ? undefined : true}
    >
      {mounted ? children : null}
    </div>
  );
}
