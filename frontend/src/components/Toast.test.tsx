import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ToastContainer, toast } from './Toast';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe('toast problem report', () => {
  afterEach(() => {
    act(() => toast.clear());
  });

  it('turns a reportable error icon into a report control that closes the toast', () => {
    const onReport = vi.fn();
    render(<ToastContainer />);

    act(() => {
      toast.show('Sync did not fully complete', 'error', undefined, 'sync', undefined, onReport);
      toast.show('Wrong password', 'error', undefined, 'login');
    });

    expect(screen.getAllByRole('button', { name: 'toast.report_problem' })).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'toast.report_problem' }));

    expect(onReport).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('Sync did not fully complete')).not.toBeInTheDocument();
    expect(screen.getByText('Wrong password')).toBeInTheDocument();
  });
});
