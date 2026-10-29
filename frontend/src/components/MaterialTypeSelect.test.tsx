import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-i18next')>()),
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));
vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  filamentsAPI: { getMaterialTypeGroups: vi.fn().mockResolvedValue([]) },
}));

import { MaterialTypeSelect } from './MaterialTypeSelect';

describe('MaterialTypeSelect list', () => {
  it('is opaque so the colour swatch behind it never shows through', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MaterialTypeSelect value="" options={['PLA', 'PETG']} onChange={vi.fn()} />
      </QueryClientProvider>,
    );
    fireEvent.focus(screen.getByRole('textbox'));
    const panel = screen.getByText('PLA').closest('.absolute');
    expect(panel).not.toBeNull();
    expect(panel!.className).toMatch(/\bbg-gray-800\b(?!\/)/);
    expect(panel!.className).not.toMatch(/backdrop-blur/);
  });
});
