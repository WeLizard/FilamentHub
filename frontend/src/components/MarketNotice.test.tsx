import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { MarketNotice } from './MarketNotice';
import type { Filament } from '../types/api';

const material = (extra: Partial<Filament>): Filament =>
  ({ id: 1, name: 'PLA', ...extra }) as Filament;

describe('MarketNotice', () => {
  it('says nothing when no cell describes the reader country', () => {
    // Написать «здесь не продаётся», не имея данных, значит утверждать факт,
    // которого у нас нет.
    const { container } = render(<MarketNotice filament={material({})} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('says nothing about a market it cannot name, whatever the status says', () => {
    // Именно страна решает, есть ли что говорить: без неё статус остаётся
    // сведением ни о чём. Раньше этот случай назывался проверкой «unknown», но
    // до статуса выполнение не доходило вовсе — страны в наборе не было.
    const { container } = render(
      <MarketNotice filament={material({ market_availability: 'unknown' })} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('calls a substituted price a recommendation for that country', () => {
    render(
      <MarketNotice
        filament={material({ market_country: 'RU', market_availability: 'available' })}
      />,
    );
    // Проверяем выбор сообщения, а не его формулировку: тексты живут в локалях.
    // FilamentHub не магазин, поэтому цена подписывается как рекомендация.
    expect(screen.getByText(/market\.priceFor/)).toBeTruthy();
  });

  it('states plainly when somebody says it is not sold there', () => {
    render(
      <MarketNotice
        filament={material({ market_country: 'RS', market_availability: 'unavailable' })}
      />,
    );
    expect(screen.getByText(/market\.notSoldIn/)).toBeTruthy();
  });
});
