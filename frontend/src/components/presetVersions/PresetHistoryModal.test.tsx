import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PresetHistoryModal } from './PresetHistoryModal';

const { diffMock, listSavedMock, listVersionsMock } = vi.hoisted(() => ({
  diffMock: vi.fn(),
  listSavedMock: vi.fn(),
  listVersionsMock: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 9 } }),
}));

vi.mock('../../api/client', () => ({
  presetVersionsAPI: {
    diff: (...args: unknown[]) => diffMock(...args),
    list: (...args: unknown[]) => listVersionsMock(...args),
    restore: vi.fn(),
    setLabel: vi.fn(),
  },
  savedPresetsAPI: {
    list: (...args: unknown[]) => listSavedMock(...args),
    updateVersion: vi.fn(),
  },
}));

vi.mock('../ModalOverlay', () => ({
  ModalOverlay: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock('../Toast', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('../../utils/pluginBridge', () => ({
  notifyProfileChanged: vi.fn(),
}));

describe('PresetHistoryModal responsive layout', () => {
  const selectedLabel = 'label_without_any_break_opportunity_'.repeat(4);
  const selectedDescription = 'description_without_any_break_opportunity_'.repeat(12);

  beforeEach(() => {
    vi.clearAllMocks();
    listSavedMock.mockResolvedValue({ items: [] });
    listVersionsMock.mockResolvedValue({
      items: [
        {
          id: 2,
          version_number: 2,
          label: '',
          label_description: null,
          change_source: 'web_edit',
          squash_count: 1,
          created_at: '2026-09-12T10:00:00Z',
        },
        {
          id: 1,
          version_number: 1,
          label: selectedLabel,
          label_description: selectedDescription,
          change_source: 'orca_sync',
          squash_count: 1,
          created_at: '2026-09-11T10:00:00Z',
        },
      ],
    });
    diffMock.mockResolvedValue({
      changes: [{
        key: 'temperature',
        label: 'Очень длинное название параметра 打印温度',
        old: 'old-value-without-spaces-that-must-wrap',
        new: 'new-value-without-spaces-that-must-wrap',
        unit: null,
      }],
      unmapped_changes: [{
        key: 'very_long_technical_key_without_breaks',
        old: 'old-technical-value-without-spaces',
        new: 'new-technical-value-without-spaces',
      }],
    });
  });

  it('stacks mobile panes, restores the desktop split, and wraps diff rows', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <PresetHistoryModal presetId={42} canRestore onClose={vi.fn()} />
      </QueryClientProvider>,
    );

    const dialog = screen.getByRole('dialog', { name: 'presetVersions.title' });
    expect(dialog).toHaveClass('max-h-[calc(100dvh-2rem)]', 'sm:max-h-[85vh]');
    expect(screen.getByTestId('preset-history-layout')).toHaveClass(
      'flex-col',
      'overflow-hidden',
      'md:flex-row',
    );
    expect(screen.getByTestId('preset-history-timeline')).toHaveClass(
      'w-full',
      'min-h-0',
      'flex-1',
      'overflow-y-auto',
      'border-b',
      'md:w-2/5',
      'md:flex-none',
      'md:border-r',
    );
    expect(screen.getByTestId('preset-history-diff')).toHaveClass(
      'w-full',
      'min-w-0',
      'min-h-0',
      'flex-1',
      'overflow-y-auto',
    );

    const label = await screen.findByText('Очень длинное название параметра 打印温度');
    expect(label).toHaveClass('w-full', 'min-w-0', 'break-words', 'md:w-[11.25rem]');
    expect(screen.getByText('old-value-without-spaces-that-must-wrap')).toHaveClass(
      'min-w-0',
      'break-all',
    );

    const technicalSummary = screen.getByText('presetVersions.diff.technicalFields').closest('summary');
    expect(technicalSummary).toHaveClass('min-h-11');
    fireEvent.click(technicalSummary!);
    expect(screen.getByText('very_long_technical_key_without_breaks')).toHaveClass(
      'w-full',
      'min-w-0',
      'break-all',
      'md:w-[11.25rem]',
    );
  });

  it('keeps header, timeline, and version actions usable by touch and keyboard', async () => {
    const onClose = vi.fn();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <PresetHistoryModal presetId={42} canRestore onClose={onClose} />
      </QueryClientProvider>,
    );

    const dialog = screen.getByRole('dialog', { name: 'presetVersions.title' });
    const close = within(dialog).getByRole('button', { name: 'common.close' });
    expect(close).toHaveClass('h-11', 'w-11');
    fireEvent.click(close);
    expect(onClose).toHaveBeenCalledOnce();

    const labeledOnly = within(dialog).getByRole('checkbox', {
      name: 'presetVersions.timeline.labeledOnly',
    });
    expect(labeledOnly.closest('label')).toHaveClass('min-h-11', 'min-w-0');

    await waitFor(() => {
      expect(within(dialog).getByRole('button', { name: /v1/ })).toHaveClass('min-h-11');
    });

    const edit = within(dialog).getByRole('button', { name: 'presetVersions.label.edit' });
    const remove = within(dialog).getByRole('button', { name: 'presetVersions.label.remove' });
    const restore = within(dialog).getByRole('button', { name: 'presetVersions.restore.button' });
    expect(edit).toHaveClass('min-h-11');
    expect(remove).toHaveClass('min-h-11');
    expect(restore).toHaveClass('min-h-11');

    const description = within(dialog).getByText(selectedDescription);
    expect(description).toHaveClass('min-w-0', 'break-all');
    expect(description.previousElementSibling).toHaveTextContent(selectedLabel);
    expect(description.previousElementSibling).toHaveClass('min-w-0', 'break-words');

    fireEvent.click(edit);
    expect(within(dialog).getByPlaceholderText('presetVersions.label.placeholder')).toHaveClass('h-11');
    expect(within(dialog).getByRole('button', { name: 'presetVersions.label.save' })).toHaveClass('min-h-11');
    expect(within(dialog).getByRole('button', { name: 'common.cancel' })).toHaveClass('min-h-11');
  });
});
