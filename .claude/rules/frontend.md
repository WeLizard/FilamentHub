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

- 57 компонентов, 13 страниц
- Toast уведомления вместо alert()/confirm()
- Confirm/Delete модалки вместо native confirm()

## Модалки — ModalOverlay

Все модалки используют `ModalOverlay` (`components/ModalOverlay.tsx`). **Не писать оверлей вручную.**

```tsx
import { ModalOverlay } from './ModalOverlay';

// В компоненте:
if (!isOpen) return null;

return (
  <ModalOverlay onClose={onClose}>
    <div className="bg-gray-900 rounded-2xl p-8 border border-white/20 max-w-md w-full">
      {/* контент модалки */}
    </div>
  </ModalOverlay>
);
```

ModalOverlay обеспечивает:
- `createPortal` в `document.body` (выход из stacking context `<main>`)
- `z-[9999]`, `fixed inset-0`, `bg-black/50 backdrop-blur-sm`
- Центрирование (`flex items-center justify-center`)
- Блокировку скролла body (с поддержкой вложенных модалок)
- Закрытие по Escape
- Закрытие по клику вне модалки (`closeOnOverlayClick`, default: true)
- `className` для переопределения стилей оверлея (напр. `className="!bg-black/60"`)

## i18n

- Все строки через `useTranslation()` / `t('key')`
- Локали: `frontend/src/locales/ru/translation.json`, `frontend/src/locales/en/translation.json`
- Ключи по формату: `pageName.section.element` (например `catalogPage.errorLoginRequired`)
- **API ошибки**: секция `apiErrors` в обоих locale файлах (~80 ключей)
- Утилита `frontend/src/utils/translateApiError.ts` — переводит `{"code": "ERR_..."}` → локализованную строку
- Все 25 компонентов с API-ошибками используют `translateApiError(t, detail, fallback)`

## Vite proxy

- Dev без Docker: proxy target `http://localhost:8000`
- Dev с Docker: proxy target задаётся через `VITE_PROXY_TARGET` env variable
- Prod: nginx проксирует `/api` → backend, Vite proxy не используется
