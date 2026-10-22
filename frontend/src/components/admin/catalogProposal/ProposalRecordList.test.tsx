import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ProposalRecordList } from './ProposalRecordList';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe('ProposalRecordList paging', () => {
  it('shows the last page and tells the parent when a narrower filter leaves the page past the end', () => {
    const onPageChange = vi.fn();
    const rows = [0, 1, 2].map((index) => ({ index, row: { brand_key: `b${index}`, name: `Brand ${index}` } }));
    render(<ProposalRecordList sheet="brands" rows={rows} page={4} pageSize={2} onPageChange={onPageChange}
      selected={new Set()} onSelect={vi.fn()} openIndex={null} onOpen={vi.fn()} planByRow={new Map()}
      coverage={() => undefined} marketCells={() => []} differs={new Set()} hasDefault={false} showBrand={false} disabled={false} />);
    expect(onPageChange).toHaveBeenCalledWith(2);
    expect(screen.getByText('Brand 2')).toBeInTheDocument();
    expect(screen.queryByText('Brand 0')).not.toBeInTheDocument();
  });
});
