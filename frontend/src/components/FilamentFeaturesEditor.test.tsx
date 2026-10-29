import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FilamentFeaturesEditor } from './FilamentFeaturesEditor';
import type { FilamentAdditive } from '../types/api';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const renderEditor = (additives: FilamentAdditive[]) =>
  render(
    <FilamentFeaturesEditor
      effects={[]}
      onEffectsChange={() => undefined}
      additives={additives}
      onAdditivesChange={() => undefined}
      propertyClaims={[]}
      onPropertyClaimsChange={() => undefined}
    />,
  );

describe('FilamentFeaturesEditor composition share', () => {
  it('asks for a share only where manufacturers state one', () => {
    renderEditor([{ code: 'carbon_fiber' }, { code: 'uv_stabilizers_hals' }]);

    expect(screen.getAllByPlaceholderText('filamentFeatures.percent')).toHaveLength(1);
    expect(screen.getByText('filamentFeatures.additives.uv_stabilizers_hals')).toBeInTheDocument();
  });

  it('keeps an already entered share of a stabiliser editable', () => {
    renderEditor([{ code: 'uv_stabilizers_hals', content_percent: 0.5 }]);

    expect(screen.getByPlaceholderText('filamentFeatures.percent')).toHaveValue(0.5);
  });
});
