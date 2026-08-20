import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  BookOpen,
  CheckCircle,
  HeartHandshake,
  Medal,
  PackageOpen,
  Rabbit,
  Shield,
  SlidersHorizontal,
  Sparkles,
  Star,
  User,
  Users,
  Warehouse,
  Wrench,
  Zap,
} from 'lucide-react';
import type { AchievementCode } from '../types/api';

export type BadgeType = 'founder' | 'beta_tester' | 'contributor' | 'verified' | 'early_adopter' | 'supporter';

export interface BadgeConfig {
  icon: React.ComponentType<{ className?: string }>;
  labelKey: string;
  color: string;
  titleKey: string;
  artworkSrc?: string;
}

export const BADGE_CONFIG: Record<BadgeType, BadgeConfig> = {
  founder: {
    icon: Star,
    labelKey: 'badge.founder.label',
    color: 'text-amber-500',
    titleKey: 'badge.founder.title',
  },
  beta_tester: {
    icon: Shield,
    labelKey: 'badge.betaTester.label',
    color: 'text-blue-500',
    titleKey: 'badge.betaTester.title',
  },
  contributor: {
    icon: User,
    labelKey: 'badge.contributor.label',
    color: 'text-purple-500',
    titleKey: 'badge.contributor.title',
  },
  verified: {
    icon: CheckCircle,
    labelKey: 'badge.verified.label',
    color: 'text-green-500',
    titleKey: 'badge.verified.title',
  },
  early_adopter: {
    icon: Zap,
    labelKey: 'badge.earlyAdopter.label',
    color: 'text-orange-500',
    titleKey: 'badge.earlyAdopter.title',
  },
  supporter: {
    icon: CheckCircle,
    labelKey: 'badge.supporter.label',
    color: 'text-pink-500',
    titleKey: 'badge.supporter.title',
  },
};

export const ACHIEVEMENT_CONFIG: Record<AchievementCode, BadgeConfig> = {
  first_hundred: {
    icon: Medal,
    labelKey: 'achievement.firstHundred.label',
    color: 'text-amber-300',
    titleKey: 'achievement.firstHundred.title',
  },
  first_catalog_contribution: {
    icon: Sparkles,
    labelKey: 'achievement.firstCatalogContribution.label',
    color: 'text-cyan-300',
    titleKey: 'achievement.firstCatalogContribution.title',
  },
  first_profile: {
    icon: SlidersHorizontal,
    labelKey: 'achievement.firstProfile.label',
    color: 'text-purple-300',
    titleKey: 'achievement.firstProfile.title',
  },
  preset_publisher_5: {
    icon: Wrench,
    labelKey: 'achievement.presetPublisher5.label',
    color: 'text-violet-300',
    titleKey: 'achievement.presetPublisher5.title',
  },
  preset_used_by_another: {
    icon: Users,
    labelKey: 'achievement.presetUsedByAnother.label',
    color: 'text-emerald-300',
    titleKey: 'achievement.presetUsedByAnother.title',
  },
  presets_used_by_10: {
    icon: HeartHandshake,
    labelKey: 'achievement.presetsUsedBy10.label',
    color: 'text-emerald-300',
    titleKey: 'achievement.presetsUsedBy10.title',
  },
  spool_collector_20: {
    icon: PackageOpen,
    labelKey: 'achievement.spoolCollector20.label',
    color: 'text-sky-300',
    titleKey: 'achievement.spoolCollector20.title',
  },
  spool_collector_100: {
    icon: Warehouse,
    labelKey: 'achievement.spoolCollector100.label',
    color: 'text-fuchsia-300',
    titleKey: 'achievement.spoolCollector100.title',
  },
  happy_hare_connected: {
    icon: Rabbit,
    labelKey: 'achievement.happyHareConnected.label',
    color: 'text-teal-300',
    titleKey: 'achievement.happyHareConnected.title',
  },
  first_wiki_article: {
    icon: BookOpen,
    labelKey: 'achievement.firstWikiArticle.label',
    color: 'text-blue-300',
    titleKey: 'achievement.firstWikiArticle.title',
  },
};

export const AchievementBadge: React.FC<{
  code: AchievementCode;
  size?: 'sm' | 'md' | 'lg';
}> = ({ code, size = 'md' }) => {
  const { t } = useTranslation();
  const [artworkFailed, setArtworkFailed] = useState(false);
  const config = ACHIEVEMENT_CONFIG[code];
  const Icon = config.icon;
  const sizeClasses = { sm: 'h-4 w-4', md: 'h-5 w-5', lg: 'h-6 w-6' };
  return (
    <span className="inline-flex items-center" title={t(config.titleKey)}>
      {config.artworkSrc && !artworkFailed ? (
        <img
          src={config.artworkSrc}
          alt=""
          className={`${sizeClasses[size]} rounded-sm object-cover`}
          onError={() => setArtworkFailed(true)}
        />
      ) : (
        <Icon className={`${sizeClasses[size]} ${config.color}`} />
      )}
    </span>
  );
};

interface BadgeProps {
  type: BadgeType;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  type,
  size = 'md',
  showLabel = false,
  className
}) => {
  const { t } = useTranslation();
  const config = BADGE_CONFIG[type];

  if (!config) {
    return null;
  }

  const Icon = config.icon;

  const sizeClasses = {
    sm: 'h-4 w-4',
    md: 'h-5 w-5',
    lg: 'h-6 w-6',
  };

  return (
    <span
      className={`inline-flex items-center ${className || ''}`}
      title={t(config.titleKey)}
    >
      <Icon className={`${sizeClasses[size]} ${config.color}`} />
      {showLabel && <span className="ml-1">{t(config.labelKey)}</span>}
    </span>
  );
};

interface BadgeListProps {
  badges: BadgeType[];
  size?: 'sm' | 'md' | 'lg';
  showLabels?: boolean;
  className?: string;
}

export const BadgeList: React.FC<BadgeListProps> = ({ 
  badges, 
  size = 'md', 
  showLabels = false,
  className 
}) => {
  if (!badges || badges.length === 0) {
    return null;
  }

  return (
    <div className={`flex flex-wrap items-center gap-1.5 ${className || ''}`}>
      {badges.map((badge) => (
        <Badge 
          key={badge} 
          type={badge} 
          size={size} 
          showLabel={showLabels}
        />
      ))}
    </div>
  );
};
