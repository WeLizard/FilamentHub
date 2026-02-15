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
- Base URL: `/api/v1` (относительный, проксируется через Vite или nginx)

## Компоненты

- 48+ компонентов, 12 страниц
- Модалки: CreatePresetModal (4320 строк), CreatePrinterProfileModal (1868 строк)
- Toast уведомления вместо alert()/confirm()

## i18n

- Все строки через `useTranslation()` / `t('key')`
- Локали: `frontend/src/locales/ru/translation.json`, `frontend/src/locales/en/translation.json`
- Ключи по формату: `pageName.section.element` (например `catalogPage.errorLoginRequired`)

## Vite proxy

- Dev без Docker: proxy target `http://localhost:8000`
- Dev с Docker: proxy target задаётся через `VITE_PROXY_TARGET` env variable
- Prod: nginx проксирует `/api` → backend, Vite proxy не используется
