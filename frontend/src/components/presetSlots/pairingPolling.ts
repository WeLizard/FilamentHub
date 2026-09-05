export function isPairingAccessDenied(error: unknown): boolean {
  const status = (error as { response?: { status?: number } } | null)?.response?.status;
  return status === 401 || status === 403;
}

export function retryPairingStatusQuery(failureCount: number, error: unknown): boolean {
  return !isPairingAccessDenied(error) && failureCount < 1;
}
