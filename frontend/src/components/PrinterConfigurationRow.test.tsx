import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { PrinterConfigurationRow } from './PrinterConfigurationRow';
import type { PrintProfile, PrinterProfile } from '../types/api';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: { count?: number }) =>
      values?.count == null ? key : `${key}:${values.count}`,
  }),
}));

describe('PrinterConfigurationRow process profiles', () => {
  it('opens the assigned process profiles and exposes their existing actions', () => {
    const configuration = {
      id: 11,
      name: 'Voron 0.4',
      nozzle_diameters: [0.4],
    } as PrinterProfile;
    const process = {
      id: 22,
      name: '0.20 mm Quality',
      owner_user_id: 7,
      is_official: false,
      layer_height_mm: 0.2,
      quality_tier: 'optimal',
    } as PrintProfile;
    const onEditPrintProfile = vi.fn();
    const onCreatePrintProfile = vi.fn();

    render(
      <PrinterConfigurationRow
        profile={configuration}
        printProfiles={[{ profile: process, exact: true }]}
        currentUserId={7}
        onEditPrintProfile={onEditPrintProfile}
        onCreatePrintProfile={onCreatePrintProfile}
      />,
    );

    expect(screen.queryByText(process.name)).toBeNull();
    fireEvent.click(
      screen.getByRole('button', { name: 'profilePage.printProfilesCount:1' }),
    );

    expect(screen.getByText(process.name)).toBeInTheDocument();
    fireEvent.click(screen.getByTitle('profilePage.edit'));
    expect(onEditPrintProfile).toHaveBeenCalledWith(process, configuration);

    fireEvent.click(
      screen.getByRole('button', { name: 'profilePage.addPrintProfile' }),
    );
    expect(onCreatePrintProfile).toHaveBeenCalledWith(configuration);
  });

  it('compacts only a redundant machine name and keeps configuration actions', () => {
    const configuration = {
      id: 33,
      name: 'Voron 2.4 350 0.4 nozzle',
      nozzle_diameters: [0.4],
      owner_user_id: 7,
      is_official: false,
    } as PrinterProfile;
    const onView = vi.fn();
    const onEdit = vi.fn();

    render(
      <PrinterConfigurationRow
        profile={configuration}
        physicalPrinterName="Voron 2.4 350"
        printProfiles={[]}
        currentUserId={7}
        onView={onView}
        onEdit={onEdit}
      />,
    );

    expect(screen.getByText('profilePage.nozzles: 0.4 profilePage.mm')).toHaveAttribute(
      'title',
      configuration.name,
    );
    expect(screen.queryByText(configuration.name)).toBeNull();

    fireEvent.click(screen.getByTitle('profilePage.view'));
    fireEvent.click(screen.getByTitle('profilePage.edit'));
    expect(onView).toHaveBeenCalledWith(configuration);
    expect(onEdit).toHaveBeenCalledWith(configuration);
  });
});
