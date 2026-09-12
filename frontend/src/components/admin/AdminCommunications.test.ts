import { describe, expect, it } from 'vitest';
import en from '../../locales/en/translation.json';
import ru from '../../locales/ru/translation.json';
import zh from '../../locales/zh/translation.json';
import { splitQuotedText } from './AdminCommunications';

describe('admin email delivery truthfulness', () => {
  it('labels relay acceptance and uncertain non-retryable outcomes in every locale', () => {
    expect(en.adminCommunications.delivery.sent).toBe('Accepted by mail server');
    expect(ru.adminCommunications.delivery.sent).toBe('Принято почтовым сервером');
    expect(zh.adminCommunications.delivery.sent).toBe('邮件服务器已接受');
    expect(en.adminCommunications.compose.sent).toBe('Email accepted by mail server');
    expect(ru.adminCommunications.replySent).toBe('Ответ принят почтовым сервером');
    expect(zh.adminCommunications.compose.sent).toBe('邮件已被邮件服务器接受');

    for (const locale of [en, ru, zh]) {
      expect(locale.adminCommunications.delivery.uncertain).toBeTruthy();
      expect(locale.apiErrors.ERR_EMAIL_DELIVERY_UNCERTAIN).toBeTruthy();
    }
  });
});

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
