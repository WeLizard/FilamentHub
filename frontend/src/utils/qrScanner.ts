// Общие хелперы сканирования QR (используются и в форме катушки, и в шапке).

/** Достаёт short-code из сырого значения: полный URL `.../qr/<CODE>` или сам код. */
export function extractQrShortCode(rawValue: string): string | null {
  const normalized = rawValue.trim();
  if (!normalized) {
    return null;
  }

  if (normalized.startsWith('http://') || normalized.startsWith('https://')) {
    try {
      const parsed = new URL(normalized);
      const segments = parsed.pathname.split('/').filter(Boolean);
      const qrIndex = segments.findIndex((segment) => segment.toLowerCase() === 'qr');
      if (qrIndex !== -1 && segments[qrIndex + 1]) {
        return segments[qrIndex + 1];
      }
    } catch {
      // Невалидный URL — пробуем как обычный short code.
    }
  }

  const match = normalized.match(/[A-Za-z0-9_-]{4,100}/);
  return match ? match[0] : null;
}

/**
 * Возвращает наш short-code, только если QR действительно наш:
 * — URL на filamenthub.ru с сегментом `/qr/<code>` (или `/f/<code>`);
 * — либо «голый» код целиком (бэкенд валидирует его при scan).
 * Для чужих QR (например, ссылка на Ozon) возвращает null — чтобы не дёргать API
 * и показать пользователю подсказку.
 */
export function ownQrShortCode(rawValue: string): string | null {
  const v = rawValue.trim();
  if (!v) return null;

  if (v.startsWith('http://') || v.startsWith('https://')) {
    try {
      const url = new URL(v);
      const host = url.hostname.toLowerCase();
      const ours = host === 'filamenthub.ru' || host.endsWith('.filamenthub.ru') || host === 'localhost';
      if (!ours) return null;
      const segments = url.pathname.split('/').filter(Boolean);
      const idx = segments.findIndex((s) => s.toLowerCase() === 'qr' || s.toLowerCase() === 'f');
      if (idx !== -1 && segments[idx + 1]) return segments[idx + 1];
      return null;
    } catch {
      return null;
    }
  }

  return /^[A-Za-z0-9_-]{4,100}$/.test(v) ? v : null;
}

/**
 * Покадровый декодер QR: нативный BarcodeDetector (Chromium на Android/desktop),
 * иначе ленивый jsQR-фолбэк на canvas (iOS Safari и Firefox — без BarcodeDetector).
 */
export async function createQrFrameDecoder(): Promise<(video: HTMLVideoElement) => Promise<string | null>> {
  const BarcodeDetectorCtor = window.BarcodeDetector;
  if (BarcodeDetectorCtor) {
    const detector = new BarcodeDetectorCtor({ formats: ['qr_code'] });
    return async (video) => {
      const barcodes = await detector.detect(video);
      return barcodes.find((item) => item.rawValue)?.rawValue ?? null;
    };
  }

  const { default: jsQR } = await import('jsqr');
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) {
    throw new Error('qr-decoder-unavailable');
  }
  return async (video) => {
    const vw = video.videoWidth;
    const vh = video.videoHeight;
    if (!vw || !vh) {
      return null;
    }
    const maxSide = 640;
    const scale = Math.min(1, maxSide / Math.max(vw, vh));
    const w = Math.round(vw * scale);
    const h = Math.round(vh * scale);
    canvas.width = w;
    canvas.height = h;
    ctx.drawImage(video, 0, 0, w, h);
    const { data } = ctx.getImageData(0, 0, w, h);
    const result = jsQR(data, w, h, { inversionAttempts: 'attemptBoth' });
    return result?.data ?? null;
  };
}
