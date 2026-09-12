import { describe, expect, it } from 'vitest';

import calculatorPageSource from '../pages/CalculatorPage.tsx?raw';

describe('CalculatorPage mobile responsive structure', () => {
  it('lets material pricing controls stack before restoring their desktop grouping', () => {
    expect(calculatorPageSource).toContain(
      'grid w-full min-w-0 grid-cols-1 gap-2 [&_input]:min-h-11 sm:w-[21rem] sm:grid-cols-2',
    );
    expect(calculatorPageSource).toContain(
      'min-h-11 min-w-0 py-1.5 text-xs sm:max-w-[24rem]',
    );
    expect(calculatorPageSource).toContain(
      'flex min-h-11 w-full min-w-0 items-start justify-between',
    );
    expect(calculatorPageSource).not.toContain('grid w-[21rem] grid-cols-2');
  });

  it('wraps the time summary and stacks time fields before their desktop layout', () => {
    expect(calculatorPageSource).toContain(
      'flex min-h-11 cursor-pointer list-none flex-col items-start gap-1.5',
    );
    expect(calculatorPageSource).toContain(
      'w-full min-w-0 break-words text-xs text-slate-400 sm:w-[13rem] sm:shrink-0',
    );
    expect(calculatorPageSource).toContain(
      '<span className="min-w-0 break-words">{tc(\'adjustPlateTime\')}</span>',
    );
    expect(calculatorPageSource).toContain(
      'grid w-full min-w-0 grid-cols-1 gap-2 border-t border-white/[0.06] px-4 py-3 [&_input]:min-h-11 sm:w-[19rem] sm:grid-cols-3',
    );
    expect(calculatorPageSource).not.toContain('w-[13rem] shrink-0');
    expect(calculatorPageSource).not.toContain('grid w-[19rem] grid-cols-3');
  });
});
