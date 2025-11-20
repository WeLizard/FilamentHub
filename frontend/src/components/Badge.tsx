import React from 'react';
import { Shield, Star, CheckCircle, Zap, User } from 'lucide-react';

export type BadgeType = 'founder' | 'beta_tester' | 'contributor' | 'verified' | 'early_adopter' | 'supporter';

interface BadgeConfig {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  color: string;
  title: string;
}

const BADGE_CONFIG: Record<BadgeType, BadgeConfig> = {
  founder: {
    icon: Star,
    label: 'Founder',
    color: 'text-amber-500',
    title: 'Основатель проекта',
  },
  beta_tester: {
    icon: Shield,
    label: 'Beta Tester',
    color: 'text-blue-500',
    title: 'Бета-тестер',
  },
  contributor: {
    icon: User,
    label: 'Contributor',
    color: 'text-purple-500',
    title: 'Контрибьютор',
  },
  verified: {
    icon: CheckCircle,
    label: 'Verified',
    color: 'text-green-500',
    title: 'Верифицированный производитель',
  },
  early_adopter: {
    icon: Zap,
    label: 'Early Adopter',
    color: 'text-orange-500',
    title: 'Ранний последователь',
  },
  supporter: {
    icon: CheckCircle,
    label: 'Supporter',
    color: 'text-pink-500',
    title: 'Поддержал проект',
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
      title={config.title}
    >
      <Icon className={`${sizeClasses[size]} ${config.color}`} />
      {showLabel && <span className="ml-1">{config.label}</span>}
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
