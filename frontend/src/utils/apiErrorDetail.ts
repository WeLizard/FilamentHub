export function apiErrorDetail(error: unknown): unknown {
  if (typeof error !== 'object' || error === null || !('response' in error)) {
    return undefined;
  }
  return (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
}
