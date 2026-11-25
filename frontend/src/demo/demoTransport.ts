import axios, { AxiosError, type AxiosAdapter, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios';

/**
 * Guest demo: the account screens stay real, their data does not.
 *
 * While a demo session is active every request of the API client is answered
 * here: a read gets the recorded response of the showcase account, a public
 * read goes to the real server, and every write is refused. One seam covers
 * all screens, so no screen needs its own read-only mode.
 */
export const ERR_DEMO_READ_ONLY = 'ERR_DEMO_READ_ONLY';

export interface DemoFixtures {
  /** Recorded GET responses, keyed by `demoRequestKey`. */
  responses: Record<string, unknown>;
}

let activeFixtures: DemoFixtures | null = null;
// A recorded read without its paging -> its key: the demo holds one page of each list.
let recordedLists = new Map<string, string>();
const PAGING = new Set(['page', 'size', 'limit', 'offset', 'cursor']);

function withoutPaging(key: string): string {
  const [path, query = ''] = key.split('?');
  const kept = query.split('&').filter((pair) => pair && !PAGING.has(pair.split('=')[0]));
  return kept.length > 0 ? `${path}?${kept.join('&')}` : path;
}
const missedRequests = new Set<string>();

export function startDemoSession(fixtures: DemoFixtures): void {
  activeFixtures = fixtures;
  recordedLists = new Map();
  for (const key of Object.keys(fixtures.responses)) {
    const list = withoutPaging(key);
    if (!recordedLists.has(list)) recordedLists.set(list, key);
  }
}

export function stopDemoSession(): void {
  activeFixtures = null;
  recordedLists = new Map();
}

export function isDemoSession(): boolean {
  return activeFixtures !== null;
}

/** The sample account keeps its books in this currency. */
const DEMO_SOURCE_CURRENCY = 'RUB';
/**
 * What a reader of each language sees instead: a plausible local price level,
 * not an exchange rate to keep current.
 */
const DEMO_CURRENCIES: Record<string, { code: string; rate: number }> = {
  ru: { code: DEMO_SOURCE_CURRENCY, rate: 1 },
  en: { code: 'USD', rate: 0.0125 },
  zh: { code: 'CNY', rate: 0.09 },
};
const MONEY_FIELD = /^(?:cost(?:_.+)?|.+_cost(?:_per_.+)?|(?:.+_)?price(?:_per_.+)?|subtotal|tax_total|grand_total|bought_total|consumed_value|shelf_value|.+_rate_per_hour|fixed_costs|profit_margin|(?:.+_)?amount)$/;
const NOT_MONEY = /^spools_|_count$|_percent$/;
const CURRENCY_FIELD = /(?:^|_)currency$/;
// Settings stored as { key, value } pairs name their money by key.
const MONEY_SETTING = /_rate$|_cost_per_|_wear_per_/;

function convertAmount(field: string, amount: number, rate: number): number {
  const digits = field.includes('per_gram') ? 4 : 2;
  return Number((amount * rate).toFixed(digits));
}

/**
 * The sample account was written in Russian and priced in roubles. `texts`
 * gives each of its free-text values (names, comments, order titles) in
 * another language; money becomes the currency a reader of that language
 * expects. Records priced in some other currency are left as they are.
 */
export function localizeDemoFixtures(
  fixtures: DemoFixtures,
  texts: Record<string, Record<string, string>>,
  locale: string,
): DemoFixtures {
  const currency = DEMO_CURRENCIES[locale];
  const localize = (value: unknown, field: string, inSourceCurrency: boolean): unknown => {
    if (typeof value === 'string') {
      if (currency && inSourceCurrency && value === DEMO_SOURCE_CURRENCY) return currency.code;
      return texts[value]?.[locale] ?? value;
    }
    if (typeof value === 'number') {
      return currency && inSourceCurrency && MONEY_FIELD.test(field) && !NOT_MONEY.test(field)
        ? convertAmount(field, value, currency.rate)
        : value;
    }
    if (Array.isArray(value)) return value.map((item) => localize(item, field, inSourceCurrency));
    if (value === null || typeof value !== 'object') return value;

    const record = value as Record<string, unknown>;
    // A record that names another currency is priced in it, and so are its parts.
    const named = Object.entries(record).find(([name, item]) => CURRENCY_FIELD.test(name) && typeof item === 'string');
    const ours = named ? named[1] === DEMO_SOURCE_CURRENCY : inSourceCurrency;
    return Object.fromEntries(Object.entries(record).map(([name, item]) => {
      if (
        currency && ours && name === 'currency' && item === null
        && Object.entries(record).some(([other, amount]) => typeof amount === 'number' && MONEY_FIELD.test(other))
      ) {
        // The showcase leaves spool prices without a currency; a priced record says which.
        return [name, currency.code];
      }
      if (currency && ours && named && name === 'total' && typeof item === 'number') {
        // `total` counts rows in a list and sums money in a record that names its currency.
        return [name, convertAmount(name, item, currency.rate)];
      }
      if (currency && ours && name === DEMO_SOURCE_CURRENCY && typeof item === 'number') {
        // Totals keyed by currency code.
        return [currency.code, convertAmount(name, item, currency.rate)];
      }
      if (
        currency && ours && name === 'value' && typeof item === 'number'
        && typeof record.key === 'string' && MONEY_SETTING.test(record.key)
      ) {
        return [name, convertAmount(record.key, item, currency.rate)];
      }
      return [name, localize(item, name, ours)];
    }));
  };
  return { responses: localize(fixtures.responses, '', true) as DemoFixtures['responses'] };
}

const DEMO_CHOICE_KEY = 'fh-demo-chosen';

/**
 * A guest who opened the demo keeps getting it from locked sections for the
 * rest of the browser session, instead of the sign-in card on every link.
 */
export function rememberDemoChoice(chosen: boolean): void {
  try {
    if (chosen) window.sessionStorage.setItem(DEMO_CHOICE_KEY, '1');
    else window.sessionStorage.removeItem(DEMO_CHOICE_KEY);
  } catch {
    // Storage is unavailable: the guest simply chooses again.
  }
}

export function demoWasChosen(): boolean {
  try {
    return window.sessionStorage.getItem(DEMO_CHOICE_KEY) === '1';
  } catch {
    return false;
  }
}

/** Account reads the recording did not cover: what to add to endpoints.json. */
export function demoMissedRequests(): string[] {
  return [...missedRequests].sort();
}

if (import.meta.env.DEV) {
  // In a dev build, `__fhDemoMissed()` in the console lists them after a walk through the demo.
  (window as unknown as { __fhDemoMissed: typeof demoMissedRequests }).__fhDemoMissed = demoMissedRequests;
}

// Reads that belong to no account: the demo shows the live catalogue around
// the sample account instead of a frozen copy of it.
const PUBLIC_READS = [
  /^\/filaments(?:\/|$)/,
  /^\/brands(?:\/|$)/,
  /^\/filament-lines(?:\/|$)/,
  /^\/filament-reviews\/filament\//,
  /^\/printers(?:\/|$)/,
  /^\/currencies(?:\/|$)/,
  /^\/wiki(?:\/|$)/,
  /^\/downloads(?:\/|$)/,
  /^\/catalog-urls(?:\/|$)/,
  /^\/country-cells(?:\/|$)/,
  /^\/labels\/filaments\//,
  /^\/auth\/(?:methods|legal-documents|legal-requirements)(?:\/|$)/,
];

function serializeQuery(params: unknown): string {
  if (params === null || params === undefined) return '';
  const entries: [string, string][] = [];
  const source = params instanceof URLSearchParams
    ? [...params.entries()]
    : Object.entries(params as Record<string, unknown>);
  for (const [name, value] of source) {
    if (value === undefined || value === null) continue;
    for (const item of Array.isArray(value) ? value : [value]) {
      entries.push([name, String(item)]);
    }
  }
  entries.sort(([a, av], [b, bv]) => (a === b ? av.localeCompare(bv) : a.localeCompare(b)));
  return entries.map(([name, value]) => `${name}=${value}`).join('&');
}

/** `path?sorted=query` relative to the API root, the same for recorder and player. */
export function demoRequestKey(url: string, params?: unknown): string {
  const [rawPath, inlineQuery = ''] = url.split('?');
  const path = rawPath.replace(/^\/api\/v1/, '').replace(/\/$/, '') || '/';
  const query = serializeQuery({
    ...Object.fromEntries(new URLSearchParams(inlineQuery)),
    ...(params instanceof URLSearchParams ? Object.fromEntries(params) : (params as object | undefined)),
  });
  return query ? `${path}?${query}` : path;
}

function respond(config: InternalAxiosRequestConfig, status: number, data: unknown) {
  const response = { data, status, statusText: String(status), headers: {}, config, request: null };
  if (status >= 200 && status < 300) return Promise.resolve(response);
  return Promise.reject(new AxiosError(
    `Demo request failed with status ${status}`,
    AxiosError.ERR_BAD_REQUEST,
    config,
    null,
    response,
  ));
}

const demoAdapter: AxiosAdapter = (config) => {
  const fixtures = activeFixtures;
  const method = (config.method || 'get').toLowerCase();
  if (fixtures === null) {
    return axios.getAdapter(axios.defaults.adapter)(config);
  }
  if (method !== 'get') {
    return respond(config, 403, { detail: { code: ERR_DEMO_READ_ONLY } });
  }
  const key = demoRequestKey(config.url || '', config.params);
  if (key in fixtures.responses) {
    return respond(config, 200, structuredClone(fixtures.responses[key]));
  }
  // Another page of a recorded list gets the recorded page; another filter is
  // a different answer and has to be recorded on its own.
  const sameList = recordedLists.get(withoutPaging(key));
  if (sameList !== undefined) {
    return respond(config, 200, structuredClone(fixtures.responses[sameList]));
  }
  const path = key.split('?')[0];
  if (PUBLIC_READS.some((pattern) => pattern.test(path))) {
    return axios.getAdapter(axios.defaults.adapter)(config);
  }
  missedRequests.add(key);
  return respond(config, 404, { detail: { code: 'ERR_NOT_FOUND' } });
};

/** Route the API client through the demo while a demo session is active. */
export function installDemoTransport(client: AxiosInstance): void {
  client.interceptors.request.use((config) => {
    if (isDemoSession()) {
      config.adapter = demoAdapter;
    }
    return config;
  });
}
