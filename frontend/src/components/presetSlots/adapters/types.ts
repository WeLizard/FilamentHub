import type { ReactNode } from 'react';
import type {
  GateState,
  MaterialSystem,
  PhysicalPrinter,
  UserSpool,
} from '../../../api/client';
import type { DeviceContactMode } from '../../../utils/deviceLink';
import type { Printer as CatalogPrinter } from '../../../types/api';

export type PrinterConnectionMethod = 'orca' | 'edge' | 'native';
export interface FeedTopologyChoice {
  id: string;
  labelKey: string;
  kind: string;
  count?: { labelKey: string; initial: number; max: number };
  extras?: Array<{ labelKey: string; index: number; kind: string; checked?: boolean }>;
  slots: (count: number) => Array<{ provider_index: number; kind: string }>;
}

export interface AdapterOnboarding {
  connectionLabelKey: string;
  connectionHintKey: string;
  methods: PrinterConnectionMethod[];
  orcaProbe?: boolean;
  /** Matching suggests a path, never proves a device identity or installed hardware. */
  matchesModel?: (model: CatalogPrinter) => boolean;
  topologies: FeedTopologyChoice[];
}

export type FeedAdapterCapability =
  | 'read'
  | 'write'
  | 'presence'
  | 'spool_identity'
  | 'consumption'
  | 'local_command';

export interface AdapterViewContext {
  printer: PhysicalPrinter;
  system: MaterialSystem;
  gates: GateState[];
  spools: UserSpool[];
  linkConfirmed: boolean;
}

export interface FeedAdapterLink {
  /** Locale key telling where this address goes on the printer. */
  hintKey: string;
  /** What a person copies: a config block, a bare address, whatever fits. */
  snippet: (baseUrl: string, apiKey: string) => string;
  /** Providers supporting a separate secret keep it out of URLs and access logs. */
  apiKeyHeader?: string;
}

export interface FeedAdapter {
  /** Stored on the system as its provider. */
  id: string;
  onboarding?: AdapterOnboarding;
  /** Locale key for the name a person picks in the list. */
  labelKey: string;
  /** Systems with a fixed shape do not ask how many slots they have. */
  fixedSlots: number | null;
  /** Dynamic providers create no guessed slots; the first snapshot supplies them. */
  topologyFromProvider?: boolean;
  /** Provider UI remains useful to collapse even when the system has one slot. */
  alwaysCollapsible?: boolean;
  /** Capabilities provided by this integration path, not hoped-for future features. */
  capabilities: FeedAdapterCapability[];
  /** This provider has an implemented Edge setup path, not merely read capability. */
  supportsEdge?: boolean;
  edgeKinds?: string[];
  /** Whether silence between provider requests is expected. */
  contactMode?: DeviceContactMode;
  /** Provider-specific wording for the topology field and its saved summary. */
  slotCountLabelKey?: string;
  slotCountSummaryKey?: string;
  /** How the printer is pointed at us; null when nothing is linked at all. */
  link: FeedAdapterLink | null;
  /** Provider-specific guidance shown while its system is being created. */
  renderCreateHelp?: () => ReactNode;
  /** Extra controls this system needs and no other one does. */
  renderSettings?: (context: AdapterViewContext) => ReactNode;
  /** Compact provider actions placed with the system-level controls. */
  renderActions?: (context: AdapterViewContext) => ReactNode;
  /** Steps left before the data starts arriving. */
  renderSetup?: (context: AdapterViewContext) => ReactNode;
}
