import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { feedbackAPI } from '../api/client';
import type { FeedbackAttachment } from '../types/api';
import { ModalOverlay } from './ModalOverlay';

/** Thread images are private to the author and admins, so they are fetched with
 * the session and shown from object URLs instead of plain `src` links. */
function useAttachmentObjectUrl(url: string): string | null {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let createdUrl: string | null = null;
    void feedbackAPI.getAttachmentBlob(url)
      .then((blob) => {
        if (!active) return;
        createdUrl = URL.createObjectURL(blob);
        setObjectUrl(createdUrl);
      })
      .catch(() => {
        if (active) setObjectUrl(null);
      });
    return () => {
      active = false;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [url]);

  return objectUrl;
}

function FeedbackImageThumb({
  attachment,
  onOpen,
}: {
  attachment: FeedbackAttachment;
  onOpen: (objectUrl: string) => void;
}) {
  const { t } = useTranslation();
  const objectUrl = useAttachmentObjectUrl(attachment.url);

  return (
    <button
      type="button"
      onClick={() => objectUrl && onOpen(objectUrl)}
      disabled={!objectUrl}
      aria-label={t('feedbackImages.open')}
      className="block overflow-hidden rounded-lg border border-white/10 bg-black/20 transition hover:border-white/30 focus:outline-none focus:ring-2 focus:ring-purple-500"
      style={{ aspectRatio: `${attachment.width} / ${attachment.height}` }}
    >
      {objectUrl ? (
        <img src={objectUrl} alt="" className="h-full max-h-40 w-auto max-w-[16rem] object-contain" />
      ) : (
        <span className="block h-24 w-32 animate-pulse bg-white/5" />
      )}
    </button>
  );
}

export function FeedbackImages({ attachments }: { attachments?: FeedbackAttachment[] }) {
  const { t } = useTranslation();
  const [opened, setOpened] = useState<string | null>(null);

  if (!attachments?.length) return null;

  return (
    <>
      <div className="mt-2 flex flex-wrap gap-2">
        {attachments.map((attachment) => (
          <FeedbackImageThumb key={attachment.public_id} attachment={attachment} onOpen={setOpened} />
        ))}
      </div>
      {opened && (
        <ModalOverlay onClose={() => setOpened(null)} className="!bg-black/80">
          <button
            type="button"
            onClick={() => setOpened(null)}
            aria-label={t('feedbackImages.close')}
            className="max-h-[85vh] max-w-[92vw] cursor-zoom-out"
          >
            <img src={opened} alt="" className="max-h-[85vh] max-w-[92vw] rounded-lg object-contain shadow-2xl" />
          </button>
        </ModalOverlay>
      )}
    </>
  );
}
