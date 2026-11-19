import { describe, expect, it } from 'vitest';
import { computeDropdownPosition } from './CustomSelect';

const button = (top: number) => ({ top, bottom: top + 50, left: 20, width: 200 });

describe('CustomSelect dropdown placement', () => {
  it('opens below when the list fits under the button', () => {
    const position = computeDropdownPosition(button(100), 800, 8);
    expect(position).toMatchObject({ top: 158, maxHeight: 240 });
    expect(position.bottom).toBeUndefined();
  });

  it('opens above near the bottom edge so the list stays on screen', () => {
    const position = computeDropdownPosition(button(600), 700, 8);
    expect(position).toMatchObject({ bottom: 108, maxHeight: 240 });
    expect(position.top).toBeUndefined();
  });

  it('keeps a short list below when it fits, and shrinks a list that fits nowhere', () => {
    expect(computeDropdownPosition(button(600), 780, 2).top).toBe(658);
    const cramped = computeDropdownPosition(button(100), 300, 8);
    expect(cramped.top).toBe(158);
    expect(cramped.maxHeight).toBe(134);
  });
});
