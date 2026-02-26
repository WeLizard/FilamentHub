import type { TFunction } from "i18next";

/**
 * Translate API error detail into localized string.
 *
 * Supported formats:
 *  - { code: "ERR_...", params?: {...} }  → new structured error
 *  - "ERR_..."  string                   → new code-only error
 *  - plain string (no ERR_ prefix)       → legacy Russian text (backward compat)
 *  - array                               → Pydantic validation (first message)
 *  - null / undefined                    → fallback
 */
export function translateApiError(
  t: TFunction,
  detail: unknown,
  fallback?: string,
): string {
  if (detail == null) {
    return fallback ?? t("apiErrors.UNKNOWN_ERROR");
  }

  // Pydantic validation errors (array of { loc, msg, type })
  if (Array.isArray(detail)) {
    const first = detail[0];
    if (first && typeof first === "object" && "msg" in first) {
      return (first as { msg: string }).msg;
    }
    return fallback ?? t("apiErrors.UNKNOWN_ERROR");
  }

  // Structured error: { code: "ERR_...", params?: {...} }
  if (typeof detail === "object" && "code" in detail) {
    const { code, params } = detail as { code: string; params?: Record<string, unknown> };
    // Translate field_name param if present (backend sends keys like "username", "brand_name")
    const translatedParams = params ? { ...params } : {};
    if (translatedParams.field_name && typeof translatedParams.field_name === "string") {
      const fieldKey = `fieldNames.${translatedParams.field_name}`;
      const fieldTranslated = t(fieldKey);
      if (fieldTranslated !== fieldKey) {
        translatedParams.field_name = fieldTranslated;
      }
    }
    const key = `apiErrors.${code}`;
    const translated = t(key, translatedParams);
    // If i18next returns the key itself, the translation is missing → use fallback
    if (translated === key) {
      return fallback ?? code;
    }
    return translated;
  }

  // String error
  if (typeof detail === "string") {
    // New code-only format: "ERR_..."
    if (detail.startsWith("ERR_")) {
      const key = `apiErrors.${detail}`;
      const translated = t(key);
      if (translated === key) {
        return fallback ?? detail;
      }
      return translated;
    }
    // Legacy Russian text — return as-is for backward compatibility
    return detail;
  }

  return fallback ?? t("apiErrors.UNKNOWN_ERROR");
}
