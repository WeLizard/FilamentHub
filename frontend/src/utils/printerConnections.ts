import type { PrinterConnectionBinding } from '../api/client';

const normalizedProvider = (binding: PrinterConnectionBinding): string =>
  binding.provider?.trim().toLowerCase() ?? '';

const normalizedEndpoint = (binding: PrinterConnectionBinding): string | null => {
  const endpoint = binding.display_endpoint?.trim();
  return endpoint ? endpoint.toLowerCase() : null;
};

const newestFirst = (
  left: PrinterConnectionBinding,
  right: PrinterConnectionBinding,
): number => right.last_seen_at.localeCompare(left.last_seen_at);

/**
 * Produce a human-readable connection list without changing stored bindings.
 *
 * A physical printer may keep both a legacy endpoint binding and one or more
 * stable local connection refs. Ref-only bindings are useful for matching but
 * render as the same "address is stored in OrcaSlicer" fallback. When a real
 * endpoint is available for that provider, it is the more useful label; when
 * it is not, one newest local fallback is enough. Distinct providers and
 * distinct disclosed endpoints remain visible.
 */
export function visiblePrinterConnections(
  bindings: PrinterConnectionBinding[],
): PrinterConnectionBinding[] {
  const byProvider = new Map<string, PrinterConnectionBinding[]>();

  [...bindings].sort(newestFirst).forEach((binding) => {
    const provider = `${normalizedProvider(binding)}:${binding.status ?? 'bound'}`;
    const current = byProvider.get(provider) ?? [];
    current.push(binding);
    byProvider.set(provider, current);
  });

  const visible: PrinterConnectionBinding[] = [];
  byProvider.forEach((providerBindings) => {
    const disclosedByEndpoint = new Map<string, PrinterConnectionBinding>();
    providerBindings.forEach((binding) => {
      const endpoint = normalizedEndpoint(binding);
      if (endpoint && !disclosedByEndpoint.has(endpoint)) {
        disclosedByEndpoint.set(endpoint, binding);
      }
    });

    if (disclosedByEndpoint.size > 0) {
      const disclosed = Array.from(disclosedByEndpoint.values());
      if (disclosed.length === 1 && providerBindings[0]) {
        visible.push({
          ...disclosed[0],
          last_seen_at: providerBindings[0].last_seen_at,
        });
      } else {
        visible.push(...disclosed);
      }
      return;
    }

    const newestFallback = providerBindings[0];
    if (newestFallback) visible.push(newestFallback);
  });

  return visible.sort(newestFirst);
}
