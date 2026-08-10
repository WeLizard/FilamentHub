import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import {
  WikiGuideCalloutLegend,
  WikiGuideImageCanvas,
  WikiGuideImageViewer,
} from './WikiGuideImageViewer';
import type { WikiGuideImage } from './wikiGuide';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const image: WikiGuideImage = {
  src: '/guide.webp',
  alt: 'Guide screenshot',
  callouts: [
    { x: 25, y: 30, label: 'Open catalog' },
    { x: 70, y: 65, label: 'Choose material' },
  ],
};

function LinkedCallouts() {
  const [activeCallout, setActiveCallout] = useState<number | null>(null);

  return (
    <>
      <WikiGuideImageCanvas
        image={image}
        activeCallout={activeCallout}
        onActiveCalloutChange={setActiveCallout}
      />
      <WikiGuideCalloutLegend
        image={image}
        activeCallout={activeCallout}
        onActiveCalloutChange={setActiveCallout}
      />
    </>
  );
}

describe('WikiGuideImageViewer', () => {
  it('links callout markers with their legend entries in both directions', () => {
    const { container } = render(<LinkedCallouts />);
    const marker = screen.getByRole('button', { name: '1. Open catalog' });
    const legendItem = container.querySelector('li');

    expect(legendItem).not.toBeNull();
    fireEvent.mouseEnter(legendItem!);
    expect(marker).toHaveAttribute('data-active', 'true');

    fireEvent.mouseLeave(legendItem!);
    fireEvent.mouseEnter(marker);
    expect(legendItem).toHaveAttribute('data-active', 'true');
  });

  it('keeps the regular wheel for panning and zooms with a modified wheel gesture', () => {
    const requestAnimationFrame = vi
      .spyOn(window, 'requestAnimationFrame')
      .mockImplementation((callback) => {
        callback(0);
        return 1;
      });
    render(<WikiGuideImageViewer image={image} onClose={vi.fn()} />);
    const scrollArea = screen.getByTestId('wiki-image-scroll-area');

    fireEvent.wheel(scrollArea, { deltaY: -100, clientX: 200, clientY: 150 });
    expect(screen.getByText(/100%/)).toBeInTheDocument();

    fireEvent.wheel(scrollArea, {
      ctrlKey: true,
      deltaY: -100,
      clientX: 200,
      clientY: 150,
    });
    expect(screen.getByText(/122%/)).toBeInTheDocument();

    scrollArea.scrollLeft = 120;
    scrollArea.scrollTop = 80;
    fireEvent.pointerDown(scrollArea, {
      button: 0,
      pointerId: 1,
      clientX: 200,
      clientY: 150,
    });
    fireEvent.pointerMove(scrollArea, { pointerId: 1, clientX: 150, clientY: 110 });

    expect(scrollArea.scrollLeft).toBe(170);
    expect(scrollArea.scrollTop).toBe(120);
    expect(scrollArea).toHaveClass('cursor-grabbing');

    fireEvent.pointerUp(scrollArea, { pointerId: 1 });
    expect(scrollArea).not.toHaveClass('cursor-grabbing');
    requestAnimationFrame.mockRestore();
  });

  it('supports pinch zoom for touch screens', () => {
    const requestAnimationFrame = vi
      .spyOn(window, 'requestAnimationFrame')
      .mockImplementation((callback) => {
        callback(0);
        return 1;
      });
    render(<WikiGuideImageViewer image={image} onClose={vi.fn()} />);
    const scrollArea = screen.getByTestId('wiki-image-scroll-area');

    fireEvent.pointerDown(scrollArea, {
      button: 0,
      pointerId: 11,
      pointerType: 'touch',
      clientX: 100,
      clientY: 100,
    });
    fireEvent.pointerDown(scrollArea, {
      button: 0,
      pointerId: 12,
      pointerType: 'touch',
      clientX: 200,
      clientY: 100,
    });
    fireEvent.pointerMove(scrollArea, {
      pointerId: 12,
      pointerType: 'touch',
      clientX: 250,
      clientY: 100,
    });

    expect(screen.getByText(/150%/)).toBeInTheDocument();
    requestAnimationFrame.mockRestore();
  });

  it('closes from the explicit button and a genuine backdrop click', () => {
    const onClose = vi.fn();
    render(<WikiGuideImageViewer image={image} onClose={onClose} />);

    fireEvent.click(screen.getByRole('button', { name: 'wikiGuide.closeImage' }));
    expect(onClose).toHaveBeenCalledTimes(1);

    const overlayContent = screen.getByRole('dialog').parentElement;
    expect(overlayContent).not.toBeNull();
    fireEvent.mouseDown(overlayContent!);
    fireEvent.click(overlayContent!);
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
