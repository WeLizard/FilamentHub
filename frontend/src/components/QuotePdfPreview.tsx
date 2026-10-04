import { useEffect, useRef, type FC } from 'react';
import { useTranslation } from 'react-i18next';
import { Printer, X } from 'lucide-react';
import { ModalOverlay } from './ModalOverlay';

interface QuotePdfPreviewProps {
  url: string;
  title: string;
  onClose: () => void;
  /** The frame holds the HTML document (not a PDF), so it can be printed from here. */
  printable?: boolean;
}

// 210 mm at the CSS reference 96 dpi.
const A4_WIDTH_PX = 794;
const SCROLLBAR_ALLOWANCE_PX = 16;
const TOOLBAR_REM = 3.25;
// Space kept above the sheet for the site's fixed header.
const VERTICAL_GAP_REM = 6;

/** A sheet-shaped A4 preview; the HTML document is scaled to the sheet width instead of stretching. */
export const QuotePdfPreview: FC<QuotePdfPreviewProps> = ({ url, title, onClose, printable = false }) => {
  const { t } = useTranslation();
  const frameRef = useRef<HTMLIFrameElement>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);

  useEffect(() => () => resizeObserverRef.current?.disconnect(), []);

  const fitDocumentToSheet = () => {
    const frame = frameRef.current;
    resizeObserverRef.current?.disconnect();
    if (!frame) return;
    let document: Document | null = null;
    try {
      document = frame.contentDocument;
    } catch {
      return;
    }
    if (!document?.documentElement || document.contentType !== 'text/html') return;
    const root = document.documentElement;
    // The sheet scrolls vertically; its scrollbar must not push the page into a horizontal one.
    root.style.overflowX = 'hidden';
    const fit = () => {
      const width = frame.clientWidth - SCROLLBAR_ALLOWANCE_PX;
      if (width > 0) root.style.zoom = String(width / A4_WIDTH_PX);
    };
    fit();
    if (typeof ResizeObserver !== 'undefined') {
      resizeObserverRef.current = new ResizeObserver(fit);
      resizeObserverRef.current.observe(frame);
    }
  };

  const sheetHeight = `calc(100dvh - ${VERTICAL_GAP_REM}rem)`;
  const sheetWidth = `min(calc(100vw - 2rem), calc((100dvh - ${VERTICAL_GAP_REM + TOOLBAR_REM}rem) * 210 / 297))`;

  return (
    <ModalOverlay onClose={onClose} contentClassName="flex h-full items-center justify-center px-4 pb-4 pt-20">
      <section
        className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-white/10 bg-slate-900 shadow-2xl shadow-black/60"
        style={{ height: sheetHeight, width: sheetWidth }}
        aria-label={t('crmWorkspace.actions.pdfPreview')}
      >
        <header className="flex shrink-0 items-center justify-between gap-2 border-b border-white/10 px-3 py-2">
          <div className="min-w-0">
            <h2 className="sr-only">{t('crmWorkspace.actions.pdfPreview')}</h2>
            <p className="truncate text-sm font-medium text-white">{title}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {printable && (
              <button type="button" onClick={() => frameRef.current?.contentWindow?.print()} className="inline-flex items-center gap-1.5 rounded-xl border border-white/15 bg-white/5 px-2.5 py-1.5 text-sm text-white hover:bg-white/10">
                <Printer className="h-4 w-4" />{t('crmWorkspace.actions.printDocument')}
              </button>
            )}
            <button type="button" autoFocus onClick={onClose} className="inline-flex items-center gap-1.5 rounded-xl border border-white/15 bg-white/5 px-2.5 py-1.5 text-sm text-white hover:bg-white/10" aria-label={t('crmWorkspace.actions.closePreview')}>
              <X className="h-4 w-4" />{t('crmWorkspace.actions.closePreview')}
            </button>
          </div>
        </header>
        <iframe ref={frameRef} key={url} src={url} title={`${title} PDF`} onLoad={fitDocumentToSheet} className="min-h-0 flex-1 border-0 bg-slate-200" />
      </section>
    </ModalOverlay>
  );
};
