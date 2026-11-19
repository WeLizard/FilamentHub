import { useEffect, useRef } from 'react';

/**
 * Asks for the next page once the returned element comes within 400px of the
 * viewport, so a long list loads only as far as the reader scrolls. The caller
 * keeps a visible "load more" button for browsers without IntersectionObserver.
 */
export function useLoadMoreOnScroll<T extends Element>({
  hasNextPage,
  isFetching,
  fetchNextPage,
}: {
  hasNextPage: boolean | undefined;
  isFetching: boolean;
  fetchNextPage: () => unknown;
}) {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    const target = ref.current;
    if (!target || !hasNextPage || typeof IntersectionObserver === 'undefined') {
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !isFetching) {
          void fetchNextPage();
        }
      },
      { rootMargin: '400px 0px' },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [fetchNextPage, hasNextPage, isFetching]);

  return ref;
}
