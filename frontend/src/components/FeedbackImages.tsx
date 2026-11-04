import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ProtectedImageError, useProtectedImage } from './ProtectedImage';
import type { FeedbackAttachment } from '../types/api';
import { ModalOverlay } from './ModalOverlay';

function FeedbackImageThumb({
  attachment,
}: {
  attachment: FeedbackAttachment;
}) {
  const { t } = useTranslation();
  const image = useProtectedImage(attachment.url);
  const [opened, setOpened] = useState(false);
  useEffect(() => {
    if (image.status !== 'ready') setOpened(false);
  }, [image.status, image.objectUrl]);
  if (image.status === 'error') return <ProtectedImageError onRetry={image.retry} />;
  const objectUrl = image.objectUrl;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpened(true)}
        disabled={image.status !== 'ready'}
        aria-label={t('feedbackImages.open')}
        className="block overflow-hidden rounded-lg border border-white/10 bg-black/20 transition hover:border-white/30 focus:outline-none focus:ring-2 focus:ring-purple-500"
        style={{ aspectRatio: `${attachment.width} / ${attachment.height}` }}
      >
        {objectUrl ? (
          <img key={objectUrl} src={objectUrl} alt="" onLoad={image.onLoad} onError={image.onError} aria-busy={image.status === 'loading'} className="h-full max-h-40 w-auto max-w-[16rem] object-contain" />
        ) : (
          <span className="block h-24 w-32 animate-pulse bg-white/5" />
        )}
      </button>
      {opened && image.status === 'ready' && objectUrl && (
        <ModalOverlay onClose={() => setOpened(false)} className="!bg-black/80">
          <button type="button" onClick={() => setOpened(false)} aria-label={t('feedbackImages.close')} className="max-h-[85vh] max-w-[92vw] cursor-zoom-out">
            <img src={objectUrl} alt="" className="max-h-[85vh] max-w-[92vw] rounded-lg object-contain shadow-2xl" />
          </button>
        </ModalOverlay>
      )}
    </>
  );
}

export function FeedbackImages({ attachments }: { attachments?: FeedbackAttachment[] }) {
  if (!attachments?.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {attachments.map((attachment) => (
        <FeedbackImageThumb key={attachment.public_id} attachment={attachment} />
      ))}
    </div>
  );
}
