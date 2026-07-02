/** Verification proof file card: authed image preview + download (no token in URL) */

import { useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import { proofFilesAPI } from '../api/client';

const IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'];

interface ProofFileCardProps {
  /** Relative path, e.g. "brand_requests/5/abc.png" */
  filePath: string;
  fileName: string;
  imageErrorText: string;
}

export function ProofFileCard({ filePath, fileName, imageErrorText }: ProofFileCardProps) {
  const ext = fileName.split('.').pop()?.toLowerCase() || '';
  const isImage = IMAGE_EXTENSIONS.includes(ext);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewFailed, setPreviewFailed] = useState(false);

  useEffect(() => {
    if (!isImage) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    proofFilesAPI
      .getObjectUrl(filePath)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        objectUrl = url;
        setPreviewUrl(url);
      })
      .catch(() => {
        if (!cancelled) setPreviewFailed(true);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [filePath, isImage]);

  return (
    <div className="bg-white/5 rounded-lg p-3 border border-white/10">
      {isImage && (
        <div className="mb-2">
          {previewFailed ? (
            <div className="flex items-center justify-center h-32 bg-white/5 rounded-lg border border-white/20">
              <span className="text-gray-400 text-sm">{imageErrorText}</span>
            </div>
          ) : previewUrl ? (
            <a href={previewUrl} target="_blank" rel="noopener noreferrer" className="block cursor-pointer">
              <img
                src={previewUrl}
                alt={fileName}
                className="max-w-full h-auto max-h-64 rounded-lg border border-white/20 hover:border-purple-400/50 transition-colors"
              />
            </a>
          ) : (
            <div className="h-32 bg-white/5 rounded-lg border border-white/20 animate-pulse" />
          )}
        </div>
      )}
      <button
        type="button"
        onClick={() => void proofFilesAPI.download(filePath, fileName)}
        className="flex items-center space-x-2 text-purple-400 hover:text-purple-300 text-sm"
      >
        <Download className="w-4 h-4" />
        <span className="truncate" title={fileName}>{fileName}</span>
      </button>
    </div>
  );
}
