import type { ReactNode } from 'react';
import type { GateState, PhysicalPrinter, MaterialSystem } from '../../../api/client';

export interface AdapterViewContext {
  printer: PhysicalPrinter;
  system: MaterialSystem;
  gates: GateState[];
  linkConfirmed: boolean;
}

export interface FeedAdapter {
  /** Stored on the system as its provider. */
  id: string;
  /** Locale key for the name a person picks in the list. */
  labelKey: string;
  /** Systems with a fixed shape do not ask how many slots they have. */
  fixedSlots: number | null;
  /** Whether the printer needs a key to report into this system. */
  needsLink: boolean;
  /** Extra controls this system needs and no other one does. */
  renderSettings?: (context: AdapterViewContext) => ReactNode;
  /** Steps left before the data starts arriving. */
  renderSetup?: (context: AdapterViewContext) => ReactNode;
}
