import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FilamentAdditionalProperties } from './FilamentAdditionalProperties';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

describe('FilamentAdditionalProperties', () => {
  it('shows approved facts in one compact list with sources and public provenance', () => {
    render(<FilamentAdditionalProperties properties={[
      {
        property_name: 'Impact strength', value_summary: '12 kJ/m²', kind: 'direct',
        source_urls: ['https://maker.example/pla/technical'],
      },
      {
        property_name: 'Chemical resistance', value_summary: 'Resists diluted acids', kind: 'inferred',
        source_urls: ['https://maker.example/pla/guide'],
      },
    ]} />);

    expect(screen.getByRole('heading', { name: 'filamentDetailPage.additionalProperties' })).toBeInTheDocument();
    expect(screen.getByText('Impact strength')).toBeInTheDocument();
    expect(screen.getByText('12 kJ/m²')).toBeInTheDocument();
    expect(screen.getByText('filamentDetailPage.inferredFromManufacturer')).toBeInTheDocument();
    const sourceLinks = screen.getAllByRole('link', { name: /filamentDetailPage.manufacturerSource/ });
    expect(sourceLinks).toHaveLength(2);
    expect(sourceLinks[0]).toHaveAttribute(
      'href', 'https://maker.example/pla/technical',
    );
    expect(screen.queryByText(/Calculated|reasoning/i)).not.toBeInTheDocument();
  });

  it('renders nothing when a filament has no approved additional facts', () => {
    const { container } = render(<FilamentAdditionalProperties properties={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
