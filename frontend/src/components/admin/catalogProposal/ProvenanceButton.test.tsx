import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { CatalogCurationEvidence, CatalogQuoteCheckItem } from '../../../types/api';
import { ProvenanceButton } from './ProvenanceButton';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const item: CatalogCurationEvidence = {
  sheet: 'Filaments', key: 'a', field: 'diameter', kind: 'direct',
  source_urls: ['https://maker.example/a'], quote: 'Diameter 1,75 mm',
};
const check = (status: CatalogQuoteCheckItem['status']): CatalogQuoteCheckItem => ({
  scope: 'evidence', sheet: 'Filaments', key: 'a', field: 'diameter', status,
  reason: null, url: 'https://maker.example/a', checked_at: null, confirmed: false, gating: true,
});

function mount(props: { check?: CatalogQuoteCheckItem; onUpdate?: () => void; onConfirmImage?: (confirmed: boolean) => void } = {}) {
  return render(<ProvenanceButton label="Diameter" entries={[{ item, index: 0 }]} readonly={false}
    check={props.check} onConfirmImage={props.onConfirmImage} onAdd={vi.fn()} onUpdate={props.onUpdate ?? vi.fn()} onRemove={vi.fn()} />);
}

describe('ProvenanceButton quote check', () => {
  it('shows the quote and the verdict in the popover and in the tooltip', () => {
    mount({ check: check('quote_not_found') });
    const trigger = screen.getByRole('button');
    expect(trigger).toHaveAttribute('title', 'adminCatalogImport.curation.kind.direct · adminCatalogImport.curation.quoteStatus.quote_not_found');
    fireEvent.click(trigger);
    expect(screen.getByLabelText('adminCatalogImport.curation.quote 1')).toHaveValue('Diameter 1,75 mm');
    expect(screen.getByText('adminCatalogImport.curation.quoteStatus.quote_not_found')).toBeInTheDocument();
  });

  it('offers a new source only while the field has none, because the server takes one per field', () => {
    const onAdd = vi.fn();
    const { unmount } = render(<ProvenanceButton label="Diameter" entries={[{ item, index: 0 }]} readonly={false}
      onAdd={onAdd} onUpdate={vi.fn()} onRemove={vi.fn()} />);
    fireEvent.click(screen.getByRole('button'));
    expect(screen.queryByRole('button', { name: 'adminCatalogImport.curation.addEvidence' })).not.toBeInTheDocument();
    unmount();
    render(<ProvenanceButton label="Diameter" entries={[]} readonly={false} onAdd={onAdd} onUpdate={vi.fn()} onRemove={vi.fn()} />);
    fireEvent.click(screen.getByRole('button'));
    fireEvent.click(screen.getByRole('button', { name: 'adminCatalogImport.curation.addEvidence' }));
    expect(onAdd).toHaveBeenCalledTimes(1);
  });

  it('shows no verdict for a proposal that was never checked', () => {
    mount();
    fireEvent.click(screen.getByRole('button'));
    expect(screen.queryByText(/quoteStatus/)).not.toBeInTheDocument();
  });

  it('turns a cleared quote into null so the server does not see a blank string', () => {
    const onUpdate = vi.fn();
    mount({ onUpdate });
    fireEvent.click(screen.getByRole('button'));
    fireEvent.change(screen.getByLabelText('adminCatalogImport.curation.quote 1'), { target: { value: '  ' } });
    expect(onUpdate).toHaveBeenCalledWith(0, { quote: null });
  });

  it('offers "checked by eye" only for image-only claims and toggles it', () => {
    const onConfirmImage = vi.fn();
    const { unmount } = mount({ check: check('image_only'), onConfirmImage });
    fireEvent.click(screen.getByRole('button'));
    fireEvent.click(screen.getByText('adminCatalogImport.curation.imageConfirm'));
    expect(onConfirmImage).toHaveBeenCalledWith(true);
    unmount();

    mount({ check: { ...check('image_only'), confirmed: true }, onConfirmImage });
    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByText('adminCatalogImport.curation.quoteStatus.image_confirmed')).toBeInTheDocument();
    fireEvent.click(screen.getByText('adminCatalogImport.curation.imageWithdraw'));
    expect(onConfirmImage).toHaveBeenLastCalledWith(false);
  });

  it('does not offer the confirmation for a quote that failed', () => {
    mount({ check: check('quote_not_found'), onConfirmImage: vi.fn() });
    fireEvent.click(screen.getByRole('button'));
    expect(screen.queryByText('adminCatalogImport.curation.imageConfirm')).not.toBeInTheDocument();
  });
});
