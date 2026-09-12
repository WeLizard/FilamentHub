import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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

    const search = within(picker).getByPlaceholderText('editGCode.searchPlaceholder');
    expect(search).toHaveClass('h-11');

    const category = within(picker).getByRole('button', { name: 'Filament G-code' });
    expect(category).toHaveClass('min-h-11');
    fireEvent.click(category);

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
});
