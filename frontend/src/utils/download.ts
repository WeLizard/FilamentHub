/** Trigger a browser download of binary data as a named file. */
export const downloadBlob = (data: Blob | BlobPart, filename: string): void => {
  const blob = data instanceof Blob ? data : new Blob([data]);
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

/** Print an exact server-rendered PDF without replacing the current editor. */
export const printPdfBlob = (data: Blob | BlobPart): Promise<void> => {
  const blob =
    data instanceof Blob ? data : new Blob([data], { type: "application/pdf" });
  const url = URL.createObjectURL(blob);
  const frame = document.createElement("iframe");
  frame.title = "Print PDF";
  frame.setAttribute("aria-hidden", "true");
  frame.style.position = "fixed";
  frame.style.width = "1px";
  frame.style.height = "1px";
  frame.style.right = "0";
  frame.style.bottom = "0";
  frame.style.opacity = "0";
  frame.style.pointerEvents = "none";

  return new Promise((resolve, reject) => {
    let cleanupTimer: number | undefined;
    const cleanup = () => {
      if (cleanupTimer !== undefined) window.clearTimeout(cleanupTimer);
      frame.remove();
      URL.revokeObjectURL(url);
    };
    frame.addEventListener(
      "error",
      () => {
        cleanup();
        reject(new Error("Could not load the print PDF"));
      },
      { once: true },
    );
    frame.addEventListener(
      "load",
      () => {
        const printWindow = frame.contentWindow;
        if (!printWindow) {
          cleanup();
          reject(new Error("Print window is unavailable"));
          return;
        }
        try {
          printWindow.addEventListener("afterprint", cleanup, { once: true });
          cleanupTimer = window.setTimeout(cleanup, 60_000);
          printWindow.focus();
          printWindow.print();
          resolve();
        } catch (error) {
          cleanup();
          reject(error);
        }
      },
      { once: true },
    );
    frame.src = url;
    document.body.appendChild(frame);
  });
};

/** Convert a user-facing title into a stable, portable download filename stem. */
export const safeDownloadStem = (value: string, fallback = 'download'): string => {
  const stem = (value || '')
    .trim()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[\s/\\:]+/g, '-')
    .replace(/[^a-zA-Z0-9а-яА-ЯёЁ_.-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .toLowerCase();
  return stem || fallback;
};
