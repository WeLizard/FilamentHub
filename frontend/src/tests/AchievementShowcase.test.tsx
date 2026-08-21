import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AchievementShowcase } from '../components/AchievementShowcase';
import type { AchievementOverview } from '../types/api';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number }) => (
      options?.count === undefined ? key : `${key}:${options.count}`
    ),
  }),
}));

const overview: AchievementOverview = {
  achievements: [
    {
      code: 'first_profile',
      earned_at: '2026-08-20T12:00:00Z',
      category: 'presets',
      rarity: 'common',
      hidden: false,
      source: 'automatic',
    },
  ],
  next_achievements: [
    {
      code: 'preset_publisher_5',
      category: 'presets',
      rarity: 'uncommon',
      current: 3,
      target: 5,
    },
  ],
  newly_earned: ['first_profile'],
  contributor_roles: ['preset_author'],
  published_presets: 3,
  saved_by_other_users: 2,
  confirmed_uses_by_other_users: 1,
};

describe('AchievementShowcase', () => {
  it('shows earned achievements, progress, and acknowledges new awards', () => {
    render(
      <AchievementShowcase
        overview={overview}
        isHeaderVisible
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'profilePage.openAchievements' }));

    expect(screen.getByText('profilePage.nextAchievements')).toBeTruthy();
    expect(screen.getByText('achievement.presetPublisher5.label')).toBeTruthy();
    expect(screen.getByText('3/5')).toBeTruthy();
    expect(screen.getByText('profilePage.earnedAchievements')).toBeTruthy();
    const earnedHeading = screen.getByText('profilePage.earnedAchievements');
    const nextHeading = screen.getByText('profilePage.nextAchievements');
    expect(earnedHeading.compareDocumentPosition(nextHeading) & Node.DOCUMENT_POSITION_FOLLOWING)
      .toBeTruthy();
    expect(screen.getByText('profilePage.newAchievementCount:1')).toBeTruthy();
    expect(screen.getAllByText('achievement.firstProfile.label')).toHaveLength(2);
    expect(screen.queryByText('profilePage.contributorRoles.preset_author')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'common.close' }));
    expect(screen.queryByText('+1')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'profilePage.openAchievements' }));
    expect(screen.queryByText('profilePage.newAchievementCount:1')).toBeNull();
  });
});
