import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../hooks/usePluginDeveloperMode', () => ({
  usePluginDeveloperMode: () => false,
}));

vi.mock('../utils/pluginBridge', () => ({
  requestPluginProfileSync: vi.fn(),
  requestPluginRecovery: vi.fn(),
}));

vi.mock('../utils/problemReport', () => ({ openProblemReport: vi.fn() }));

import { OrcaPluginToolbar } from './OrcaPluginToolbar';

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}${location.hash}`}</output>;
}

function renderToolbar(initialEntry: string) {
  render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <OrcaPluginToolbar
        authenticated
        accountLabel="account"
        onLogin={vi.fn()}
        onLogout={vi.fn()}
      />
      <LocationProbe />
    </MemoryRouter>,
  );
}

describe('OrcaPluginToolbar inventory navigation', () => {
  it('places My Spools first and preserves the plugin bridge hash when opening the inventory', () => {
    renderToolbar('/wiki/articles/example?source=plugin&lng=ru#bridge-session=abc123');

    const accountGroup = screen.getByTestId('orca-plugin-account-group');
    const firstDestination = accountGroup.nextElementSibling;
    expect(firstDestination).toHaveTextContent('layout.plugin_nav_spools');

    fireEvent.click(screen.getByRole('button', { name: 'layout.plugin_nav_spools' }));

    expect(screen.getByTestId('location')).toHaveTextContent(
      '/embed?tab=spools&lng=ru#bridge-session=abc123',
    );
  });

  it('preserves the bridge hash when navigating to a deep link in another plugin section', () => {
    renderToolbar('/profile?tab=presets#bridge-session=abc123');

    fireEvent.click(screen.getByRole('button', { name: 'layout.nav_wiki' }));

    expect(screen.getByTestId('location')).toHaveTextContent('/wiki#bridge-session=abc123');
  });

  it('marks the profile destination as active after its tab query is consumed', () => {
    renderToolbar('/profile?tab=spools&lng=ru#bridge-session=abc123');

    expect(screen.getByRole('button', { name: 'layout.nav_profile' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('button', { name: 'layout.plugin_nav_spools' })).not.toHaveAttribute(
      'aria-current',
    );
  });

  it('marks the default plugin inventory route as the active first destination', () => {
    renderToolbar('/embed#bridge-session=abc123');

    expect(screen.getByRole('button', { name: 'layout.plugin_nav_spools' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('button', { name: 'layout.nav_catalog' })).not.toHaveAttribute(
      'aria-current',
    );
  });

  it('keeps catalog reachable by selecting its explicit plugin destination', () => {
    renderToolbar('/profile?tab=spools&lng=ru#bridge-session=abc123');

    fireEvent.click(screen.getByRole('button', { name: 'layout.nav_catalog' }));

    expect(screen.getByTestId('location')).toHaveTextContent(
      '/embed/catalog?lng=ru#bridge-session=abc123',
    );
  });
});
