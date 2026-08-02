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
