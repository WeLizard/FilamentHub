import type { GateState } from '../api/client';

export function isUnidentifiedHHFilament(
  gate: Pick<GateState, 'hh_status' | 'spool_id'> | null | undefined,
): boolean {
  return gate?.spool_id == null && (gate?.hh_status === 1 || gate?.hh_status === 2);
}

export function markHHGateEmptyCommand(gateIndex: number): string {
  return `MMU_GATE_MAP GATE=${gateIndex} AVAILABLE=0`;
}
