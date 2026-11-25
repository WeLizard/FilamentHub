import data from './capabilities.json';

/**
 * The single list of what FilamentHub does. The features page, the roadmap on
 * the about page, llms.txt and the static pages for crawlers are all derived
 * from it, so a capability is described once.
 */
export type CapabilityStatus = 'working' | 'progress' | 'next';
export type CapabilityAccess = 'open' | 'account' | 'brand';

export interface CapabilityGroup {
  id: string;
  access: CapabilityAccess;
  /** The one place this group sends the reader to. Unique across groups. */
  link: string;
  /** The account screen of this group with sample data, for a guest. */
  demo?: string;
}

export interface CapabilityItem {
  id: string;
  /** null: a project-wide item shown only in the roadmap. */
  group: string | null;
  status: CapabilityStatus;
}

export const CAPABILITY_STATUSES: readonly CapabilityStatus[] = ['working', 'progress', 'next'];
export const CAPABILITY_GROUPS = data.groups as CapabilityGroup[];
export const CAPABILITY_ITEMS = data.items as CapabilityItem[];

export interface ManufacturerStep {
  id: string;
  /** content_key of the wiki guide for this step. */
  guide: string;
}

/** The manufacturer path, in order: the wiki hub and the manufacturers page share it. */
export const MANUFACTURER_STEPS = data.manufacturerSteps as ManufacturerStep[];

export function manufacturerGuideLink(step: ManufacturerStep): string {
  return `/wiki/articles/${step.guide}?start=1&journey=${encodeURIComponent(`brand:${step.id}`)}`;
}

export function capabilitiesWithStatus(status: CapabilityStatus): CapabilityItem[] {
  return CAPABILITY_ITEMS.filter((item) => item.status === status);
}

export function groupCapabilities(groupId: string, status: CapabilityStatus): CapabilityItem[] {
  return CAPABILITY_ITEMS.filter((item) => item.group === groupId && item.status === status);
}
