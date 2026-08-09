import { useEffect, useState } from 'react';
import { Maximize2, MousePointer2, RotateCcw, X, ZoomIn, ZoomOut } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { ModalOverlay } from '../ModalOverlay';
import type { WikiGuideImage } from './wikiGuide';

interface WikiGuideImageCanvasProps {
  image: WikiGuideImage;
  onOpen?: () => void;
}

interface WikiGuideImageViewerProps {
  image: WikiGuideImage | null;
  onClose: () => void;
}

const MIN_ZOOM = 1;
const MAX_ZOOM = 3;
const ZOOM_STEP = 0.25;

function calloutPosition(x: number, y: number) {
  return {
    horizontal: x < 24 ? 'left-0' : x > 76 ? 'right-0' : 'left-1/2 -translate-x-1/2',
    vertical: y < 28 ? 'top-full mt-2' : 'bottom-full mb-2',
  };
}

export function WikiGuideImageCanvas({ image, onOpen }: WikiGuideImageCanvasProps) {
  const { t } = useTranslation();

  return (
    <div
      className={`relative overflow-hidden rounded-2xl border border-white/10 bg-black/20 shadow-2xl shadow-black/30 ${onOpen ? 'cursor-zoom-in' : ''}`}
      onClick={onOpen}
    >
      <img src={image.src} alt={image.alt} className="block h-auto w-full" />
      {image.callouts.map((callout, index) => {
        const position = calloutPosition(callout.x, callout.y);
        return (
          <button
            key={`${callout.x}-${callout.y}-${callout.label}`}
            type="button"
            aria-label={`${index + 1}. ${callout.label}`}
            className="group absolute z-10 -translate-x-1/2 -translate-y-1/2 cursor-help"
            style={{ left: `${callout.x}%`, top: `${callout.y}%` }}
            onClick={(event) => event.stopPropagation()}
          >
            <span className="relative flex h-7 w-7 items-center justify-center rounded-full border-2 border-white bg-cyan-400 text-[11px] font-black text-slate-950 shadow-[0_0_0_5px_rgba(34,211,238,0.22),0_10px_28px_rgba(0,0,0,0.5)] md:h-8 md:w-8 md:text-xs">
              {index + 1}
              <MousePointer2 className="absolute -bottom-2 -right-2 h-4 w-4 fill-slate-950 text-white drop-shadow-md" />
            </span>
            <span className={`pointer-events-none absolute ${position.horizontal} ${position.vertical} invisible w-max max-w-64 rounded-xl border border-cyan-200/25 bg-slate-950/95 px-3 py-2 text-left text-xs font-semibold leading-5 text-white opacity-0 shadow-xl shadow-black/40 backdrop-blur-sm transition group-hover:visible group-hover:opacity-100 group-focus-visible:visible group-focus-visible:opacity-100`}>
              {callout.label}
            </span>
          </button>
        );
      })}
      {onOpen && (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onOpen();
          }}
          className="absolute right-3 top-3 inline-flex items-center gap-2 rounded-xl border border-white/15 bg-slate-950/80 px-3 py-2 text-xs font-semibold text-white shadow-lg backdrop-blur-md transition hover:bg-slate-900"
        >
          <Maximize2 className="h-4 w-4" />
          <span className="hidden sm:inline">{t('wikiGuide.openImage')}</span>
        </button>
      )}
    </div>
  );
}

export function WikiGuideCalloutLegend({ image }: { image: WikiGuideImage }) {
  if (image.callouts.length === 0) return null;

  return (
    <ol className="mt-3 grid gap-2 sm:grid-cols-2">
      {image.callouts.map((callout, index) => (
        <li key={`${callout.x}-${callout.y}-${callout.label}`} className="flex items-start gap-2 rounded-xl border border-cyan-300/10 bg-cyan-300/[0.045] px-3 py-2.5 text-xs leading-5 text-slate-300">
          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-cyan-400/15 text-[10px] font-bold text-cyan-200 ring-1 ring-cyan-300/20">
            {index + 1}
          </span>
          <span>{callout.label}</span>
        </li>
      ))}
    </ol>
  );
}

export function WikiGuideImageViewer({ image, onClose }: WikiGuideImageViewerProps) {
  const { t } = useTranslation();
  const [zoom, setZoom] = useState(MIN_ZOOM);

  useEffect(() => {
    setZoom(MIN_ZOOM);
  }, [image?.src]);

  if (!image) return null;

  const setClampedZoom = (nextZoom: number) => {
    setZoom(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, nextZoom)));
  };

  return (
    <ModalOverlay onClose={onClose} closeOnOverlayClick={false} className="bg-[#030712]/90" contentClassName="min-h-full flex items-center justify-center p-2 sm:p-4">
      <section role="dialog" aria-modal="true" aria-label={t('wikiGuide.imageViewer')} className="flex max-h-[96vh] w-full max-w-[96rem] flex-col overflow-hidden rounded-2xl border border-white/15 bg-[#07111f] shadow-2xl shadow-black/60">
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-white/10 bg-[#0b1524]/95 px-3 py-3 backdrop-blur-xl sm:px-5">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-white">{image.alt}</p>
            <p className="mt-0.5 text-xs text-slate-500">{Math.round(zoom * 100)}%</p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <button type="button" onClick={() => setClampedZoom(zoom - ZOOM_STEP)} disabled={zoom <= MIN_ZOOM} aria-label={t('wikiGuide.zoomOut')} className="rounded-lg border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white disabled:opacity-30">
              <ZoomOut className="h-4 w-4" />
            </button>
            <button type="button" onClick={() => setClampedZoom(zoom + ZOOM_STEP)} disabled={zoom >= MAX_ZOOM} aria-label={t('wikiGuide.zoomIn')} className="rounded-lg border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white disabled:opacity-30">
              <ZoomIn className="h-4 w-4" />
            </button>
            <button type="button" onClick={() => setZoom(MIN_ZOOM)} disabled={zoom === MIN_ZOOM} aria-label={t('wikiGuide.resetZoom')} className="rounded-lg border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white disabled:opacity-30">
              <RotateCcw className="h-4 w-4" />
            </button>
            <button type="button" onClick={onClose} aria-label={t('wikiGuide.closeImage')} className="ml-1 rounded-lg border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:bg-red-500/15 hover:text-red-200">
              <X className="h-4 w-4" />
            </button>
          </div>
        </header>

        <div className="scrollbar-contained min-h-0 flex-1 overflow-auto bg-black/35 p-2 sm:p-4">
          <div className="mx-auto transition-[width] duration-200" style={{ width: `${zoom * 100}%` }} onDoubleClick={() => setZoom(zoom === MIN_ZOOM ? 2 : MIN_ZOOM)}>
            <WikiGuideImageCanvas image={image} />
          </div>
        </div>

        {image.callouts.length > 0 && (
          <footer className="scrollbar-contained max-h-36 shrink-0 overflow-y-auto border-t border-white/10 bg-[#0b1524] px-3 pb-3 sm:px-5">
            <WikiGuideCalloutLegend image={image} />
          </footer>
        )}
      </section>
    </ModalOverlay>
  );
}
