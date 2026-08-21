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
}

export const ACHIEVEMENT_CONFIG: Record<AchievementCode, BadgeConfig> = {
  project_founder: {
    icon: Star,
    labelKey: 'achievement.projectFounder.label',
    color: 'text-amber-300',
    titleKey: 'achievement.projectFounder.title',
  },
  beta_tester: {
    icon: Shield,
    labelKey: 'achievement.betaTester.label',
    color: 'text-blue-300',
    titleKey: 'achievement.betaTester.title',
  },
  project_contributor: {
    icon: User,
    labelKey: 'achievement.projectContributor.label',
    color: 'text-purple-300',
    titleKey: 'achievement.projectContributor.title',
  },
  early_adopter: {
    icon: Zap,
    labelKey: 'achievement.earlyAdopter.label',
    color: 'text-orange-300',
    titleKey: 'achievement.earlyAdopter.title',
  },
  project_supporter: {
    icon: CheckCircle,
    labelKey: 'achievement.projectSupporter.label',
    color: 'text-pink-300',
    titleKey: 'achievement.projectSupporter.title',
  },
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
  preset_publisher_20: {
    icon: Wrench,
    labelKey: 'achievement.presetPublisher20.label',
    color: 'text-violet-300',
    titleKey: 'achievement.presetPublisher20.title',
  },
  preset_publisher_50: {
    icon: Medal,
    labelKey: 'achievement.presetPublisher50.label',
    color: 'text-fuchsia-300',
    titleKey: 'achievement.presetPublisher50.title',
  },
  preset_used_by_another: {
    icon: Users,
    labelKey: 'achievement.presetUsedByAnother.label',
    color: 'text-emerald-300',
    titleKey: 'achievement.presetUsedByAnother.title',
  },
  presets_used_by_3: {
    icon: Users,
    labelKey: 'achievement.presetsUsedBy3.label',
    color: 'text-emerald-300',
    titleKey: 'achievement.presetsUsedBy3.title',
  },
  presets_used_by_10: {
    icon: HeartHandshake,
    labelKey: 'achievement.presetsUsedBy10.label',
    color: 'text-emerald-300',
    titleKey: 'achievement.presetsUsedBy10.title',
  },
  preset_confirmed_by_author: {
    icon: CheckCircle,
    labelKey: 'achievement.presetConfirmedByAuthor.label',
    color: 'text-green-300',
    titleKey: 'achievement.presetConfirmedByAuthor.title',
  },
  preset_material_types_5: {
    icon: Sparkles,
    labelKey: 'achievement.presetMaterialTypes5.label',
    color: 'text-lime-300',
    titleKey: 'achievement.presetMaterialTypes5.title',
  },
  spool_collector_1: {
    icon: PackageOpen,
    labelKey: 'achievement.spoolCollector1.label',
    color: 'text-sky-300',
    titleKey: 'achievement.spoolCollector1.title',
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
  material_system_connected: {
    icon: SlidersHorizontal,
    labelKey: 'achievement.materialSystemConnected.label',
    color: 'text-cyan-300',
    titleKey: 'achievement.materialSystemConnected.title',
  },
  happy_hare_connected: {
    icon: Rabbit,
    labelKey: 'achievement.happyHareConnected.label',
    color: 'text-teal-300',
    titleKey: 'achievement.happyHareConnected.title',
  },
  printer_integration_connected: {
    icon: Zap,
    labelKey: 'achievement.printerIntegrationConnected.label',
    color: 'text-teal-300',
    titleKey: 'achievement.printerIntegrationConnected.title',
  },
  octoprint_connected: {
    icon: Cable,
    labelKey: 'achievement.octoprintConnected.label',
    color: 'text-fuchsia-300',
    titleKey: 'achievement.octoprintConnected.title',
  },
  bambu_connected: {
    icon: PawPrint,
    labelKey: 'achievement.bambuConnected.label',
    color: 'text-emerald-300',
    titleKey: 'achievement.bambuConnected.title',
  },
  automatic_spool_assignment: {
    icon: Wrench,
    labelKey: 'achievement.automaticSpoolAssignment.label',
    color: 'text-indigo-300',
    titleKey: 'achievement.automaticSpoolAssignment.title',
  },
  full_material_system: {
    icon: Warehouse,
    labelKey: 'achievement.fullMaterialSystem.label',
    color: 'text-fuchsia-300',
    titleKey: 'achievement.fullMaterialSystem.title',
  },
  spool_depleted_by_print: {
    icon: CheckCircle,
    labelKey: 'achievement.spoolDepletedByPrint.label',
    color: 'text-amber-300',
    titleKey: 'achievement.spoolDepletedByPrint.title',
  },
  first_wiki_article: {
    icon: BookOpen,
    labelKey: 'achievement.firstWikiArticle.label',
    color: 'text-blue-300',
    titleKey: 'achievement.firstWikiArticle.title',
  },
  first_wiki_revision: {
    icon: BookOpen,
    labelKey: 'achievement.firstWikiRevision.label',
    color: 'text-blue-300',
    titleKey: 'achievement.firstWikiRevision.title',
  },
  wiki_editor_5: {
    icon: BookOpen,
    labelKey: 'achievement.wikiEditor5.label',
    color: 'text-indigo-300',
    titleKey: 'achievement.wikiEditor5.title',
  },
  first_saved_calculation: {
    icon: Calculator,
    labelKey: 'achievement.firstSavedCalculation.label',
    color: 'text-cyan-300',
    titleKey: 'achievement.firstSavedCalculation.title',
  },
  gcode_calculation: {
    icon: Layers3,
    labelKey: 'achievement.gcodeCalculation.label',
    color: 'text-indigo-300',
    titleKey: 'achievement.gcodeCalculation.title',
  },
  first_quote_sent: {
    icon: Send,
    labelKey: 'achievement.firstQuoteSent.label',
    color: 'text-sky-300',
    titleKey: 'achievement.firstQuoteSent.title',
  },
  first_quote_accepted: {
    icon: Handshake,
    labelKey: 'achievement.firstQuoteAccepted.label',
    color: 'text-emerald-300',
    titleKey: 'achievement.firstQuoteAccepted.title',
  },
  first_order_completed: {
    icon: PackageCheck,
    labelKey: 'achievement.firstOrderCompleted.label',
    color: 'text-green-300',
    titleKey: 'achievement.firstOrderCompleted.title',
  },
  returning_customer: {
    icon: Repeat2,
    labelKey: 'achievement.returningCustomer.label',
    color: 'text-violet-300',
    titleKey: 'achievement.returningCustomer.title',
  },
  full_business_cycle: {
    icon: Workflow,
    labelKey: 'achievement.fullBusinessCycle.label',
    color: 'text-fuchsia-300',
    titleKey: 'achievement.fullBusinessCycle.title',
  },
  material_to_print: {
    icon: Factory,
    labelKey: 'achievement.materialToPrint.label',
    color: 'text-amber-300',
    titleKey: 'achievement.materialToPrint.title',
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
    <span className="inline-flex items-center" title={t(config.titleKey)}>
      {showArtwork && config.artworkSrc && !artworkFailed ? (
        <img
          src={config.artworkSrc}
          alt=""
          className="h-full w-full rounded-xl object-cover"
          onError={() => setArtworkFailed(true)}
        />
      ) : (
        <Icon className={`${sizeClasses[size]} ${config.color}`} />
      )}
    </span>
  );
};
