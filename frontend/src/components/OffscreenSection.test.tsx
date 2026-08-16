import { render, screen, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { OffscreenSection } from './OffscreenSection';

type IntersectionCallback = (entries: IntersectionObserverEntry[]) => void;

let intersect: IntersectionCallback | null = null;
let resize: (() => void) | null = null;

class FakeIntersectionObserver {
  constructor(callback: IntersectionCallback) {
    intersect = callback;
  }
  observe() {}
  disconnect() {}
}

class FakeResizeObserver {
  constructor(callback: () => void) {
    resize = callback;
  }
  observe() {}
  disconnect() {}
}

function leaveViewport() {
  act(() => {
    intersect?.([{ isIntersecting: false } as IntersectionObserverEntry]);
  });
}

function enterViewport() {
  act(() => {
    intersect?.([{ isIntersecting: true } as IntersectionObserverEntry]);
  });
}

beforeEach(() => {
  intersect = null;
  resize = null;
  vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver);
  vi.stubGlobal('ResizeObserver', FakeResizeObserver);
  // jsdom has no layout, so every element measures zero; the section only ever
  // records a height it actually saw.
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    height: 640,
    width: 800,
    top: 0,
    left: 0,
    right: 800,
    bottom: 640,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('OffscreenSection', () => {
  it('drops its children once far off screen and brings them back', () => {
    render(
      <OffscreenSection className="grid">
        <article>Filament card</article>
      </OffscreenSection>,
    );
    expect(screen.getByText('Filament card')).toBeTruthy();

    leaveViewport();
    expect(screen.queryByText('Filament card')).toBeNull();

    enterViewport();
    expect(screen.getByText('Filament card')).toBeTruthy();
  });

  it('holds the height it measured, so the page does not shrink under the reader', () => {
    const { container } = render(
      <OffscreenSection className="grid">
        <article>Filament card</article>
      </OffscreenSection>,
    );
    // Cards grow after their first paint; the last observed size is the one worth keeping.
    act(() => resize?.());

    leaveViewport();

    const spacer = container.firstElementChild as HTMLElement;
    expect(spacer.style.height).toBe('640px');
    expect(spacer.className).toBe('');

    enterViewport();
    expect((container.firstElementChild as HTMLElement).style.height).toBe('');
    expect((container.firstElementChild as HTMLElement).className).toBe('grid');
  });
});
