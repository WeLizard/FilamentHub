import axios, { type AxiosAdapter } from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';

import endpoints from './endpoints.json';
import fixtures from './fixtures.json';
import texts from './texts.json';
import {
  ERR_DEMO_READ_ONLY,
  demoMissedRequests,
  demoRequestKey,
  installDemoTransport,
  localizeDemoFixtures,
  startDemoSession,
  stopDemoSession,
} from './demoTransport';

function demoClient(server: AxiosAdapter) {
  const client = axios.create({ baseURL: '/api/v1', adapter: server });
  installDemoTransport(client);
  return client;
}

const sample = {
  responses: {
    '/spools/feed?limit=24&state=active': { items: [{ id: 1 }] },
    '/auth/me': { id: 7 },
  },
};

describe('demo transport', () => {
  afterEach(() => stopDemoSession());

  it('leaves the client alone outside a demo session', async () => {
    const server = vi.fn<AxiosAdapter>(async (config) => (
      { data: 'live', status: 200, statusText: 'OK', headers: {}, config }
    ));

    await expect(demoClient(server).get('/auth/me')).resolves.toMatchObject({ data: 'live' });
    expect(server).toHaveBeenCalledOnce();
  });

  it('answers account reads from the recording and never reaches the server', async () => {
    const server = vi.fn<AxiosAdapter>();
    startDemoSession(sample);
    const client = demoClient(server);

    await expect(client.get('/auth/me')).resolves.toMatchObject({ data: { id: 7 } });
    // Another page of a recorded list is the recorded page.
    await expect(client.get('/spools/feed', { params: { state: 'active', limit: 24, cursor: 'next' } }))
      .resolves.toMatchObject({ data: { items: [{ id: 1 }] } });
    expect(server).not.toHaveBeenCalled();
  });

  it('does not pass one filter off as another', async () => {
    startDemoSession(sample);
    const client = demoClient(vi.fn<AxiosAdapter>());

    // Showing active spools under "archived" would be a lie; a miss is reported instead.
    await expect(client.get('/spools/feed', { params: { state: 'archived', limit: 24 } }))
      .rejects.toMatchObject({ response: { status: 404 } });
    expect(demoMissedRequests()).toContain('/spools/feed?limit=24&state=archived');
  });

  it('refuses every write with an error the screens already know how to show', async () => {
    const server = vi.fn<AxiosAdapter>();
    startDemoSession(sample);
    const client = demoClient(server);

    for (const write of [client.post('/spools', {}), client.patch('/auth/me', {}), client.delete('/spools/1')]) {
      await expect(write).rejects.toMatchObject({
        response: { status: 403, data: { detail: { code: ERR_DEMO_READ_ONLY } } },
      });
    }
    expect(server).not.toHaveBeenCalled();
  });

  it('keys a request the same way however its query was written', () => {
    expect(demoRequestKey('/api/v1/presets/?size=100', { page: 1, active_only: false }))
      .toBe('/presets?active_only=false&page=1&size=100');
  });
});

describe('demo recording', () => {
  it('holds every read the demo screens are known to make', () => {
    // endpoints.json is the list, fixtures.json the recording: a read added to
    // the list without re-recording would leave a hole in a demo screen.
    // A read that names records by id is listed with a placeholder for them.
    const recorded = Object.keys(fixtures.responses);
    const unmatched = endpoints.filter((endpoint) => {
      const [before, after = null] = endpoint.split(/\{\w+\}/);
      return !recorded.some((key) => (
        after === null ? key === endpoint : key.startsWith(before) && key.endsWith(after)
      ));
    });

    expect(unmatched).toEqual([]);
    expect(recorded).toHaveLength(endpoints.length);
  });

  it('has every free-text value of the sample account in all three languages', () => {
    // The showcase is written in Russian; a re-recording with new text must
    // not leave Russian strings in the English or Chinese demo.
    const translations = texts as Record<string, Record<string, string>>;
    const untranslated = new Set<string>();
    const visit = (value: unknown) => {
      if (typeof value === 'string') {
        if (/[а-яё]/i.test(value) && !(translations[value]?.en && translations[value]?.zh)) untranslated.add(value);
      } else if (value !== null && typeof value === 'object') {
        Object.values(value).forEach(visit);
      }
    };
    visit(fixtures);

    expect([...untranslated]).toEqual([]);
    expect(JSON.stringify(localizeDemoFixtures(fixtures, translations, 'en'))).not.toMatch(/[а-яё]/i);
    expect(JSON.stringify(localizeDemoFixtures(fixtures, translations, 'ru'))).toContain('Ольга Крафт');
  });

  it('prices the sample account in the currency of the reader', () => {
    const sampleMoney = {
      responses: {
        '/spools': [
          { price: 2000, currency: null, weight: 1000, bought_priced_count: 3 },
          { price: 30, currency: 'EUR' },
        ],
        '/crm/summary': { accepted_amount: { RUB: 10000 }, customers_total: 1 },
        '/calculator/profile': { settings: [{ key: 'machine_hour_rate', value: 200, source_currency: 'RUB' }] },
      },
    };

    const chinese = localizeDemoFixtures(sampleMoney, {}, 'zh').responses as typeof sampleMoney.responses;

    // Roubles in a Chinese demo read as a mistake; a price in euros is a fact about that record.
    expect(chinese['/spools']).toEqual([
      { price: 180, currency: 'CNY', weight: 1000, bought_priced_count: 3 },
      { price: 30, currency: 'EUR' },
    ]);
    expect(chinese['/crm/summary']).toEqual({ accepted_amount: { CNY: 900 }, customers_total: 1 });
    expect(chinese['/calculator/profile'].settings[0]).toMatchObject({ value: 18, source_currency: 'CNY' });
    expect(JSON.stringify(localizeDemoFixtures(fixtures, {}, 'zh'))).not.toContain('"RUB"');
    // In the source language only the missing currency is filled in.
    expect(localizeDemoFixtures(sampleMoney, {}, 'ru').responses).toMatchObject({
      '/spools': [{ price: 2000, currency: 'RUB' }, { price: 30, currency: 'EUR' }],
      '/crm/summary': sampleMoney.responses['/crm/summary'],
    });
    expect(localizeDemoFixtures({ responses: { '/crm/orders': { total: 2, items: [{ total: 1000, currency: 'RUB' }] } } }, {}, 'en'))
      .toEqual({ responses: { '/crm/orders': { total: 2, items: [{ total: 12.5, currency: 'USD' }] } } });
  });

  it('carries nothing that looks like a credential', () => {
    const secrets: string[] = [];
    const visit = (value: unknown, field: string) => {
      if (Array.isArray(value)) value.forEach((item) => visit(item, field));
      else if (value !== null && typeof value === 'object') {
        Object.entries(value).forEach(([name, item]) => visit(item, name));
      } else if (
        typeof value === 'string' && value !== '' && value !== 'demo'
        && /api_key|device_key|bridge_key|plain_key|key_hash|secret|password|token|pairing_code/i.test(field)
      ) {
        secrets.push(field);
      }
    };
    visit(fixtures, '');

    expect(secrets).toEqual([]);
  });
});
