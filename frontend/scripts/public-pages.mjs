// The public pages as plain text: what a reader without JavaScript gets.
//
// Every string comes from the same locale files the application renders, and
// every capability from src/data/capabilities.json, so the static pages,
// llms.txt and the live pages describe the product in the same words. A
// missing key stops the build instead of publishing a hole.

export const DEFAULT_LOCALE = 'en';

export function createTranslator(...resources) {
  const merged = Object.assign({}, ...resources);
  const lookup = (key) => key.split('.').reduce(
    (node, part) => (node !== null && typeof node === 'object' ? node[part] : undefined),
    merged,
  );
  const t = (key) => {
    const value = lookup(key);
    if (typeof value !== 'string' || value === '') {
      throw new Error(`Public page text is missing: ${key}`);
    }
    return value;
  };
  /** A list of records, as the application reads it with `returnObjects`. */
  t.rows = (key) => {
    const value = lookup(key);
    if (!Array.isArray(value) || value.length === 0) {
      throw new Error(`Public page list is missing: ${key}`);
    }
    return value;
  };
  return t;
}

const withoutQuery = (link) => link.split('?')[0];

function capabilityLists(capabilities, t, groupId, status) {
  return capabilities.items
    .filter((item) => item.group === groupId && item.status === status)
    .map((item) => t(`capabilities.items.${item.id}`));
}

function siteNavigation(t) {
  return ['nav', [
    { href: '/', label: t('catalogPage.seoTitle') },
    { href: '/features', label: t('featuresPage.title') },
    { href: '/wiki', label: t('capabilities.groups.learning.title') },
    { href: '/download', label: t('downloadPage.pluginTitle') },
    { href: '/download/edge', label: t('edgeSection.title') },
    { href: '/for-brands', label: t('forBrands.navLabel') },
    { href: '/about', label: t('aboutPage.title') },
  ]];
}

function homePage(t, capabilities) {
  return {
    path: '/',
    title: t('catalogPage.seoTitle'),
    description: t('catalogPage.seoDescription'),
    blocks: [
      ['h1', t('catalogPage.heroTitle')],
      ['p', t('catalogPage.heroSubtitle')],
      ['p', t('featuresPage.lead')],
      ['h2', t('featuresPage.title')],
      ['ul', capabilities.groups.map((group) => ({
        href: withoutQuery(group.link),
        label: t(`capabilities.groups.${group.id}.title`),
        text: t(`capabilities.groups.${group.id}.text`),
      }))],
    ],
  };
}

function featuresPage(t, capabilities) {
  const blocks = [
    ['h1', t('featuresPage.title')],
    ['p', t('featuresPage.lead')],
  ];
  for (const group of capabilities.groups) {
    const working = capabilityLists(capabilities, t, group.id, 'working');
    const progress = capabilityLists(capabilities, t, group.id, 'progress');
    blocks.push(['h2', t(`capabilities.groups.${group.id}.title`)]);
    blocks.push(['p', `${t(`featuresPage.access.${group.access}`)}. ${t(`capabilities.groups.${group.id}.text`)}`]);
    if (working.length > 0) {
      blocks.push(['ul', working]);
    }
    if (progress.length > 0) {
      blocks.push(['h3', t('featuresPage.progressLabel')]);
      blocks.push(['ul', progress]);
    }
    blocks.push(['link', {
      href: withoutQuery(group.link),
      label: t(`capabilities.groups.${group.id}.action`),
    }]);
  }
  blocks.push(['h2', t('featuresPage.aboutTitle')]);
  blocks.push(['p', t('featuresPage.aboutText')]);
  return {
    path: '/features',
    title: t('featuresPage.seoTitle'),
    description: t('featuresPage.seoDescription'),
    blocks,
  };
}

function aboutPage(t, capabilities) {
  const blocks = [
    ['h1', t('aboutPage.title')],
    ['p', t('aboutPage.intro')],
    ['p', t('aboutPage.free')],
    ['h2', t('aboutPage.roadmapTitle')],
  ];
  for (const status of ['working', 'progress', 'next']) {
    blocks.push(['h3', t(`aboutPage.${status}.title`)]);
    blocks.push(['ul', capabilities.items
      .filter((item) => item.status === status)
      .map((item) => t(`capabilities.items.${item.id}`))]);
  }
  blocks.push(['p', t('aboutPage.roadmapNote')]);
  blocks.push(['h2', t('aboutPage.brand.title')]);
  blocks.push(['p', t('aboutPage.brand.description')]);
  return {
    path: '/about',
    title: t('aboutPage.title'),
    description: t('aboutPage.intro'),
    blocks,
  };
}

function forBrandsPage(t, capabilities) {
  return {
    path: '/for-brands',
    title: t('forBrands.seoTitle'),
    description: t('forBrands.seoDescription'),
    blocks: [
      ['h1', t('forBrands.title')],
      ['p', t('forBrands.lead')],
      ['h2', t('forBrands.changeTitle')],
      ['table', {
        head: [t('forBrands.now'), t('forBrands.with')],
        rows: t.rows('forBrands.rows').map((row) => [row.now, row.with]),
      }],
      ['p', t('forBrands.figureCaption')],
      ['h2', t('forBrands.tags.title')],
      ['p', t('forBrands.tags.lead')],
      ['ul', [['qr', 'featuresPage.workingLabel'], ['open', 'aboutPage.progress.title'], ['write', 'aboutPage.next.title']]
        .map(([item, status]) => (
          `${t(`forBrands.tags.items.${item}.title`)} (${t(status)}). ${t(`forBrands.tags.items.${item}.text`)}`
        ))],
      ['h2', t('forBrands.stepsTitle')],
      ['ol', capabilities.manufacturerSteps.map((step) => ({
        href: `/wiki/articles/${step.guide}`,
        label: t(`wikiPage.manufacturerJourney.${step.id}`),
        text: t(`forBrands.steps.${step.id}`),
      }))],
      ['h2', t('forBrands.startTitle')],
      ['p', t('forBrands.startText')],
    ],
  };
}

function orcaPluginPage(t) {
  return {
    path: '/download',
    title: t('downloadPage.seoTitle'),
    description: t('downloadPage.seoDescription'),
    blocks: [
      ['h1', t('downloadPage.pluginTitle')],
      ['p', t('downloadPage.pluginSubtitle')],
      ['h2', t('downloadPage.stepsTitle')],
      ['ol', [1, 2, 3].map((step) => (
        `${t(`downloadPage.step${step}Title`)}. ${t(`downloadPage.step${step}Desc`)}`
      ))],
      ['p', `${t('downloadPage.permissionTitle')} ${t('downloadPage.permissionDesc')}`],
      ['h2', t('downloadPage.whyTitle')],
      ['ul', ['AllInOne', 'Sync', 'Library', 'Verified', 'Full', 'Free'].map((benefit) => (
        `${t(`downloadPage.benefit${benefit}Title`)}. ${t(`downloadPage.benefit${benefit}Desc`)}`
      ))],
      ['h2', t('downloadPage.sectionsLabel')],
      ['ul', [
        { href: '/download/octoprint', label: t('downloadPage.octoTitle'), text: t('downloadPage.octoTagline') },
        { href: '/download/print-farm', label: t('downloadPage.sections.print-farm'), text: t('downloadPage.printFarmDesc') },
        { href: '/download/edge', label: t('edgeSection.title'), text: t('edgeSection.lead') },
      ]],
    ],
  };
}

function octoprintPage(t) {
  return {
    path: '/download/octoprint',
    title: t('downloadPage.octoTitle'),
    description: t('downloadPage.octoDesc'),
    blocks: [
      ['h1', t('downloadPage.octoTitle')],
      ['p', t('downloadPage.octoTagline')],
      ['p', t('downloadPage.octoDesc')],
      ['ul', ['Outbound', 'Sync', 'Usage'].map((feature) => t(`downloadPage.octoFeature${feature}`))],
      ['h2', t('downloadPage.octoInstallTitle')],
      ['ol', [1, 2, 3].map((step) => t(`downloadPage.octoInstall${step}`))],
    ],
  };
}

function printFarmPage(t) {
  return {
    path: '/download/print-farm',
    title: t('downloadPage.sections.print-farm'),
    description: t('downloadPage.printFarmDesc'),
    blocks: [
      ['h1', t('downloadPage.sections.print-farm')],
      ['p', t('downloadPage.printFarmEyebrow')],
      ['p', t('downloadPage.printFarmDesc')],
      ['p', t('downloadPage.printFarmIndependent')],
    ],
  };
}

function edgePage(t) {
  const printers = ['happyHare', 'klipper', 'qidi', 'flashforgeStation', 'flashforgeSingle', 'bambu'];
  return {
    path: '/download/edge',
    title: t('edgeSection.seoTitle'),
    description: t('edgeSection.seoDescription'),
    blocks: [
      ['h1', t('edgeSection.title')],
      ['p', t('edgeSection.lead')],
      ['p', t('edgeSection.forms')],
      ['h2', t('edgeSection.pathsTitle')],
      ['ul', ['printer', 'tags'].map((choice) => (
        `${t(`edgeSection.paths.${choice}.title`)} (${t(`edgeSection.paths.${choice}.status`)}). `
        + t(`edgeSection.paths.${choice}.text`)
      ))],
      ['p', t('edgeSection.map.caption')],
      ['h2', t('edgeSection.whyTitle')],
      ['ul', ['slots', 'oneNode', 'keys'].map((benefit) => (
        `${t(`edgeSection.benefits.${benefit}.title`)}. ${t(`edgeSection.benefits.${benefit}.text`)}`
      ))],
      ['h2', t('edgeSection.supportTitle')],
      ['p', t('edgeSection.supportLead')],
      ['table', {
        head: [t('edgeSection.supportPrinter'), t('edgeSection.supportSees')],
        rows: printers.map((printer) => [
          t(`edgeSection.printers.${printer}.name`),
          t(`edgeSection.printers.${printer}.sees`),
        ]),
      }],
      ['h2', t('edgeSection.otherTitle')],
      ['ul', ['bambu', 'octoprint', 'slicerOpen'].map((other) => t(`edgeSection.other.${other}.text`))],
      ['h2', t('edgeSection.installTitle')],
      ['p', t('edgeSection.installLead')],
      ['ol', ['printer', 'install', 'pair'].map((step) => t(`edgeSection.steps.${step}`))],
      ['p', t('edgeSection.privacy')],
      ['h2', t('edgeKit.guide.title')],
      ['p', t('edgeKit.guide.lead')],
      ['p', t('edgeKit.guide.status')],
      ['h2', t('edgeSection.laterTitle')],
      ['p', t('edgeSection.laterLead')],
    ],
  };
}

/** Every public page that ships as static text, for one language. */
export function buildPublicPages(t, capabilities) {
  const pages = [
    homePage(t, capabilities),
    featuresPage(t, capabilities),
    aboutPage(t, capabilities),
    forBrandsPage(t, capabilities),
    orcaPluginPage(t),
    octoprintPage(t),
    printFarmPage(t),
    edgePage(t),
  ];
  const navigation = siteNavigation(t);
  return pages.map((page) => ({ ...page, blocks: [...page.blocks, navigation] }));
}

const escapeHtml = (value) => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;');

function renderListItem(item, localizeHref) {
  if (typeof item === 'string') {
    return `<li>${escapeHtml(item)}</li>`;
  }
  const link = `<a href="${escapeHtml(localizeHref(item.href))}">${escapeHtml(item.label)}</a>`;
  return item.text ? `<li>${link}: ${escapeHtml(item.text)}</li>` : `<li>${link}</li>`;
}

/** The site navigation block that ends every static page. */
export function renderSiteNavigation(t, localizeHref) {
  const [, items] = siteNavigation(t);
  return `<nav><ul>${items.map((item) => renderListItem(item, localizeHref)).join('')}</ul></nav>`;
}

/** Render a page's blocks as semantic HTML. `localizeHref` adds the language prefix. */
export function renderPageBody(page, localizeHref) {
  const parts = page.blocks.map(([type, value]) => {
    switch (type) {
      case 'h1':
      case 'h2':
      case 'h3':
      case 'p':
        return `<${type}>${escapeHtml(value)}</${type}>`;
      case 'ul':
      case 'ol':
        return `<${type}>${value.map((item) => renderListItem(item, localizeHref)).join('')}</${type}>`;
      case 'link':
        return `<p><a href="${escapeHtml(localizeHref(value.href))}">${escapeHtml(value.label)}</a></p>`;
      case 'nav':
        return `<nav><ul>${value.map((item) => renderListItem(item, localizeHref)).join('')}</ul></nav>`;
      case 'table':
        return [
          '<table><thead><tr>',
          ...value.head.map((cell) => `<th>${escapeHtml(cell)}</th>`),
          '</tr></thead><tbody>',
          ...value.rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join('')}</tr>`),
          '</tbody></table>',
        ].join('');
      default:
        throw new Error(`Unknown public page block: ${type}`);
    }
  });
  return `<main class="fh-static">${parts.join('')}</main>`;
}

/**
 * llms.txt: the product in one plain-text file for programs that read sites
 * on a person's behalf. Written in the default language, with canonical links.
 */
export function buildLlmsTxt(t, capabilities, siteOrigins) {
  const origin = siteOrigins[DEFAULT_LOCALE];
  const url = (path) => `${origin}${withoutQuery(path)}`;
  const itemsWithStatus = (status) => capabilities.items
    .filter((item) => item.status === status)
    .map((item) => `- ${t(`capabilities.items.${item.id}`)}`);
  const lines = [
    '# FilamentHub',
    '',
    `> ${t('featuresPage.lead')}`,
    '',
    `${t('aboutPage.intro')} ${t('aboutPage.free')}`,
    '',
    'The site is served in English and Chinese at https://filamenthub.club and in Russian at https://filamenthub.ru/ru/. Both hosts are the same service and the same account.',
    '',
    '## What works today',
    '',
  ];
  for (const group of capabilities.groups) {
    const working = capabilityLists(capabilities, t, group.id, 'working');
    lines.push(
      `- [${t(`capabilities.groups.${group.id}.title`)}](${url(group.link)}): `
      + `${t(`capabilities.groups.${group.id}.text`)} `
      + `Access: ${t(`featuresPage.access.${group.access}`).toLowerCase()}.`,
    );
    for (const item of working) {
      lines.push(`  - ${item}`);
    }
  }
  lines.push(
    '',
    '## In progress',
    '',
    'Being built or tested. Not available to every user yet.',
    '',
    ...itemsWithStatus('progress'),
    '',
    '## Planned',
    '',
    'No dates are promised.',
    '',
    ...itemsWithStatus('next'),
    '',
    '## Pages',
    '',
    `- [${t('featuresPage.title')}](${url('/features')})`,
    `- [${t('aboutPage.title')}](${url('/about')})`,
    `- [${t('forBrands.title')}](${url('/for-brands')}): ${t('forBrands.lead')}`,
    `- [${t('downloadPage.pluginTitle')}](${url('/download')}): ${t('downloadPage.pluginSubtitle')}`,
    `- [${t('downloadPage.octoTitle')}](${url('/download/octoprint')}): ${t('downloadPage.octoTagline')}`,
    `- [${t('downloadPage.sections.print-farm')}](${url('/download/print-farm')}): ${t('downloadPage.printFarmDesc')}`,
    `- [${t('edgeSection.title')}](${url('/download/edge')}): ${t('edgeSection.lead')}`,
    `- [${t('capabilities.groups.learning.title')}](${url('/wiki')}): ${t('capabilities.groups.learning.text')}`,
    '',
    '## Catalogue data',
    '',
    'Filament cards and print presets change as manufacturers and users update them. Read the live page for current values instead of relying on a stored copy.',
    '',
    '## Legal',
    '',
    `- [User agreement](${url('/user-agreement')})`,
    `- [Privacy policy](${url('/privacy-policy')})`,
    '',
  );
  return lines.join('\n');
}
