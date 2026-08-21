import { useMemo, useState } from 'react';
import { ChevronRight, Sparkles, Star, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type {
  AchievementCode,
  AchievementOverview,
  AchievementProgress,
  UserAchievement,
} from '../types/api';
import { formatDate } from '../utils/formatDate';
import { ACHIEVEMENT_CONFIG, AchievementBadge } from './Badge';
import { ModalOverlay } from './ModalOverlay';

const PREVIEW_LIMIT = 3;

const NEWCOMER_GOAL_PRIORITY: AchievementCode[] = [
  'spool_collector_1',
  'first_profile',
  'printer_integration_connected',
];

const ACHIEVEMENT_GUIDES: Partial<Record<AchievementCode, string>> = {
  spool_collector_1: '/wiki/articles/spool-on-shelf?start=1&journey=user%3Ashelf&returnTo=%2Fprofile%3Ftab%3Dspools',
  first_profile: '/wiki/articles/orca-preset-guide?start=1&journey=user%3Aslicer&returnTo=%2Fprofile%3Ftab%3Dpresets',
  printer_integration_connected: '/wiki/articles/printer-feed-guide?start=1&journey=user%3Aprinter&returnTo=%2Fprofile%3Ftab%3Dprinter-profiles',
};

const RARITY_STYLES: Record<string, { card: string; chip: string }> = {
  common: {
    card: 'border-white/10 bg-white/[0.045]',
    chip: 'border-white/10 bg-white/5 text-gray-300',
  },
  uncommon: {
    card: 'border-cyan-300/15 bg-cyan-300/[0.055]',
    chip: 'border-cyan-300/20 bg-cyan-300/10 text-cyan-200',
  },
  rare: {
    card: 'border-violet-300/20 bg-violet-300/[0.07]',
    chip: 'border-violet-300/25 bg-violet-300/10 text-violet-200',
  },
  epic: {
    card: 'border-fuchsia-300/25 bg-fuchsia-300/[0.075]',
    chip: 'border-fuchsia-300/30 bg-fuchsia-300/10 text-fuchsia-200',
  },
  historic: {
    card: 'border-amber-300/20 bg-amber-300/[0.065]',
    chip: 'border-amber-300/25 bg-amber-300/10 text-amber-200',
  },
  honor: {
    card: 'border-amber-200/25 bg-amber-200/[0.07]',
    chip: 'border-amber-200/30 bg-amber-200/10 text-amber-100',
  },
  secret: {
    card: 'border-fuchsia-300/20 bg-fuchsia-300/[0.065]',
    chip: 'border-fuchsia-300/25 bg-fuchsia-300/10 text-fuchsia-200',
  },
};

const isAchievementCode = (code: string): code is AchievementCode => (
  Object.prototype.hasOwnProperty.call(ACHIEVEMENT_CONFIG, code)
);

const knownAchievement = (
  achievement: UserAchievement,
): achievement is UserAchievement & { code: AchievementCode } => (
  isAchievementCode(achievement.code)
);

const knownProgress = (
  progress: AchievementProgress,
): progress is AchievementProgress & { code: AchievementCode } => (
  isAchievementCode(progress.code)
);

interface AchievementShowcaseProps {
  overview?: AchievementOverview;
  isHeaderVisible: boolean;
  onAcknowledgeNew?: (codes: AchievementCode[]) => void;
}

export function AchievementShowcase({
  overview,
  isHeaderVisible,
  onAcknowledgeNew,
}: AchievementShowcaseProps) {
  const { t, i18n } = useTranslation();
  const language = (i18n.resolvedLanguage || i18n.language).split('-')[0];
  const [isOpen, setIsOpen] = useState(false);
  const [viewedAchievementCodes, setViewedAchievementCodes] = useState<Set<AchievementCode>>(
    () => new Set(),
  );
  const [openedNewAchievementCodes, setOpenedNewAchievementCodes] = useState<Set<AchievementCode>>(
    () => new Set(),
  );
  const achievements = useMemo(
    () => (overview?.achievements ?? []).filter(knownAchievement),
    [overview?.achievements],
  );
  const nextAchievements = useMemo(() => {
    const priority = new Map(NEWCOMER_GOAL_PRIORITY.map((code, index) => [code, index]));
    return (overview?.next_achievements ?? [])
      .filter(knownProgress)
      .map((progress, sourceIndex) => ({ progress, sourceIndex }))
      .sort((left, right) => {
        const leftRank = priority.get(left.progress.code) ?? Number.MAX_SAFE_INTEGER;
        const rightRank = priority.get(right.progress.code) ?? Number.MAX_SAFE_INTEGER;
        return leftRank - rightRank || left.sourceIndex - right.sourceIndex;
      })
      .map(({ progress }) => progress);
  }, [overview?.next_achievements]);
  const newlyEarned = useMemo(
    () => new Set((overview?.newly_earned ?? []).filter(isAchievementCode)),
    [overview?.newly_earned],
  );
  const unseenAchievementCodes = useMemo(
    () => new Set([...newlyEarned].filter((code) => !viewedAchievementCodes.has(code))),
    [newlyEarned, viewedAchievementCodes],
  );
  const previewAchievements = achievements.slice(0, PREVIEW_LIMIT);
  const totalMarks = achievements.length;
  const openShowcase = () => {
    setOpenedNewAchievementCodes(unseenAchievementCodes);
    setViewedAchievementCodes((current) => new Set([...current, ...unseenAchievementCodes]));
    if (unseenAchievementCodes.size > 0) {
      onAcknowledgeNew?.([...unseenAchievementCodes]);
    }
    setIsOpen(true);
  };

  return (
    <>
      <button
        type="button"
        onClick={openShowcase}
        className="group relative inline-flex max-w-full items-center gap-1 overflow-visible rounded-full border border-white/[0.07] bg-black/[0.14] px-1.5 py-1 text-left shadow-sm shadow-black/10 transition-all duration-200 hover:border-purple-300/20 hover:bg-purple-950/25 hover:shadow-[0_0_22px] hover:shadow-purple-500/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/50"
        aria-label={t('profilePage.openAchievements')}
        title={t('profilePage.openAchievements')}
      >
        <span className="pointer-events-none absolute inset-0 rounded-full bg-gradient-to-r from-purple-400/[0.055] via-pink-400/[0.035] to-cyan-300/[0.025] opacity-20 transition-opacity duration-200 group-hover:opacity-100" />
        {previewAchievements.map((achievement) => (
          <span
            key={achievement.code}
            className="group/badge relative flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-white/[0.06] bg-white/[0.035] opacity-90 transition-opacity group-hover:opacity-100"
            title={t(ACHIEVEMENT_CONFIG[achievement.code].titleKey)}
          >
            <AchievementBadge code={achievement.code} size="sm" />
            <span className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 -translate-x-1/2 translate-y-1 scale-95 whitespace-nowrap rounded-lg border border-white/10 bg-slate-950/95 px-2 py-1 text-[11px] font-medium text-gray-200 opacity-0 shadow-lg shadow-black/30 transition-all duration-150 group-hover/badge:translate-y-0 group-hover/badge:scale-100 group-hover/badge:opacity-100">
              {t(ACHIEVEMENT_CONFIG[achievement.code].labelKey)}
            </span>
          </span>
        ))}
        <span className="relative ml-0.5 flex min-w-0 items-center gap-0.5 border-l border-white/[0.06] pl-1.5 text-[11px] font-medium text-gray-500 transition-colors group-hover:text-gray-300">
          <span>{totalMarks}</span>
          <ChevronRight className="h-3 w-3 shrink-0 transition-transform group-hover:translate-x-0.5" />
        </span>
        {unseenAchievementCodes.size > 0 && (
          <span className="absolute -right-2 -top-2 rounded-full border border-cyan-200/30 bg-cyan-500 px-1.5 py-0.5 text-[10px] font-bold leading-none text-slate-950 shadow-[0_0_14px_rgba(34,211,238,0.55)]">
            +{unseenAchievementCodes.size}
          </span>
        )}
      </button>

      {isOpen && (
        <ModalOverlay onClose={() => setIsOpen(false)}>
          <div
            className={`mx-4 flex w-full max-w-3xl flex-col overflow-hidden rounded-3xl border border-white/15 bg-gradient-to-br from-slate-950 via-purple-950/95 to-slate-950 shadow-[0_28px_100px_rgba(76,29,149,0.38)] ${
              isHeaderVisible ? 'max-h-[calc(100vh-100px)]' : 'max-h-[90vh]'
            }`}
          >
            <div className="relative overflow-hidden border-b border-white/10 px-5 py-5 sm:px-7">
              <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(168,85,247,0.28),transparent_42%),radial-gradient(circle_at_top_right,rgba(34,211,238,0.16),transparent_38%)]" />
              <div className="relative flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <Star className="h-5 w-5 text-amber-300" />
                    <span className="rounded-full border border-white/10 bg-white/8 px-2.5 py-1 text-xs font-semibold text-purple-100">
                      {t('profilePage.achievementCount', { count: achievements.length })}
                    </span>
                    {openedNewAchievementCodes.size > 0 && (
                      <span className="rounded-full border border-cyan-200/20 bg-cyan-300/10 px-2.5 py-1 text-xs font-semibold text-cyan-100">
                        {t('profilePage.newAchievementCount', { count: openedNewAchievementCodes.size })}
                      </span>
                    )}
                  </div>
                  <h2 className="text-xl font-bold text-white sm:text-2xl">
                    {t('profilePage.achievements')}
                  </h2>
                  <p className="mt-1 max-w-2xl text-sm leading-6 text-gray-300">
                    {t('profilePage.achievementsDescription')}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setIsOpen(false)}
                  className="shrink-0 rounded-xl p-2 text-gray-400 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/70"
                  aria-label={t('common.close')}
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>

            <div className="space-y-6 overflow-y-auto p-5 sm:p-7">
              <section>
                <h3 className="mb-3 font-semibold text-white">
                  {t('profilePage.earnedAchievements')}
                </h3>
                {achievements.length > 0 ? (
                  <div className="grid gap-3 sm:grid-cols-2">
                    {achievements.map((achievement) => {
                      const config = ACHIEVEMENT_CONFIG[achievement.code];
                      const rarity = RARITY_STYLES[achievement.rarity] ?? RARITY_STYLES.common;
                      return (
                        <article
                          key={achievement.code}
                          className={`group flex min-w-0 items-center gap-4 rounded-2xl border p-4 ${rarity.card} ${
                            openedNewAchievementCodes.has(achievement.code)
                              ? 'ring-1 ring-cyan-300/45 shadow-[0_0_24px_rgba(34,211,238,0.12)]'
                              : ''
                          }`}
                        >
                          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl border border-white/10 bg-black/25 shadow-[0_0_24px_rgba(34,211,238,0.12)]">
                            <AchievementBadge code={achievement.code} size="lg" showArtwork />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <h4 className="font-semibold text-white">{t(config.labelKey)}</h4>
                              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${rarity.chip}`}>
                                {t(`profilePage.achievementRarity.${achievement.rarity}`)}
                              </span>
                            </div>
                            <p className="mt-1 text-sm leading-5 text-gray-300">{t(config.titleKey)}</p>
                            <p className="mt-1 text-xs text-gray-500">{formatDate(achievement.earned_at)}</p>
                          </div>
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <p className="rounded-2xl border border-white/10 bg-black/15 p-4 text-sm text-gray-400">
                    {t('profilePage.noAchievementsYet')}
                  </p>
                )}
              </section>

              {nextAchievements.length > 0 && (
                <section>
                  <div className="mb-3 flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-cyan-300" />
                    <h3 className="font-semibold text-white">
                      {t('profilePage.nextAchievements')}
                    </h3>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {nextAchievements.map((progress) => {
                      const config = ACHIEVEMENT_CONFIG[progress.code];
                      const guideTo = ACHIEVEMENT_GUIDES[progress.code]
                        ? language === 'ru'
                          ? ACHIEVEMENT_GUIDES[progress.code]
                          : '/wiki'
                        : undefined;
                      const ratio = Math.min(100, Math.round((progress.current / progress.target) * 100));
                      return (
                        <div
                          key={progress.code}
                          className="flex min-w-0 items-center gap-3 rounded-2xl border border-white/10 bg-black/15 p-3"
                        >
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] grayscale opacity-70">
                            <AchievementBadge code={progress.code} size="md" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center justify-between gap-2">
                              <p className="truncate text-sm font-semibold text-gray-100">
                                {t(config.labelKey)}
                              </p>
                              <span className="shrink-0 text-xs tabular-nums text-gray-400">
                                {progress.current}/{progress.target}
                              </span>
                            </div>
                            <p className="mt-0.5 line-clamp-2 text-xs leading-4 text-gray-400">
                              {t(config.titleKey)}
                            </p>
                            {guideTo && (
                              <Link
                                to={guideTo}
                                className="mt-1 inline-flex items-center gap-1 text-[11px] font-medium text-cyan-300 transition hover:text-cyan-200"
                              >
                                {t('profilePage.newcomer.howTo')}
                                <ChevronRight className="h-3 w-3" />
                              </Link>
                            )}
                            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/8">
                              <div
                                className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-violet-400 transition-[width]"
                                style={{ width: `${ratio}%` }}
                              />
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}

              {overview && (
                <section className="grid grid-cols-1 gap-2 rounded-2xl border border-white/10 bg-black/15 p-4 sm:grid-cols-3">
                  <div>
                    <p className="text-xl font-bold text-white">{overview.published_presets}</p>
                    <p className="text-xs text-gray-400">{t('profilePage.contributionStats.publishedPresets')}</p>
                  </div>
                  <div>
                    <p className="text-xl font-bold text-white">{overview.saved_by_other_users}</p>
                    <p className="text-xs text-gray-400">{t('profilePage.contributionStats.savedByOthers')}</p>
                  </div>
                  <div>
                    <p className="text-xl font-bold text-white">{overview.confirmed_uses_by_other_users}</p>
                    <p className="text-xs text-gray-400">{t('profilePage.contributionStats.confirmedUses')}</p>
                  </div>
                </section>
              )}
            </div>
          </div>
        </ModalOverlay>
      )}
    </>
  );
}
