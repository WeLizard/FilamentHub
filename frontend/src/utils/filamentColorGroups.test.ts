import { describe, expect, it } from 'vitest';
import { classifyFilamentColorGroup } from './filamentColorGroups';

describe('classifyFilamentColorGroup', () => {
  it.each([
    ['#111111', false, 'black'],
    ['#F5F5F5', false, 'white'],
    ['#808080', false, 'gray'],
    ['#FF0000', false, 'red'],
    ['#FF7A00', false, 'orange'],
    ['#FFD900', false, 'yellow'],
    ['#00A651', false, 'green'],
    ['#0066FF', false, 'blue'],
    ['#800080', false, 'purple'],
    ['#FFB6C1', false, 'pink'],
    ['#A52A2A', false, 'brown'],
    ['#D4AF37', true, 'gold'],
    ['#C0C0C0', true, 'silver'],
    ['#C98C86', true, 'pink'],
    ['#52664A', false, 'green'],
    ['#C5A77B', false, 'brown'],
    ['#34383D', false, 'gray'],
    ['#C9E8B4', false, 'green'],
    ['#7E9CAB', false, 'blue'],
    ['#F05A28', false, 'orange'],
  ] as const)('maps %s to %s', (hex, metallic, expected) => {
    expect(classifyFilamentColorGroup(hex, metallic)).toBe(expected);
  });

  it('does not invent a group for an invalid HEX value', () => {
    expect(classifyFilamentColorGroup('red-ish')).toBeNull();
  });
});
