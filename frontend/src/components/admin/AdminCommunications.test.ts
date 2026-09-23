import { afterEach, describe, expect, it, vi } from 'vitest';
import en from '../../locales/en/translation.json';
import ru from '../../locales/ru/translation.json';
import zh from '../../locales/zh/translation.json';
import { createElement } from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { adminCommunicationsAPI } from '../../api/client';
import type { EmailAttachment } from '../../types/api';
import { EmailImagePreviews, splitQuotedText } from './AdminCommunications';

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


describe('email attachment previews', () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  const attachment: EmailAttachment = {
    index: 0, filename: 'scan.tiff', content_type: 'image/tiff', size: 10,
    downloadable: true, content_id: null, inline: false,
  };

  function mockImage(valid = true) {
    vi.stubGlobal('Image', class {
      src = '';
      naturalWidth = 32;
      naturalHeight = 24;
      decode = () => valid ? Promise.resolve() : Promise.reject(new Error('Invalid image'));
    });
  }

  it('automatically shows a regular image attachment in a plain text letter', async () => {
    mockImage();
    const download = vi.spyOn(adminCommunicationsAPI, 'downloadEmailAttachment')
      .mockResolvedValue(new Blob(['image'], { type: 'image/png' }));
    render(createElement(EmailImagePreviews, {
      threadId: 1, messageId: 2, attachments: [attachment], html: null,
    }));
    expect(await screen.findByAltText('scan.tiff')).toBeTruthy();
    expect(download).toHaveBeenCalledWith(1, 2, 0, true);
  });

  it('does not fetch documents or duplicate a CID image already inside the letter', () => {
    const download = vi.spyOn(adminCommunicationsAPI, 'downloadEmailAttachment');
    render(createElement(EmailImagePreviews, {
      threadId: 1, messageId: 2, html: '<img src="cid:photo">', attachments: [
        { ...attachment, content_id: 'photo' },
        { ...attachment, index: 1, filename: 'file.zip', content_type: 'application/zip' },
      ],
    }));
    expect(download).not.toHaveBeenCalled();
  });

  it('does not render a file the image decoder rejects', async () => {
    mockImage(false);
    const download = vi.spyOn(adminCommunicationsAPI, 'downloadEmailAttachment')
      .mockResolvedValue(new Blob(['invalid'], { type: 'image/png' }));
    render(createElement(EmailImagePreviews, {
      threadId: 1, messageId: 2, attachments: [attachment], html: null,
    }));
    await waitFor(() => expect(download).toHaveBeenCalled());
    expect(screen.queryByRole('img')).toBeNull();
  });
});
