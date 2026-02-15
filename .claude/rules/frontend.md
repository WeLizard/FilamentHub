---
paths:
  - "frontend/**/*"
---

# Frontend правила (React / TypeScript)

## Стек

- React 19 + TypeScript + Vite
- TailwindCSS для стилей
- TanStack Query для API запросов
- react-i18next для локализации (ru, en)
- react-router-dom для маршрутизации

## API клиент

- Все API вызовы через `frontend/src/api/client.ts` (20 модулей)
- Авто-рефреш токена при 401
- Maintenance mode detection при 503

## Компоненты

- 48+ компонентов, 12 страниц
- Модалки: CreatePresetModal (4320 строк), CreatePrinterProfileModal (1868 строк)
- Toast уведомления вместо alert()/confirm()
