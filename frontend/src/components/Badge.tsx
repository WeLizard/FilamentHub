import React from 'react';
import { useTranslation } from 'react-i18next';
import { Shield, Star, CheckCircle, Zap, User } from 'lucide-react';

export type BadgeType = 'founder' | 'beta_tester' | 'contributor' | 'verified' | 'early_adopter' | 'supporter';

interface BadgeConfig {
  icon: React.ComponentType<{ className?: string }>;
  labelKey: string;
  color: string;
  titleKey: string;
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
