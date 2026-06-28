import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, X } from 'lucide-react';
import { ModalOverlay } from './ModalOverlay';
import { createQrFrameDecoder } from '../utils/qrScanner';

interface QrScannerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onDetected: (rawCode: string) => void;
  busy?: boolean;
}

/** Переиспользуемая модалка сканирования QR камерой (BarcodeDetector + jsQR-фолбэк). */
export function QrScannerModal({ isOpen, onClose, onDetected, busy = false }: QrScannerModalProps) {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const frameRef = useRef<number | null>(null);
  const scanningRef = useRef(false);
  const [isReady, setIsReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    let cancelled = false;

    const stop = () => {
      scanningRef.current = false;
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
      if (videoRef.current) {
        videoRef.current.srcObject = null;
      }
    };

    const start = async () => {
      setError(null);
      setIsReady(false);
      if (!navigator.mediaDevices?.getUserMedia) {
        setError(t('profilePage.spoolAddModal.scanQrCameraNotSupported'));
        return;
      }
      try {
        const decode = await createQrFrameDecoder();
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        scanningRef.current = true;
        setIsReady(true);

        let lastDecodeAt = 0;
        const scanFrame = async (now: number) => {
          if (!scanningRef.current) {
            return;
          }
          const video = videoRef.current;
          if (!video || video.readyState < 2) {
            frameRef.current = requestAnimationFrame((ts) => void scanFrame(ts));
            return;
          }
          if (now - lastDecodeAt >= 120) {
            lastDecodeAt = now;
            try {
              const rawValue = await decode(video);
              if (!scanningRef.current) {
                return;
              }
              if (rawValue) {
                scanningRef.current = false;
                onDetected(rawValue);
                return;
              }
            } catch {
              // Временные ошибки декодирования игнорируем.
            }
          }
          frameRef.current = requestAnimationFrame((ts) => void scanFrame(ts));
        };
        frameRef.current = requestAnimationFrame((ts) => void scanFrame(ts));
      } catch {
        if (!cancelled) {
          setError(t('profilePage.spoolAddModal.scanQrCameraNotSupported'));
        }
      }
    };

    void start();

    return () => {
      cancelled = true;
      stop();
    };
  }, [isOpen, onDetected, t]);

  if (!isOpen) {
    return null;
  }

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-gray-900 rounded-2xl p-5 border border-white/20 max-w-md w-full">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-bold text-white">{t('qrScanner.title')}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors" aria-label={t('qrScanner.close')}>
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="rounded-xl overflow-hidden border border-white/15 bg-black/40">
          <video ref={videoRef} className="w-full max-h-80 object-cover" playsInline muted autoPlay />
          <div className="px-3 py-2 text-xs text-gray-300 border-t border-white/10 flex items-center gap-2">
            {(busy || !isReady) && !error && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            <span>
              {error
                ? error
                : busy
                  ? t('qrScanner.resolving')
                  : isReady
                    ? t('qrScanner.hint')
                    : t('profilePage.spoolAddModal.scanQrCameraStarting')}
            </span>
          </div>
        </div>
      </div>
    </ModalOverlay>
  );
}
