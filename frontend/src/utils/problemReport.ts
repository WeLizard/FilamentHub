/** Opens the plugin problem-report window from the toolbar or an error toast. */

export interface ProblemReportRequest {
  subject?: string;
  message?: string;
}

const listeners = new Set<(request: ProblemReportRequest) => void>();

export function openProblemReport(request: ProblemReportRequest = {}): void {
  listeners.forEach((listener) => listener(request));
}

export function subscribeToProblemReport(
  listener: (request: ProblemReportRequest) => void,
): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
