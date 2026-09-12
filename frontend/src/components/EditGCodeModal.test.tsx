import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import adminPrintersSource from './admin/AdminPrinters.tsx?raw';
import createPresetModalSource from './CreatePresetModal.tsx?raw';
import createPrinterProfileModalSource from './CreatePrinterProfileModal.tsx?raw';
import { EditGCodeModal } from './EditGCodeModal';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe('EditGCodeModal', () => {
  const onClose = vi.fn();
  const onInsert = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fits its available width and bounds its list height without changing the desktop maximum', () => {
    render(
      <EditGCodeModal
        isOpen
        onClose={onClose}
        onInsert={onInsert}
        title="Очень длинное название списка 占位符 placeholders"
      />,
    );

    const picker = screen.getByRole('region', {
      name: 'Очень длинное название списка 占位符 placeholders',
    });
    expect(picker).toHaveClass(
      'w-full',
      'min-w-0',
      'max-w-[23.75rem]',
      'h-[16.125rem]',
      'max-h-[calc(100dvh-2rem)]',
      'min-h-0',
      'overflow-hidden',
      'md:w-[23.75rem]',
      'md:shrink-0',
    );
    expect(picker).not.toHaveClass('w-[380px]', 'h-[258px]', 'flex-shrink-0');

    const list = picker.querySelector('.overflow-y-auto');
    expect(list).toHaveClass('min-h-0', 'flex-1');
  });

  it('keeps every interactive picker control at least 44px tall while icons stay compact', () => {
    render(
      <EditGCodeModal
        isOpen
        onClose={onClose}
        onInsert={onInsert}
        title="Placeholders"
        gcodeType="filament_start_gcode"
      />,
    );

    const picker = screen.getByRole('region', { name: 'Placeholders' });
    const closeButton = within(picker).getByRole('button', { name: 'common.close' });
    expect(closeButton).toHaveClass('h-11', 'w-11');
    expect(closeButton.querySelector('svg')).toHaveClass('h-4', 'w-4');

    const search = within(picker).getByRole('textbox', {
      name: 'editGCode.searchPlaceholder',
    });
    expect(search).toHaveClass('h-11');

    const category = within(picker).getByRole('button', { name: 'Filament G-code' });
    expect(category).toHaveClass('min-h-11');
    expect(category).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(category);
    expect(category).toHaveAttribute('aria-expanded', 'true');

    const placeholder = within(picker).getByRole('button', {
      name: /\{filament_extruder_id\}/,
    });
    expect(placeholder).toHaveClass('min-h-11');
    fireEvent.click(placeholder);
    expect(onInsert).toHaveBeenCalledWith('{filament_extruder_id}');

    fireEvent.click(closeButton);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('does not render a closed picker', () => {
    render(
      <EditGCodeModal
        isOpen={false}
        onClose={onClose}
        onInsert={onInsert}
        title="Placeholders"
      />,
    );

    expect(screen.queryByRole('region', { name: 'Placeholders' })).not.toBeInTheDocument();
  });

  it('stacks every consumer row before restoring the desktop side-by-side layout', () => {
    const contracts = [
      {
        source: createPresetModalSource,
        rows: 3,
        textareaMarker: 'w-full min-w-0 resize',
      },
      {
        source: createPrinterProfileModalSource,
        rows: 2,
        textareaMarker: 'w-full min-w-0 resize',
      },
      {
        source: adminPrintersSource,
        rows: 1,
        textareaMarker: 'w-full min-w-0 resize',
      },
    ];

    for (const { source, rows, textareaMarker } of contracts) {
      expect(source.split('flex min-w-0 flex-col items-stretch gap-3 md:flex-row md:items-start')).toHaveLength(rows + 1);
      expect(source.split(textareaMarker).length).toBeGreaterThanOrEqual(rows + 1);
    }
  });
});
