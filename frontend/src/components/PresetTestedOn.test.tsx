import { render, screen } from '@testing-library/react';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import { describe, expect, it } from 'vitest';
import en from '../locales/en/translation.json';
import ru from '../locales/ru/translation.json';
import zh from '../locales/zh/translation.json';
import type { Printer } from '../types/api';
import { PresetTestedOn } from './PresetTestedOn';

describe('PresetTestedOn', () => {
  it.each([
    ['en', 'Tested on'],
    ['ru', 'Проверено на'],
    ['zh', '已测试的打印机'],
  ])('shows both tested models as evidence in %s', async (language, label) => {
    const i18n = createInstance();
    await i18n.init({
      lng: language,
      resources: { en: { translation: en }, ru: { translation: ru }, zh: { translation: zh } },
    });
    const printers = [
      { id: 1, name: 'Bambu Lab P2S', manufacturer: 'BambuLab', model: 'P2S' },
      { id: 2, name: 'Voron 2.4 350', manufacturer: 'Voron', model: '2.4 350' },
    ] as Printer[];

    render(<I18nextProvider i18n={i18n}><PresetTestedOn printers={printers} /></I18nextProvider>);

    expect(screen.getByText(`${label}:`)).toBeInTheDocument();
    expect(screen.getByText('Bambu Lab P2S')).toHaveAttribute('title', 'Bambu Lab P2S');
    expect(screen.getByText('Voron 2.4 350')).toBeInTheDocument();
    expect(i18n.t('presetModal.printers')).toBe(label);
  });
});
