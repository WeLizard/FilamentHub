import { describe, expect, it } from 'vitest';
import { splitQuotedText } from './AdminCommunications';

describe('splitQuotedText', () => {
  it('keeps an unquoted letter as one block', () => {
    const blocks = splitQuotedText('Hi Stefan,\nthanks for the reply.');

    expect(blocks).toEqual([
      { quoted: false, depth: 0, lines: ['Hi Stefan,', 'thanks for the reply.'] },
    ]);
  });

  it('separates the reply from what it quotes and drops the markers', () => {
    const blocks = splitQuotedText('Sounds good.\n\n> I built a BumpMesh integration\n> and opened a draft PR');

    expect(blocks).toEqual([
      { quoted: false, depth: 0, lines: ['Sounds good.'] },
      { quoted: true, depth: 1, lines: ['I built a BumpMesh integration', 'and opened a draft PR'] },
    ]);
  });

  it('reads a quote inside a quote as its own depth', () => {
    const blocks = splitQuotedText('> he wrote:\n>> the original question');

    expect(blocks).toEqual([
      { quoted: true, depth: 1, lines: ['he wrote:'] },
      { quoted: true, depth: 2, lines: ['the original question'] },
    ]);
  });

  it('reads both spellings of a nested quote the same way', () => {
    expect(splitQuotedText('>> tight')).toEqual(splitQuotedText('> > tight'));
  });

  it('drops the blank lines mail clients leave around a quote', () => {
    const blocks = splitQuotedText('>\n> the point\n>\n');

    expect(blocks).toEqual([{ quoted: true, depth: 1, lines: ['the point'] }]);
  });

  it('keeps a blank line inside a paragraph, since it is the author speaking', () => {
    const blocks = splitQuotedText('First.\n\nSecond.');

    expect(blocks).toEqual([{ quoted: false, depth: 0, lines: ['First.', '', 'Second.'] }]);
  });
});
