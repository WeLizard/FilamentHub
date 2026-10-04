import { describe, expect, it } from 'vitest';
import { buildEditedDraftQuoteHtml, readDraftQuoteDocumentDefaults } from '../utils/quoteDocumentEditor';

const oldHtml = `<!doctype html><html lang="ru"><head><title>Old quote</title><style>.page{width:210mm}.document-footer{position:fixed;bottom:-24mm}</style></head><body>
  <footer class="document-footer"><p class="footer-note">Old service wording</p></footer>
  <div class="page"><div class="header"><div><h2>Коммерческое предложение КП-20260801-00003</h2><p class="subtitle">Предварительный расчёт</p><p class="date">1 августа 2026 г.</p></div><div class="header-right"><p><strong>Исполнитель:</strong></p><p>Lizard</p><p class="status">Служебное сообщение FilamentHub</p><p>ИНН: 123</p><p>Адрес: Example</p><p>Телефон: +7 900</p><p>Банк: Account</p></div></div>
  <div class="box"><p class="box-title">Заказчик:</p><p class="box-line">Customer</p><p class="box-muted">ИНН: 987</p><p class="box-muted">Адрес: Customer address</p></div>
  <div class="box"><p class="box-title">Условия оплаты:</p><p class="box-line">По согласованию</p></div>
  <div class="box"><p class="box-line">Расчёт актуален до: <strong>15 августа 2026 г.</strong></p></div>
  <table><tbody><tr><td>1</td><td><strong>Old item</strong><div>Preserved detail</div></td><td>1</td><td>910,00</td><td>910,00</td></tr></tbody><tfoot><tr><td colspan="4">Налог включён</td><td>910,00</td></tr><tr class="total-row"><td colspan="4">Total</td><td>910,00</td></tr></tfoot></table>
  <div class="included"><p>Состав расчёта</p></div><div class="box" style="background: transparent; border-color: #e5e7eb;"><p class="box-muted">Старый текст со ст. 437 ГК РФ</p><p class="box-muted">Дополнительная офертная формулировка</p></div><div class="signatures">Старые подписи</div></div></body></html>`;

const tr = (key: string, options?: Record<string, string | number>) => ({
  'profilePage.calculator.quoteTaxStatus': 'Calculated using the user’s settings.',
  'profilePage.calculator.quoteHeaderNoticeBefore': 'Estimate prepared in',
  'profilePage.calculator.quoteHeaderNoticeAfter': 'using the user’s data and settings.',
  'profilePage.calculator.quoteFooterNote': 'Not a payment or tax invoice.',
  'profilePage.calculator.quotePaymentTerms': 'Payment terms',
  'profilePage.calculator.totalCost': 'Total cost',
  'profilePage.calculator.quoteBuyerFallback': 'Customer not specified',
  'profilePage.calculator.quoteInn': 'Tax ID',
  'profilePage.calculator.quoteAddress': 'Address',
  'profilePage.calculator.quoteValidUntil': 'Estimate valid until',
  'profilePage.calculator.quoteTaxGeneric': 'Tax',
  'profilePage.calculator.quoteTaxVat': 'VAT',
  'profilePage.calculator.quoteTaxIncluded': 'Included in total',
  'profilePage.calculator.quoteTaxIncludedAmount': 'Includes {{taxLabel}}',
  'profilePage.calculator.quoteTaxFromEstimate': '{{taxLabel}} from saved estimate (delivery excluded)',
  'profilePage.calculator.quoteDelivery': 'Customer delivery',
  'profilePage.calculator.quoteSubtotal': 'Work subtotal before tax',
  'profilePage.calculator.quoteLegalStatus': 'Document purpose',
  'profilePage.calculator.quoteDisclaimerText': 'Preliminary estimate. The contract is agreed separately.',
} as Record<string, string>)[key]?.replace('{{taxLabel}}', String(options?.taxLabel ?? "")) ?? key;

const baseValues = () => {
  const defaults = readDraftQuoteDocumentDefaults(oldHtml, {}, {});
  return {
    language: 'ru', quoteNumber: 'КП-20260801-00003', title: 'Correct title', currency: 'RUB', validUntil: '2026-08-15',
    sellerName: defaults.sellerName, sellerInn: '', sellerPhone: '', sellerAdditionalDetails: defaults.sellerAdditionalDetails,
    sellerIdLabel: defaults.sellerIdLabel, sellerPhoneLabel: defaults.sellerPhoneLabel,
    buyerName: defaults.buyerName, buyerInn: '', buyerAddress: '', paymentTerms: 'По согласованию',
    lines: [{ id: 1, position: 1, title: 'Correct item', details: ['Preserved detail'], quantity: 1, unit: 'pcs', unit_price: 910, total_price: 910, source_data: null }],
    grandTotal: 910, taxTotal: 0, taxRatePercent: null, taxKind: null, taxMode: 'hide' as const, customerDeliveryAmount: 0, formatCurrency: (amount: number) => String(amount), t: tr,
    originalLineCount: 1,
  };
};

describe('saved quote draft editor', () => {
  it('upgrades legacy documents idempotently, retains seller extras, clears optional fields, and keeps the expiry editable', () => {
    const defaults = readDraftQuoteDocumentDefaults(oldHtml, {}, {});
    expect(defaults).toMatchObject({
      sellerName: 'Lizard', sellerInn: '123', sellerPhone: '+7 900',
      sellerAdditionalDetails: 'Адрес: Example\nБанк: Account',
      buyerName: 'Customer', buyerInn: '987', buyerAddress: 'Customer address',
    });

    const updated = buildEditedDraftQuoteHtml(oldHtml, baseValues());
    const document = new DOMParser().parseFromString(updated, 'text/html');
    expect(document.querySelector('h2')?.textContent).toContain('КП-20260801-00003');
    expect(document.querySelector('.document-quote-title')?.textContent).toBe('Correct title');
    expect(document.querySelector('table tbody strong')?.textContent).toBe('Correct item');
    expect(document.querySelector('table tbody div')?.textContent).toBe('Preserved detail');
    expect(document.querySelector('.header-right')?.textContent).toContain('Банк: Account');
    expect(document.querySelector('.header-right')?.textContent).not.toContain('Служебное сообщение');
    expect(document.querySelector('.header-right')?.textContent).not.toContain('ИНН:');
    expect(document.querySelector('.header-right')?.textContent).not.toContain('Телефон:');
    expect(document.querySelector('.quote-meta-row [data-quote-validity] strong')?.textContent).toBe('15 августа 2026 г.');
    expect(document.querySelector('table tfoot')).toBeNull();
    expect(document.querySelectorAll('.quote-totals .quote-total-row')).toHaveLength(1);
    expect(document.querySelector('[style*="background: transparent"]')).toBeNull();
    expect(document.querySelector('footer.document-footer')?.textContent).toContain('Not a payment or tax invoice.');
    expect(document.querySelector('.quote-meta-row')?.textContent).toContain('15 августа 2026 г.');
    expect(document.querySelector('.signatures, .footer-note')).toBeNull();
    expect(document.querySelector('.header-right .quote-buyer-block .box-muted')).toBeNull();
    expect(document.querySelectorAll('.header-right .quote-buyer-block .party-label')).toHaveLength(1);
    expect(document.querySelector('header.document-header .header-brand svg path')?.getAttribute('fill')).toBe('#475569');
    expect(document.querySelector('header.document-header')?.textContent).toContain('Estimate prepared in');

    const secondValues = { ...baseValues(), validUntil: null, paymentTerms: 'Updated conditions' };
    const twiceEdited = buildEditedDraftQuoteHtml(updated, secondValues);
    const secondDocument = new DOMParser().parseFromString(twiceEdited, 'text/html');
    expect(secondDocument.querySelector('.quote-meta-row [data-quote-validity]')).toBeNull();
    expect(secondDocument.querySelectorAll('.box-title')).toHaveLength(1);
    expect(secondDocument.body.textContent).toContain('Updated conditions');
    expect(secondDocument.querySelector('.header-right .quote-buyer-block .box-muted')).toBeNull();
    expect(oldHtml).toContain('Старый текст со ст. 437 ГК РФ');
  });

  it('keeps confirmed tax lines and rounds fractional line totals before summing', () => {
    const values = {
      ...baseValues(), language: 'en', validUntil: '2026-08-15', paymentTerms: '', taxTotal: 200, grandTotal: 1720.19, taxKind: 'vat' as const, taxMode: 'separate' as const,
      taxRatePercent: 13,
      lines: [
        { id: 1, position: 1, title: 'Line A', details: [], quantity: 1.5, unit: 'pcs', unit_price: 1000.11, total_price: 1500.17, source_data: null },
        { id: 2, position: 2, title: 'Line B', details: [], quantity: 2, unit: 'pcs', unit_price: 10.01, total_price: 20.02, source_data: null },
      ],
      originalLineCount: 2,
    };
    const taxHtml = oldHtml.replace('<tr><td>1</td><td><strong>Old item</strong><div>Preserved detail</div></td><td>1</td><td>910,00</td><td>910,00</td></tr>', '<tr><td>1</td><td><strong>Old item</strong></td><td>1.5</td><td>1000.11</td><td>1500.17</td></tr><tr><td>2</td><td><strong>Second item</strong></td><td>2</td><td>10.01</td><td>20.02</td></tr>')
      .replace('Налог включён</td><td>910,00', 'Net amount:</td><td>710.00')
      .replace('<tr class="total-row">', '<tr><td colspan="4">Tax 13%:</td><td>200.00</td></tr><tr class="total-row">');
    const document = new DOMParser().parseFromString(buildEditedDraftQuoteHtml(taxHtml, values), 'text/html');
    const footerRows = Array.from(document.querySelectorAll('.quote-totals .quote-total-row')).map((row) => row.textContent?.replace(/\s+/g, ' ').trim());
    expect(footerRows).toEqual(['Work subtotal before tax:1520.19', 'VAT from saved estimate (delivery excluded):200', 'Total cost:1720.19']);
    expect(document.querySelectorAll('table tbody tr')).toHaveLength(2);
    expect(document.querySelector('table tbody tr:nth-child(1) td:last-child')?.textContent).toBe('1500.17');
    expect(document.querySelector('table tbody tr:nth-child(2) td:last-child')?.textContent).toBe('20.02');
  });

  it('renders the explicit saved tax split from the version amount', () => {
    const withSplit = oldHtml.replace('Налог включён</td><td>910,00', 'Net amount:</td><td>100.00')
      .replace('<tr class="total-row">', '<tr><td colspan="4">Tax 13%:</td><td>13.00</td></tr><tr class="total-row">');
    const values = {
      ...baseValues(), language: 'en', paymentTerms: '', taxTotal: 13, taxRatePercent: 13, taxKind: 'vat' as const, taxMode: 'separate' as const, grandTotal: 113,
      lines: [{ id: 1, position: 1, title: 'Line', details: [], quantity: 1, unit: 'pcs', unit_price: 113, total_price: 113, source_data: null }],
    };
    const document = new DOMParser().parseFromString(buildEditedDraftQuoteHtml(withSplit, values), 'text/html');
    const rows = Array.from(document.querySelectorAll('.quote-totals .quote-total-row')).map((row) => row.textContent?.replace(/\s+/g, ' ').trim());
    expect(rows).toEqual(['Work subtotal before tax:100', 'VAT from saved estimate (delivery excluded):13', 'Total cost:113']);
  });

  it('keeps a Russian separate-tax subtotal on two successive legacy draft edits', () => {
    const values = {
      ...baseValues(), taxTotal: 200, taxDisclosureAmount: 200, taxRatePercent: 20,
      taxKind: 'tax' as const, taxMode: 'separate' as const, grandTotal: 1110,
      lines: [{ id: 1, position: 1, title: 'Line', details: [], quantity: 1, unit: 'pcs', unit_price: 910, total_price: 910, source_data: null }],
      t: (key: string, options?: Record<string, string | number>) => ({
        'profilePage.calculator.quoteSubtotal': 'Стоимость работ без налога',
        'profilePage.calculator.quoteTaxGeneric': 'Налог',
        'profilePage.calculator.quoteTaxFromEstimate': '{{taxLabel}} по сохранённому расчёту (без доставки)',
        'profilePage.calculator.totalCost': 'Итого',
      } as Record<string, string>)[key]?.replace('{{taxLabel}}', String(options?.taxLabel ?? "")) ?? tr(key, options),
    };
    const first = buildEditedDraftQuoteHtml(oldHtml, values);
    const second = buildEditedDraftQuoteHtml(first, values);
    for (const html of [first, second]) {
      const document = new DOMParser().parseFromString(html, 'text/html');
      const rows = Array.from(document.querySelectorAll('.quote-totals .quote-total-row')).map((row) => row.textContent?.replace(/\s+/g, ' ').trim());
      expect(document.querySelector('table tfoot')).toBeNull();
      expect(rows).toEqual([
        'Стоимость работ без налога:910',
        'Налог по сохранённому расчёту (без доставки):200',
        'Итого:1110',
      ]);
    }
  });

  it('renders included tax as informational only and keeps customer delivery outside the tax subtotal', () => {
    const values = {
      ...baseValues(), language: 'en', taxTotal: 0, taxDisclosureAmount: 200,
      taxKind: 'vat' as const, taxMode: 'included' as const, customerDeliveryAmount: 30, grandTotal: 1230,
      lines: [
        { id: 1, position: 1, title: 'Part', details: [], quantity: 1, unit: 'pcs', unit_price: 1200, total_price: 1200, source_data: null },
        { id: 2, position: 2, title: 'Customer delivery', details: [], quantity: 1, unit: 'pcs', unit_price: 30, total_price: 30, source_data: { quote_component: 'customer_delivery' } },
      ],
    };
    const included = new DOMParser().parseFromString(buildEditedDraftQuoteHtml(oldHtml, values), 'text/html');
    const includedRows = Array.from(included.querySelectorAll('.quote-totals .quote-total-row')).map((row) => row.textContent?.replace(/\s+/g, ' ').trim());
    expect(includedRows).toEqual(['Includes VAT:200', 'Total cost:1230']);
    expect(included.querySelectorAll('table tbody tr')).toHaveLength(2);
    expect(included.querySelector('table tbody tr:nth-child(2) td:last-child')?.textContent).toBe('30');

    const separateValues = {
      ...values, taxMode: 'separate' as const, taxTotal: 200,
      lines: [
        { ...values.lines[0], unit_price: 1000, total_price: 1000 },
        values.lines[1],
      ],
    };
    const separate = new DOMParser().parseFromString(buildEditedDraftQuoteHtml(oldHtml, separateValues), 'text/html');
    const separateRows = Array.from(separate.querySelectorAll('.quote-totals .quote-total-row')).map((row) => row.textContent?.replace(/\s+/g, ' ').trim());
    expect(separateRows).toEqual(['Work subtotal before tax:1000', 'VAT from saved estimate (delivery excluded):200', 'Total cost:1230']);
    expect(separate.querySelector('table tbody tr:nth-child(2) td:last-child')?.textContent).toBe('30');
  });

  it('treats explicit empty snapshot fields and document-language buyer placeholders as empty', () => {
    const legacy = oldHtml.replace('Customer</p>', 'Заказчик не указан</p>');
    const defaults = readDraftQuoteDocumentDefaults(legacy, { inn: '', phone: '' }, { name: '', inn: '', address: '' });
    expect(defaults).toMatchObject({ sellerInn: '', sellerPhone: '', buyerName: '', buyerInn: '', buyerAddress: '' });

    const values = {
      ...baseValues(), ...defaults, sellerInn: defaults.sellerInn, sellerPhone: defaults.sellerPhone,
      buyerName: defaults.buyerName, buyerInn: defaults.buyerInn, buyerAddress: defaults.buyerAddress,
    };
    const edited = buildEditedDraftQuoteHtml(legacy, values);
    const document = new DOMParser().parseFromString(edited, 'text/html');
    expect(document.querySelector('.header-right')?.textContent).not.toMatch(/ИНН:\s*123|Телефон:\s*\+7 900/);
    expect(document.querySelector('.draft-customer-empty')?.textContent).not.toContain('Заказчик не указан');
    expect(readDraftQuoteDocumentDefaults(edited, { inn: '', phone: '' }, { name: '', inn: '', address: '' }))
      .toMatchObject({ sellerInn: '', sellerPhone: '', buyerName: '', buyerInn: '', buyerAddress: '' });
  });
});
