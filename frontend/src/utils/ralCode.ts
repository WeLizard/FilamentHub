export const normalizeRalCode = (value: string): string => {
  const trimmed = value.trim();
  if (!trimmed) return '';
  const match = trimmed.match(/^(?:RAL[\s_-]*)?(\d{4})$/i);
  return match ? match[1] : trimmed.toUpperCase();
};

export const formatRalCode = (value?: string | null): string => {
  const normalized = normalizeRalCode(value || '');
  return normalized ? `RAL ${normalized}` : '';
};
