import { describe, expect, it } from 'vitest';

import { nameForColor } from './presetColorCopy';

describe('nameForColor', () => {
  const blue = { name: 'DAS PETG', color_name: 'Blau' };
  const green = { name: 'DAS PETG', color_name: 'Grasgrün', color_hex: '#008B29' };

  it('puts the new colour where the name says the old one', () => {
    expect(nameForColor('DAS PETG Blau fast', blue, green)).toBe('DAS PETG Grasgrün fast');
    expect(nameForColor('PETG (blau)', blue, green)).toBe('PETG (Grasgrün)');
  });

  it('leaves a name alone when it does not mention the old colour as a word', () => {
    expect(nameForColor('Blaupause PETG', blue, green)).toBe('Blaupause PETG');
    expect(nameForColor('My tuned PETG', blue, green)).toBe('My tuned PETG');
  });

  it('names a colour without a name by its HEX', () => {
    expect(nameForColor('PETG Blau', blue, { name: 'DAS PETG', color_hex: '#00ff00' })).toBe('PETG #00FF00');
  });
});
