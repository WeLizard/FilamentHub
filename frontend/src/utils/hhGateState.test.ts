import { describe, expect, it } from 'vitest';
import { isUnidentifiedHHFilament, markHHGateEmptyCommand } from './hhGateState';

describe('Happy Hare unidentified filament state', () => {
  it.each([1, 2])('detects occupied gate without a linked spool for status %s', (hh_status) => {
    expect(isUnidentifiedHHFilament({ hh_status, spool_id: null })).toBe(true);
  });

  it.each([-1, 0, null])('does not treat status %s as unidentified filament', (hh_status) => {
    expect(isUnidentifiedHHFilament({ hh_status, spool_id: null })).toBe(false);
  });

  it('does not flag a gate that already has a linked spool', () => {
    expect(isUnidentifiedHHFilament({ hh_status: 1, spool_id: 42 })).toBe(false);
  });

  it('builds the stock Happy Hare command for marking a gate empty', () => {
    expect(markHHGateEmptyCommand(6)).toBe('MMU_GATE_MAP GATE=6 AVAILABLE=0');
  });
});
