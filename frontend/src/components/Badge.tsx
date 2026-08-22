import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  BookOpen,
  Cable,
  Calculator,
  CheckCircle,
  Factory,
  Handshake,
  HeartHandshake,
  Layers3,
  Medal,
  PackageCheck,
  PackageOpen,
  PawPrint,
  Rabbit,
  Repeat2,
  Route,
  Send,
  Shield,
  SlidersHorizontal,
  Sparkles,
  Star,
  User,
  Users,
  Warehouse,
  Workflow,
  Wrench,
  Zap,
} from 'lucide-react';
import type { AchievementCode } from '../types/api';

export interface BadgeConfig {
  icon: React.ComponentType<{ className?: string }>;
  labelKey: string;
  color: string;
  titleKey: string;
  artworkSrc?: string;
  artworkFrameSrc?: string;
}

const ACHIEVEMENT_FRAME_VERSION = '20260822-glow-1';

const achievementArtwork = (code: string, rarity: string) => ({
  artworkSrc: `/achievements/artwork/${code}.webp`,
  artworkFrameSrc: `/achievements/frames/${rarity}.svg?v=${ACHIEVEMENT_FRAME_VERSION}`,
});

export const ACHIEVEMENT_CONFIG: Record<AchievementCode, BadgeConfig> = {
  project_founder: {
    icon: Star,
    labelKey: 'achievement.projectFounder.label',
    color: 'text-amber-300',
    titleKey: 'achievement.projectFounder.title',
    ...achievementArtwork('project_founder', 'historic'),
  },
  beta_tester: {
    icon: Shield,
    labelKey: 'achievement.betaTester.label',
    color: 'text-blue-300',
    titleKey: 'achievement.betaTester.title',
    ...achievementArtwork('beta_tester', 'honor'),
  },
  project_contributor: {
    icon: User,
    labelKey: 'achievement.projectContributor.label',
    color: 'text-purple-300',
    titleKey: 'achievement.projectContributor.title',
    ...achievementArtwork('project_contributor', 'honor'),
  },
  early_adopter: {
    icon: Zap,
    labelKey: 'achievement.earlyAdopter.label',
    color: 'text-orange-300',
    titleKey: 'achievement.earlyAdopter.title',
    ...achievementArtwork('early_adopter', 'historic'),
  },
  project_supporter: {
    icon: CheckCircle,
    labelKey: 'achievement.projectSupporter.label',
    color: 'text-pink-300',
    titleKey: 'achievement.projectSupporter.title',
    ...achievementArtwork('project_supporter', 'honor'),
  },
  first_hundred: {
    icon: Medal,
    labelKey: 'achievement.firstHundred.label',
    color: 'text-amber-300',
    titleKey: 'achievement.firstHundred.title',
    ...achievementArtwork('first_hundred', 'historic'),
  },
  first_catalog_contribution: {
    icon: Sparkles,
    labelKey: 'achievement.firstCatalogContribution.label',
    color: 'text-cyan-300',
    titleKey: 'achievement.firstCatalogContribution.title',
    ...achievementArtwork('first_catalog_contribution', 'common'),
  },
  first_profile: {
    icon: SlidersHorizontal,
    labelKey: 'achievement.firstProfile.label',
    color: 'text-purple-300',
    titleKey: 'achievement.firstProfile.title',
    ...achievementArtwork('first_profile', 'common'),
  },
  preset_publisher_5: {
    icon: Wrench,
    labelKey: 'achievement.presetPublisher5.label',
    color: 'text-violet-300',
    titleKey: 'achievement.presetPublisher5.title',
    ...achievementArtwork('preset_publisher_5', 'uncommon'),
  },
  preset_publisher_20: {
    icon: Wrench,
    labelKey: 'achievement.presetPublisher20.label',
    color: 'text-violet-300',
    titleKey: 'achievement.presetPublisher20.title',
    ...achievementArtwork('preset_publisher_20', 'rare'),
  },
  preset_publisher_50: {
    icon: Medal,
    labelKey: 'achievement.presetPublisher50.label',
    color: 'text-fuchsia-300',
    titleKey: 'achievement.presetPublisher50.title',
    ...achievementArtwork('preset_publisher_50', 'epic'),
  },
  preset_used_by_another: {
    icon: Users,
    labelKey: 'achievement.presetUsedByAnother.label',
    color: 'text-emerald-300',
    titleKey: 'achievement.presetUsedByAnother.title',
    ...achievementArtwork('preset_used_by_another', 'uncommon'),
  },
  presets_used_by_3: {
    icon: Users,
    labelKey: 'achievement.presetsUsedBy3.label',
    color: 'text-emerald-300',
    titleKey: 'achievement.presetsUsedBy3.title',
    ...achievementArtwork('presets_used_by_3', 'uncommon'),
  },
  presets_used_by_10: {
    icon: HeartHandshake,
    labelKey: 'achievement.presetsUsedBy10.label',
    color: 'text-emerald-300',
    titleKey: 'achievement.presetsUsedBy10.title',
    ...achievementArtwork('presets_used_by_10', 'rare'),
  },
  preset_confirmed_by_author: {
    icon: CheckCircle,
    labelKey: 'achievement.presetConfirmedByAuthor.label',
    color: 'text-green-300',
    titleKey: 'achievement.presetConfirmedByAuthor.title',
    ...achievementArtwork('preset_confirmed_by_author', 'common'),
  },
  preset_material_types_5: {
    icon: Sparkles,
    labelKey: 'achievement.presetMaterialTypes5.label',
    color: 'text-lime-300',
    titleKey: 'achievement.presetMaterialTypes5.title',
    ...achievementArtwork('preset_material_types_5', 'rare'),
  },
  spool_collector_1: {
    icon: PackageOpen,
    labelKey: 'achievement.spoolCollector1.label',
    color: 'text-sky-300',
    titleKey: 'achievement.spoolCollector1.title',
    ...achievementArtwork('spool_collector_1', 'common'),
  },
  spool_collector_20: {
    icon: PackageOpen,
    labelKey: 'achievement.spoolCollector20.label',
    color: 'text-sky-300',
    titleKey: 'achievement.spoolCollector20.title',
    ...achievementArtwork('spool_collector_20', 'uncommon'),
  },
  spool_collector_100: {
    icon: Warehouse,
    labelKey: 'achievement.spoolCollector100.label',
    color: 'text-fuchsia-300',
    titleKey: 'achievement.spoolCollector100.title',
    ...achievementArtwork('spool_collector_100', 'secret'),
  },
  material_system_connected: {
    icon: SlidersHorizontal,
    labelKey: 'achievement.materialSystemConnected.label',
    color: 'text-cyan-300',
    titleKey: 'achievement.materialSystemConnected.title',
    ...achievementArtwork('material_system_connected', 'common'),
  },
  happy_hare_connected: {
    icon: Rabbit,
    labelKey: 'achievement.happyHareConnected.label',
    color: 'text-teal-300',
    titleKey: 'achievement.happyHareConnected.title',
    ...achievementArtwork('happy_hare_connected', 'secret'),
  },
  printer_integration_connected: {
    icon: Zap,
    labelKey: 'achievement.printerIntegrationConnected.label',
    color: 'text-teal-300',
    titleKey: 'achievement.printerIntegrationConnected.title',
    ...achievementArtwork('printer_integration_connected', 'uncommon'),
  },
  octoprint_connected: {
    icon: Cable,
    labelKey: 'achievement.octoprintConnected.label',
    color: 'text-fuchsia-300',
    titleKey: 'achievement.octoprintConnected.title',
    ...achievementArtwork('octoprint_connected', 'secret'),
  },
  bambu_connected: {
    icon: PawPrint,
    labelKey: 'achievement.bambuConnected.label',
    color: 'text-emerald-300',
    titleKey: 'achievement.bambuConnected.title',
    ...achievementArtwork('bambu_connected', 'secret'),
  },
  automatic_spool_assignment: {
    icon: Wrench,
    labelKey: 'achievement.automaticSpoolAssignment.label',
    color: 'text-indigo-300',
    titleKey: 'achievement.automaticSpoolAssignment.title',
    ...achievementArtwork('automatic_spool_assignment', 'uncommon'),
  },
  full_material_system: {
    icon: Warehouse,
    labelKey: 'achievement.fullMaterialSystem.label',
    color: 'text-fuchsia-300',
    titleKey: 'achievement.fullMaterialSystem.title',
    ...achievementArtwork('full_material_system', 'secret'),
  },
  spool_depleted_by_print: {
    icon: CheckCircle,
    labelKey: 'achievement.spoolDepletedByPrint.label',
    color: 'text-amber-300',
    titleKey: 'achievement.spoolDepletedByPrint.title',
    ...achievementArtwork('spool_depleted_by_print', 'secret'),
  },
  first_wiki_article: {
    icon: BookOpen,
    labelKey: 'achievement.firstWikiArticle.label',
    color: 'text-blue-300',
    titleKey: 'achievement.firstWikiArticle.title',
    ...achievementArtwork('first_wiki_article', 'common'),
  },
  first_wiki_revision: {
    icon: BookOpen,
    labelKey: 'achievement.firstWikiRevision.label',
    color: 'text-blue-300',
    titleKey: 'achievement.firstWikiRevision.title',
    ...achievementArtwork('first_wiki_revision', 'common'),
  },
  wiki_editor_5: {
    icon: BookOpen,
    labelKey: 'achievement.wikiEditor5.label',
    color: 'text-indigo-300',
    titleKey: 'achievement.wikiEditor5.title',
    ...achievementArtwork('wiki_editor_5', 'uncommon'),
  },
  printer_learning_path: {
    icon: Route,
    labelKey: 'achievement.printerLearningPath.label',
    color: 'text-cyan-300',
    titleKey: 'achievement.printerLearningPath.title',
    ...achievementArtwork('printer_learning_path', 'uncommon'),
  },
  manufacturer_learning_path: {
    icon: Factory,
    labelKey: 'achievement.manufacturerLearningPath.label',
    color: 'text-violet-300',
    titleKey: 'achievement.manufacturerLearningPath.title',
    ...achievementArtwork('manufacturer_learning_path', 'uncommon'),
  },
  first_saved_calculation: {
    icon: Calculator,
    labelKey: 'achievement.firstSavedCalculation.label',
    color: 'text-cyan-300',
    titleKey: 'achievement.firstSavedCalculation.title',
    ...achievementArtwork('first_saved_calculation', 'common'),
  },
  gcode_calculation: {
    icon: Layers3,
    labelKey: 'achievement.gcodeCalculation.label',
    color: 'text-indigo-300',
    titleKey: 'achievement.gcodeCalculation.title',
    ...achievementArtwork('gcode_calculation', 'uncommon'),
  },
  first_quote_sent: {
    icon: Send,
    labelKey: 'achievement.firstQuoteSent.label',
    color: 'text-sky-300',
    titleKey: 'achievement.firstQuoteSent.title',
    ...achievementArtwork('first_quote_sent', 'common'),
  },
  first_quote_accepted: {
    icon: Handshake,
    labelKey: 'achievement.firstQuoteAccepted.label',
    color: 'text-emerald-300',
    titleKey: 'achievement.firstQuoteAccepted.title',
    ...achievementArtwork('first_quote_accepted', 'uncommon'),
  },
  first_order_completed: {
    icon: PackageCheck,
    labelKey: 'achievement.firstOrderCompleted.label',
    color: 'text-green-300',
    titleKey: 'achievement.firstOrderCompleted.title',
    ...achievementArtwork('first_order_completed', 'uncommon'),
  },
  returning_customer: {
    icon: Repeat2,
    labelKey: 'achievement.returningCustomer.label',
    color: 'text-violet-300',
    titleKey: 'achievement.returningCustomer.title',
    ...achievementArtwork('returning_customer', 'rare'),
  },
  full_business_cycle: {
    icon: Workflow,
    labelKey: 'achievement.fullBusinessCycle.label',
    color: 'text-fuchsia-300',
    titleKey: 'achievement.fullBusinessCycle.title',
    ...achievementArtwork('full_business_cycle', 'rare'),
  },
  material_to_print: {
    icon: Factory,
    labelKey: 'achievement.materialToPrint.label',
    color: 'text-amber-300',
    titleKey: 'achievement.materialToPrint.title',
    ...achievementArtwork('material_to_print', 'epic'),
  },
};

export const AchievementBadge: React.FC<{
  code: AchievementCode;
  size?: 'sm' | 'md' | 'lg';
  showArtwork?: boolean;
}> = ({ code, size = 'md', showArtwork = false }) => {
  const { t } = useTranslation();
  const [artworkFailed, setArtworkFailed] = useState(false);
  const config = ACHIEVEMENT_CONFIG[code];
  const Icon = config.icon;
  const sizeClasses = { sm: 'h-4 w-4', md: 'h-5 w-5', lg: 'h-6 w-6' };
  return (
    <span
      className={`inline-flex items-center ${showArtwork && config.artworkSrc ? 'h-full w-full' : ''}`}
      title={t(config.titleKey)}
    >
      {showArtwork && config.artworkSrc && !artworkFailed ? (
        <span className="relative block h-full w-full">
          <img
            src={config.artworkSrc}
            alt=""
            className="absolute inset-0 h-full w-full object-cover"
            style={{ clipPath: 'inset(5.75% round 12%)' }}
            onError={() => setArtworkFailed(true)}
          />
          {config.artworkFrameSrc && (
            <img
              src={config.artworkFrameSrc}
              alt=""
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 h-full w-full object-contain"
            />
          )}
        </span>
      ) : (
        <Icon className={`${sizeClasses[size]} ${config.color}`} />
      )}
    </span>
  );
};
