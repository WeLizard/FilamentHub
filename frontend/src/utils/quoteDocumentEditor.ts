import type { CrmQuoteLine } from '../types/api';
import { createQuoteBreakdownHtml, createQuoteFooterHtml, createQuoteHeaderHtml, quoteDocumentLayoutCss, quoteDocumentTotalsCss, quoteFooterBaseCss, workBreakdownHtmlEntries } from './quoteDocumentPresentation';
import type { QuoteWorkBreakdownEntry } from './quoteDisclosure';

export interface DraftQuoteDocumentValues {
  language: string;
  quoteNumber: string;
  title: string;
  currency: string;
  validUntil: string | null;
  sellerName: string;
  sellerInn: string;
  sellerPhone: string;
  sellerAdditionalDetails: string;
  sellerIdLabel: string;
  sellerPhoneLabel: string;
  buyerName: string;
  buyerInn: string;
  buyerAddress: string;
  paymentTerms: string;
  lines: CrmQuoteLine[];
  originalLineCount?: number;
  grandTotal: number;
  taxTotal: number;
  taxRatePercent: number | null;
  taxKind: 'tax' | 'vat' | null;
  taxMode: 'hide' | 'included' | 'separate' | null;
  taxDisclosureAmount?: number | null;
  customerDeliveryAmount: number;
  formatCurrency: (amount: number) => string;
  t: (key: string, options?: Record<string, string | number>) => string;
  showCostBreakdown?: boolean;
  costBreakdownNote?: string;
  /** "By work" rows computed from the saved calculation; absent when the breakdown is unavailable. */
  workBreakdown?: QuoteWorkBreakdownEntry[] | null;
}

const parseDocument = (html: string): Document => {
  const document = new DOMParser().parseFromString(html, 'text/html');
  if (!document.querySelector('.page')) {
    throw new Error('This saved quote version has no editable document layout.');
  }
  return document;
};

const textAfterColon = (text: string | null | undefined): string => {
  const value = text?.trim() ?? '';
  const colon = value.indexOf(':');
  if (colon < 0) return '';
  const fieldValue = value.slice(colon + 1).trim();
  return fieldValue === '—' || fieldValue === '-' ? '' : fieldValue;
};

const labelBeforeColon = (text: string | null | undefined): string => {
  const value = text?.trim() ?? '';
  const colon = value.indexOf(':');
  return colon < 0 ? '' : value.slice(0, colon).trim();
};

const snapshotText = (snapshot: Record<string, unknown>, key: string): string => {
  const value = snapshot[key];
  return typeof value === 'string' ? value : '';
};

const legacyPlaceholderValues: Record<string, string[]> = {
  ru: ['Заказчик не указан'],
  en: ['Customer not specified'],
  zh: ['客户未指定'],
};

const cleanOptionalValue = (value: string, documentLanguage: string): string => {
  const trimmed = value.trim();
  const language = documentLanguage.toLowerCase().split('-')[0];
  if (!trimmed || trimmed === '—' || trimmed === '-') return '';
  return legacyPlaceholderValues[language]?.some((placeholder) => placeholder.toLocaleLowerCase() === trimmed.toLocaleLowerCase())
    ? ''
    : trimmed;
};

const readSnapshotOptional = (
  snapshot: Record<string, unknown>,
  key: string,
  htmlFallback: string,
  documentLanguage: string,
): string => Object.prototype.hasOwnProperty.call(snapshot, key)
  ? cleanOptionalValue(snapshotText(snapshot, key), documentLanguage)
  : cleanOptionalValue(htmlFallback, documentLanguage);

export function readDraftQuoteDocumentDefaults(
  html: string,
  sellerSnapshot: Record<string, unknown>,
  customerSnapshot: Record<string, unknown>,
): Pick<DraftQuoteDocumentValues,
  'sellerName' | 'sellerInn' | 'sellerPhone' | 'sellerAdditionalDetails' | 'sellerIdLabel' |
  'sellerPhoneLabel' | 'buyerName' | 'buyerInn' | 'buyerAddress'> {
  const document = parseDocument(html);
  const documentLanguage = document.documentElement.lang || 'en';
  const sellerLines = Array.from(document.querySelectorAll('.header-right .quote-seller-block p:not(.status)'));
  if (!sellerLines.length) sellerLines.push(...Array.from(document.querySelectorAll('.header-right p:not(.status)')));
  const customerBox = document.querySelector('.page .header-right .quote-buyer-block')
    ?? document.querySelector('.page .header + .box');
  const customerLine = customerBox?.querySelector('.box-line')?.textContent?.trim() ?? '';
  const customerDetails = Array.from(customerBox?.querySelectorAll('.box-muted') ?? [])
    .map((line) => line.textContent?.trim() ?? '');
  const snapshotPhone = snapshotText(sellerSnapshot, 'phone');
  const lineTexts = sellerLines.map((line) => line.textContent?.trim() ?? '');
  const sellerNameIndex = Math.max(0, lineTexts.findIndex((line) => /^исполнитель\s*:/i.test(line) || /^provider\s*:/i.test(line) || /^执行方\s*:/i.test(line))) + 1;
  const innIndex = lineTexts.findIndex((line) => /^(ИНН|tax id|纳税人识别号|税号)\s*:/i.test(line));
  const phoneIndex = sellerLines.findIndex((line) => {
    const text = line.textContent?.trim() ?? '';
    const label = labelBeforeColon(text).toLocaleLowerCase();
    return (snapshotPhone && textAfterColon(text) === snapshotPhone)
      || /phone|telephone|телефон|电话/i.test(label);
  });
  const sellerPhoneLine = sellerLines[phoneIndex]?.textContent ?? '';
  const sellerInnLine = lineTexts[innIndex] ?? '';
  const excludedSellerIndexes = new Set([0, sellerNameIndex, innIndex, phoneIndex]);

  return {
    sellerName: snapshotText(sellerSnapshot, 'name') || lineTexts[sellerNameIndex] || '',
    sellerInn: readSnapshotOptional(sellerSnapshot, 'inn', textAfterColon(sellerInnLine), documentLanguage),
    sellerPhone: readSnapshotOptional(sellerSnapshot, 'phone', textAfterColon(sellerPhoneLine), documentLanguage),
    sellerAdditionalDetails: lineTexts.filter((_, index) => !excludedSellerIndexes.has(index)).filter(Boolean).join('\n'),
    sellerIdLabel: labelBeforeColon(sellerInnLine),
    sellerPhoneLabel: labelBeforeColon(sellerPhoneLine),
    buyerName: readSnapshotOptional(customerSnapshot, 'name', customerLine, documentLanguage),
    buyerInn: readSnapshotOptional(customerSnapshot, 'inn', textAfterColon(customerDetails.find((line) => /^(ИНН|tax id|纳税人识别号|税号)\s*:/i.test(line))), documentLanguage),
    buyerAddress: readSnapshotOptional(customerSnapshot, 'address', textAfterColon(customerDetails.find((line) => /^(адрес|address|地址)\s*:/i.test(line))), documentLanguage),
  };
}

const updateCustomerField = (
  document: Document,
  box: Element,
  fieldClass: string,
  label: string,
  value: string,
): void => {
  const legacyFieldMatcher = fieldClass === 'draft-buyer-inn'
    ? /^(ИНН|tax id|纳税人识别号|税号)\s*:/i
    : /^(адрес|address|地址)\s*:/i;
  let element = box.querySelector<HTMLElement>(`.${fieldClass}`)
    ?? Array.from(box.querySelectorAll<HTMLElement>('.box-muted')).find((candidate) => (
      legacyFieldMatcher.test(candidate.textContent?.trim() ?? '')
    ))
    ?? null;
  if (!value.trim()) {
    element?.remove();
    return;
  }
  if (!element) {
    element = document.createElement('p');
    element.className = 'box-muted';
    box.append(element);
  }
  element.className = `box-muted ${fieldClass}`;
  element.textContent = `${label}: ${value.trim()}`;
};

const installQuoteHeader = (document: Document, values: DraftQuoteDocumentValues): void => {
  let header = document.querySelector<HTMLElement>('header.document-header');
  if (!header) {
    header = document.createElement('header');
    header.className = 'document-header';
    document.body.insertBefore(header, document.querySelector('.page'));
  }
  header.outerHTML = createQuoteHeaderHtml(
    values.t('profilePage.calculator.quoteHeaderNoticeBefore'),
    values.t('profilePage.calculator.quoteHeaderNoticeAfter'),
  );
};

const installQuoteFooter = (document: Document, values: DraftQuoteDocumentValues): void => {
  let footer = document.querySelector<HTMLElement>('footer.document-footer');
  if (!footer) {
    footer = document.createElement('footer');
    footer.className = 'document-footer';
    document.body.insertBefore(footer, document.querySelector('.page'));
  }
  footer.outerHTML = createQuoteFooterHtml(values.t('profilePage.calculator.quoteFooterNote'));
};

const installPresentationStyles = (document: Document): void => {
  const style = document.querySelector('style');
  if (!style) throw new Error('This saved quote version has no editable style block.');
  style.textContent = `${style.textContent ?? ''}
      h2 { font-size: 18px; }
      .document-quote-title { margin: 3px 0 4px; font-size: 15px; font-weight: 600; }
      .draft-customer-empty { display: none !important; }
      ${quoteFooterBaseCss}
      ${quoteDocumentTotalsCss}
      @media screen { body { display: flex; flex-direction: column; } .page { order: 0; } .document-footer { order: 1; width: 210mm; margin: 0 auto; padding: 5mm 20mm; background: white; } }
      @media print {
      @page { size: A4; margin: 24mm 14mm 32mm; @top-center { content: element(quoteHeader); vertical-align: bottom; width: 100%; } @bottom-center { content: element(quoteFooter); vertical-align: top; width: 100%; } }
      body { background: white; }
      .page { width: 100%; min-height: auto; margin: 0; padding: 0; box-shadow: none; }
      tr, .box, .included { break-inside: avoid; }
      .document-header { position: fixed; top: -14mm; left: 0; right: 0; height: 10mm; margin: 0; }
      .document-header { position: running(quoteHeader); width: 100%; height: auto; margin: 0; padding: 0 0 2mm; }
      .document-footer { position: fixed; bottom: -24mm; left: 0; right: 0; height: 20mm; margin: 0; }
      .document-footer { position: running(quoteFooter); width: 100%; height: auto; margin: 0; padding: 4mm 0 0; }
      }
      ${quoteDocumentLayoutCss}
    `;
};

export function buildEditedDraftQuoteHtml(
  html: string,
  values: DraftQuoteDocumentValues,
): string {
  const document = parseDocument(html);
  document.documentElement.lang = values.language;
  const page = document.querySelector<HTMLElement>('.page');
  const header = page?.querySelector<HTMLElement>('.header');
  const headerTitle = header?.querySelector('h2');
  if (!page || !header || !headerTitle) throw new Error('The saved quote header is incomplete.');

  let quoteTitle = header.querySelector<HTMLElement>('.document-quote-title');
  if (!quoteTitle) {
    quoteTitle = document.createElement('p');
    quoteTitle.className = 'document-quote-title';
    headerTitle.after(quoteTitle);
  }
  quoteTitle.textContent = values.title.trim();

  const sellerBlock = header.querySelector<HTMLElement>('.header-right');
  const customerBox = header.querySelector<HTMLElement>('.quote-buyer-block')
    ?? header.nextElementSibling as HTMLElement | null;
  if (!sellerBlock || !customerBox || (!customerBox.classList.contains('box') && !customerBox.classList.contains('quote-buyer-block'))) {
    throw new Error('The saved quote party details are incomplete.');
  }
  const sellerSource = sellerBlock.querySelector('.quote-seller-block') ?? sellerBlock;
  const existingSellerLines = Array.from(sellerSource.querySelectorAll('p:not(.status)'));
  const executorLabel = existingSellerLines[0]?.cloneNode(true) as HTMLElement | undefined;
  const idLabel = values.sellerIdLabel || labelBeforeColon(existingSellerLines[2]?.textContent) || 'Tax ID';
  const phoneLabel = values.sellerPhoneLabel || labelBeforeColon(existingSellerLines.at(-1)?.textContent) || 'Phone';
  const sellerExtraLines = values.sellerAdditionalDetails.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  sellerBlock.replaceChildren();
  if (executorLabel) sellerBlock.append(executorLabel);
  const sellerName = document.createElement('p');
  sellerName.textContent = values.sellerName.trim() || '—';
  sellerBlock.append(sellerName);
  if (values.sellerInn.trim()) {
    const sellerId = document.createElement('p');
    sellerId.textContent = `${idLabel}: ${values.sellerInn.trim()}`;
    sellerBlock.append(sellerId);
  }
  for (const line of sellerExtraLines) {
    const paragraph = document.createElement('p');
    paragraph.textContent = line;
    sellerBlock.append(paragraph);
  }
  if (values.sellerPhone.trim()) {
    const sellerPhone = document.createElement('p');
    sellerPhone.textContent = `${phoneLabel}: ${values.sellerPhone.trim()}`;
    sellerBlock.append(sellerPhone);
  }

  const customerName = customerBox.querySelector<HTMLElement>('.box-line');
  const normalizedBuyerName = cleanOptionalValue(values.buyerName, values.language);
  if (customerName) customerName.textContent = normalizedBuyerName;
  updateCustomerField(document, customerBox, 'draft-buyer-inn', values.t('profilePage.calculator.quoteInn'), values.buyerInn);
  updateCustomerField(document, customerBox, 'draft-buyer-address', values.t('profilePage.calculator.quoteAddress'), values.buyerAddress);
  customerBox.querySelectorAll<HTMLElement>('.party-label, .box-title').forEach((label) => label.remove());
  const buyerLabel = document.createElement('p');
  buyerLabel.className = 'party-label';
  buyerLabel.textContent = `${values.t('profilePage.calculator.quoteCustomer')}:`;
  customerBox.prepend(buyerLabel);
  customerBox.className = 'quote-buyer-block';
  sellerBlock.append(customerBox);
  if (!normalizedBuyerName && !values.buyerInn.trim() && !values.buyerAddress.trim()) customerBox.classList.add('draft-customer-empty');

  const boxes = Array.from(page.querySelectorAll<HTMLElement>('.box'));
  const validUntilBox = boxes.find((box) => box.querySelector('.box-line strong'))
    ?? page.querySelector<HTMLElement>('.draft-valid-until');
  const existingMeta = page.querySelector<HTMLElement>('.quote-meta-row');
  let validUntil = validUntilBox?.querySelector<HTMLElement>('.box-line strong')
    ?? existingMeta?.querySelector<HTMLElement>('[data-quote-validity] strong');
  if (!validUntilBox && !existingMeta) throw new Error('The saved quote expiry field is missing.');
  let formattedValidUntil = '';
  if (values.validUntil) {
    if (!validUntil) {
      validUntil = document.createElement('strong');
    }
    const [year, month, day] = values.validUntil.split('-').map(Number);
    validUntil.textContent = new Intl.DateTimeFormat(values.language, { dateStyle: 'long' }).format(new Date(year, month - 1, day));
    formattedValidUntil = validUntil.textContent;
  } else {
    validUntil?.closest('[data-quote-validity]')?.remove();
    validUntil?.remove();
  }
  const issueDate = header.querySelector<HTMLElement>('.date')?.textContent?.trim()
    ?? existingMeta?.querySelector<HTMLElement>('[data-quote-issue-date]')?.textContent?.trim()
    ?? '';
  header.querySelector('.date')?.remove();
  const metaRow = existingMeta ?? document.createElement('div');
  metaRow.className = 'quote-meta-row';
  const dateCell = document.createElement('p');
  dateCell.dataset.quoteIssueDate = '';
  dateCell.textContent = issueDate;
  const oldDateCell = metaRow.querySelector('[data-quote-issue-date]');
  if (oldDateCell) oldDateCell.replaceWith(dateCell); else metaRow.prepend(dateCell);
  if (formattedValidUntil) {
    const expiryCell = document.createElement('p');
    expiryCell.dataset.quoteValidity = '';
    expiryCell.append(`${values.t('profilePage.calculator.quoteValidUntil')}: `);
    const expiryValue = document.createElement('strong');
    expiryValue.textContent = formattedValidUntil;
    expiryCell.append(expiryValue);
    const oldExpiry = metaRow.querySelector('[data-quote-validity]');
    if (oldExpiry) oldExpiry.replaceWith(expiryCell); else metaRow.append(expiryCell);
  }
  header.after(metaRow);
  validUntilBox?.remove();

  const paymentLabel = values.t('profilePage.calculator.quotePaymentTerms');
  const paymentBox = boxes.find((box) => box !== customerBox && box !== validUntilBox && box.querySelector('.box-title') !== null);
  if (values.paymentTerms.trim()) {
    const termsBox = paymentBox ?? document.createElement('div');
    termsBox.className = 'box';
    if (!paymentBox) metaRow.after(termsBox);
    let termsTitle = termsBox.querySelector<HTMLElement>('.box-title');
    if (!termsTitle) {
      termsTitle = document.createElement('p');
      termsTitle.className = 'box-title';
      termsBox.append(termsTitle);
    }
    termsTitle.textContent = `${paymentLabel}:`;
    let termsText = termsBox.querySelector<HTMLElement>('.box-line');
    if (!termsText) {
      termsText = document.createElement('p');
      termsText.className = 'box-line';
      termsBox.append(termsText);
    }
    termsText.textContent = values.paymentTerms.trim();
  } else {
    paymentBox?.remove();
  }

  const tableBody = page.querySelector<HTMLTableSectionElement>('table tbody');
  if (!tableBody) throw new Error('The saved quote table body is missing.');
  const displayLines = values.lines.filter((line) => line.source_data?.quote_component !== 'modeling' && line.source_data?.quote_component !== 'postprocessing');
  const bodyRows = Array.from(tableBody.querySelectorAll<HTMLTableRowElement>('tr'));
  if (values.originalLineCount !== undefined && bodyRows.length !== values.originalLineCount && bodyRows.length !== displayLines.length) {
    throw new Error('The saved quote lines do not match its structured version.');
  }
  while (bodyRows.length < displayLines.length) {
    const template = bodyRows.at(-1);
    if (!template) throw new Error('The saved quote table has no row to extend.');
    const row = template.cloneNode(true) as HTMLTableRowElement;
    tableBody.append(row);
    bodyRows.push(row);
  }
  while (bodyRows.length > displayLines.length) bodyRows.pop()?.remove();
  bodyRows.forEach((row, index) => {
    const line = displayLines[index];
    const cells = Array.from(row.cells);
    if (cells.length < 5) throw new Error('A saved quote line has an unexpected layout.');
    cells[0].textContent = String(index + 1);
    const name = document.createElement('strong');
    name.textContent = line.title;
    cells[1].replaceChildren(name);
    if (line.details.length) {
      const details = document.createElement('div');
      details.className = 'text-xs text-gray-500 mt-1';
      details.textContent = line.details.join(' · ');
      cells[1].append(details);
    }
    cells[2].textContent = String(line.quantity);
    cells[3].textContent = values.formatCurrency(line.unit_price);
    cells[4].textContent = values.formatCurrency(Math.round((line.quantity * line.unit_price) * 100 + Number.EPSILON) / 100);
  });
  const table = page.querySelector<HTMLTableElement>('table');
  const tableFooter = table?.querySelector('tfoot');
  const totalRow = tableFooter?.querySelector<HTMLTableRowElement>('.total-row');
  const oldTotals = page.querySelector<HTMLElement>('.quote-totals');
  if (!table || (!totalRow && !oldTotals)) throw new Error('The saved quote total row is missing.');
  const legacySummaryRows = oldTotals
    ? Array.from(oldTotals.querySelectorAll<HTMLElement>('.quote-total-row:not(.quote-grand-total)'))
    : Array.from(tableFooter?.querySelectorAll<HTMLTableRowElement>('tr') ?? []).filter((row) => row !== totalRow);
  const roundMoney = (value: number) => Math.round(value * 100 + Number.EPSILON) / 100;
  const displayTaxTotal = values.taxTotal > 0 ? roundMoney(values.taxTotal) : 0;
  const disclosureAmount = values.taxDisclosureAmount == null ? displayTaxTotal : roundMoney(values.taxDisclosureAmount);
  const mode = values.taxMode ?? (displayTaxTotal > 0 ? 'separate' : 'hide');
  const totals = oldTotals ?? document.createElement('div');
  totals.className = 'quote-totals';
  totals.dataset.quoteTotals = '';
  totals.replaceChildren();
  const appendTotalRow = (kind: string, label: string, amount: string, grand = false): void => {
    const row = document.createElement('div');
    row.className = `quote-total-row${grand ? ' quote-grand-total' : ''}`;
    row.dataset.quoteTotalKind = kind;
    const labelNode = document.createElement('span');
    labelNode.textContent = label;
    const amountNode = grand ? document.createElement('strong') : document.createElement('span');
    amountNode.textContent = amount;
    row.append(labelNode, amountNode);
    totals.append(row);
  };
  if (mode === 'included') {
    if (disclosureAmount > 0) {
      const taxLabel = values.t(values.taxKind === 'vat' ? 'profilePage.calculator.quoteTaxVat' : 'profilePage.calculator.quoteTaxGeneric');
      appendTotalRow('included-tax', `${values.t('profilePage.calculator.quoteTaxIncludedAmount', { taxLabel }).replace('{{taxLabel}}', taxLabel)}:`, values.formatCurrency(disclosureAmount));
    }
  } else if (mode === 'separate') {
    appendTotalRow('net', `${values.t('profilePage.calculator.quoteSubtotal')}:`, values.formatCurrency(roundMoney(values.grandTotal - displayTaxTotal - values.customerDeliveryAmount)));
    const taxLabel = values.t(values.taxKind === 'vat' ? 'profilePage.calculator.quoteTaxVat' : 'profilePage.calculator.quoteTaxGeneric');
    appendTotalRow('tax', `${values.t('profilePage.calculator.quoteTaxFromEstimate', { taxLabel }).replace('{{taxLabel}}', taxLabel)}:`, values.formatCurrency(displayTaxTotal));
  } else if (values.taxMode === null) {
    legacySummaryRows.forEach((legacyRow) => {
      const cells = legacyRow instanceof HTMLTableRowElement ? Array.from(legacyRow.cells) : Array.from(legacyRow.querySelectorAll<HTMLElement>(':scope > span, :scope > strong'));
      if (cells.length < 2) return;
      const kind = legacyRow.dataset.quoteTotalKind ?? 'legacy';
      appendTotalRow(kind, cells[0].textContent?.trim() ?? '', cells.at(-1)?.textContent?.trim() ?? '');
    });
  }
  appendTotalRow('total', `${values.t('profilePage.calculator.totalCost')}:`, values.formatCurrency(values.grandTotal), true);
  tableFooter?.remove();
  if (!oldTotals) table.after(totals);

  document.querySelector('.quote-breakdown')?.remove();
  if (values.showCostBreakdown && values.workBreakdown?.length) {
    const entries = workBreakdownHtmlEntries(values.workBreakdown, values.t, values.formatCurrency, values.language);
    const wrapper = document.createElement('div');
    wrapper.innerHTML = createQuoteBreakdownHtml(values.t('profilePage.calculator.quoteBreakdownLabel'), entries, values.costBreakdownNote ?? '');
    if (wrapper.firstElementChild) totals.after(wrapper.firstElementChild);
  }

  page.querySelectorAll<HTMLElement>('.box[style*="background: transparent"]').forEach((box) => box.remove());
  document.querySelectorAll('.signatures, .footer-note').forEach((element) => element.remove());
  document.title = `${headerTitle.textContent?.trim() ?? values.quoteNumber} · ${values.title}`;
  installQuoteHeader(document, values);
  installQuoteFooter(document, values);
  installPresentationStyles(document);
  return `<!doctype html>\n${document.documentElement.outerHTML}`;
}
