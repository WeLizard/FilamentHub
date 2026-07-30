import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { FilamentPreview } from './FilamentPreview';

describe('FilamentPreview material effects', () => {
  it('keeps the legacy filler visible when effects are absent', () => {
    const { container } = render(
      <FilamentPreview
        colorHex="#8844CC"
        visualSettings={{ filler: 'glitter', colors: ['#8844CC'] }}
      />,
    );

    expect(container.querySelector('pattern[id$="-glitter"]')).not.toBeNull();
  });

  it('layers independent metallic and glitter effects on the same geometry', () => {
    const { container } = render(
      <FilamentPreview
        colorHex="#8844CC"
        visualSettings={{
          filler: 'metallic',
          effects: ['metallic', 'glitter'],
          colors: ['#8844CC'],
        }}
      />,
    );

    expect(container.querySelector('linearGradient[id$="-metallic-body"]')).not.toBeNull();
    expect(container.querySelector('radialGradient[id$="-metallic-end"]')).not.toBeNull();
    expect(container.querySelector('pattern[id$="-glitter"]')).not.toBeNull();
    expect(container.querySelector('pattern[id$="-glitter-end"]')).not.toBeNull();
  });

  it('keeps the original carbon body weave but renders a distinct cut face', () => {
    const { container } = render(
      <FilamentPreview
        colorHex="#20242A"
        visualSettings={{ filler: 'carbon', colors: ['#20242A'] }}
      />,
    );

    const bodyPattern = container.querySelector('pattern[id$="-carbon"]');
    const cutPattern = container.querySelector('pattern[id$="-carbon-end"]');

    expect(bodyPattern).not.toBeNull();
    expect(bodyPattern?.getAttribute('width')).toBe('8');
    expect(bodyPattern?.getAttribute('height')).toBe('8');
    expect(cutPattern).not.toBeNull();
    expect(cutPattern?.id).not.toBe(bodyPattern?.id);
    expect(cutPattern?.querySelector('rect')?.getAttribute('fill')).toBe('#1A1A1A');
  });

  it.each(['glass', 'wood', 'fibers', 'stone', 'carbonaceous', 'microspheres', 'particles'])(
    'uses a cross-sectional cut texture for %s',
    (effect) => {
      const { container } = render(
        <FilamentPreview
          colorHex="#5D7FA3"
          visualSettings={{ filler: effect, colors: ['#5D7FA3'] }}
        />,
      );

      const bodyPattern = container.querySelector(`pattern[id$="-${effect}"]`);
      const cutPattern = container.querySelector(`pattern[id$="-${effect}-end"]`);

      expect(bodyPattern).not.toBeNull();
      expect(cutPattern).not.toBeNull();
      expect(cutPattern?.id).not.toBe(bodyPattern?.id);
    },
  );

  it('uses the selected broad soft glossy highlight without the old hard specular spot', () => {
    const { container } = render(
      <FilamentPreview
        colorHex="#F25D85"
        visualSettings={{ finish: 'glossy', colors: ['#F25D85'] }}
      />,
    );

    expect(container.querySelector('linearGradient[id$="-body-highlight"]')).not.toBeNull();
    expect(container.querySelector('filter[id$="-body-softness"] feGaussianBlur')).not.toBeNull();
    expect(container.querySelector('filter[id$="-end-softness"] feGaussianBlur')).not.toBeNull();
    expect(container.querySelector('[id$="-body-specular"]')).toBeNull();

    const bodyHighlight = [...container.querySelectorAll('path')].find((path) =>
      path.getAttribute('fill')?.includes('body-highlight'),
    );
    expect(bodyHighlight?.getAttribute('opacity')).toBe('0.8');
  });
});
