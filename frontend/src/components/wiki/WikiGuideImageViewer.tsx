import { useEffect, useRef, useState } from 'react';
import { Maximize2, MousePointer2, RotateCcw, X, ZoomIn, ZoomOut } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { ModalOverlay } from '../ModalOverlay';
import type { WikiGuideImage } from './wikiGuide';

interface WikiGuideImageCanvasProps {
  image: WikiGuideImage;
  onOpen?: () => void;
  activeCallout?: number | null;
  onActiveCalloutChange?: (index: number | null) => void;
}

interface WikiGuideImageViewerProps {
  image: WikiGuideImage | null;
  onClose: () => void;
}

const MIN_ZOOM = 1;
const MAX_ZOOM = 3;
const ZOOM_STEP = 0.25;
const WHEEL_ZOOM_SENSITIVITY = 0.002;

interface PointerPosition {
  x: number;
  y: number;
}

interface DragState {
  pointerId: number;
  startX: number;
  startY: number;
  scrollLeft: number;
  scrollTop: number;
}

interface PinchState {
  pointerIds: [number, number];
  startDistance: number;
  startZoom: number;
  imageX: number;
  imageY: number;
}

function pointerDistance(first: PointerPosition, second: PointerPosition) {
  return Math.hypot(second.x - first.x, second.y - first.y);
}

function pointerMidpoint(first: PointerPosition, second: PointerPosition) {
  return {
    x: (first.x + second.x) / 2,
    y: (first.y + second.y) / 2,
  };
}

function calloutPosition(x: number, y: number) {
  return {
    horizontal: x < 24 ? 'left-0' : x > 76 ? 'right-0' : 'left-1/2 -translate-x-1/2',
    vertical: y < 28 ? 'top-full mt-2' : 'bottom-full mb-2',
  };
}

export function WikiGuideImageCanvas({
  image,
  onOpen,
  activeCallout = null,
  onActiveCalloutChange,
}: WikiGuideImageCanvasProps) {
  const { t } = useTranslation();

  return (
    <div
      className={`group/image relative overflow-hidden rounded-2xl border border-white/10 bg-black/20 shadow-2xl shadow-black/30 ${onOpen ? 'cursor-zoom-in' : ''}`}
      onClick={onOpen}
    >
      <img
        src={image.src}
        alt={image.alt}
        draggable={false}
        onDragStart={(event) => event.preventDefault()}
        className="block h-auto w-full select-none"
      />
      {image.callouts.map((callout, index) => {
        const position = calloutPosition(callout.x, callout.y);
        const isActive = activeCallout === index;
        return (
          <button
            key={`${callout.x}-${callout.y}-${callout.label}`}
            type="button"
            aria-label={`${index + 1}. ${callout.label}`}
            data-active={isActive ? 'true' : undefined}
            className="group absolute z-10 -translate-x-1/2 -translate-y-1/2 cursor-help"
            style={{ left: `${callout.x}%`, top: `${callout.y}%` }}
            onClick={(event) => event.stopPropagation()}
            onMouseEnter={() => onActiveCalloutChange?.(index)}
            onMouseLeave={() => onActiveCalloutChange?.(null)}
            onFocus={() => onActiveCalloutChange?.(index)}
            onBlur={() => onActiveCalloutChange?.(null)}
          >
            <span className={`relative flex h-7 w-7 items-center justify-center rounded-full border-2 text-[11px] font-black shadow-[0_0_0_5px_rgba(34,211,238,0.24),0_0_24px_rgba(34,211,238,0.55),0_10px_28px_rgba(0,0,0,0.45)] transition-all md:h-8 md:w-8 md:text-xs ${isActive ? 'border-cyan-100/75 bg-cyan-400/10 text-transparent shadow-[0_0_0_3px_rgba(34,211,238,0.12),0_0_18px_rgba(34,211,238,0.32)]' : 'border-white bg-cyan-400/95 text-slate-950 group-hover:border-cyan-100/75 group-hover:bg-cyan-400/10 group-hover:text-transparent group-hover:shadow-[0_0_0_3px_rgba(34,211,238,0.12),0_0_18px_rgba(34,211,238,0.32)] group-focus-visible:border-cyan-100/75 group-focus-visible:bg-cyan-400/10 group-focus-visible:text-transparent group-focus-visible:shadow-[0_0_0_3px_rgba(34,211,238,0.12),0_0_18px_rgba(34,211,238,0.32)]'}`}>
              <span className={`transition-opacity ${isActive ? 'opacity-0' : 'group-hover:opacity-0 group-focus-visible:opacity-0'}`}>{index + 1}</span>
              <MousePointer2 className={`absolute -bottom-2 -right-2 h-4 w-4 fill-slate-950 text-white drop-shadow-md transition-opacity ${isActive ? 'opacity-0' : 'group-hover:opacity-0 group-focus-visible:opacity-0'}`} />
            </span>
            <span className={`pointer-events-none absolute ${position.horizontal} ${position.vertical} w-max max-w-64 rounded-xl border border-cyan-200/25 bg-slate-950/95 px-3 py-2 text-left text-xs font-semibold leading-5 text-white shadow-xl shadow-black/40 backdrop-blur-sm transition ${isActive ? 'visible opacity-100' : 'invisible opacity-0 group-hover:visible group-hover:opacity-100 group-focus-visible:visible group-focus-visible:opacity-100'}`}>
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
          className="pointer-events-none absolute right-3 top-3 inline-flex translate-y-1 items-center gap-2 rounded-xl border border-white/15 bg-slate-950/80 px-3 py-2 text-xs font-semibold text-white opacity-0 shadow-lg backdrop-blur-md transition hover:bg-slate-900 focus-visible:translate-y-0 focus-visible:opacity-100 group-hover/image:pointer-events-auto group-hover/image:translate-y-0 group-hover/image:opacity-100 group-focus-within/image:pointer-events-auto group-focus-within/image:translate-y-0 group-focus-within/image:opacity-100"
        >
          <Maximize2 className="h-4 w-4" />
          <span className="hidden sm:inline">{t('wikiGuide.openImage')}</span>
        </button>
      )}
    </div>
  );
}

export function WikiGuideCalloutLegend({
  image,
  activeCallout = null,
  onActiveCalloutChange,
}: {
  image: WikiGuideImage;
  activeCallout?: number | null;
  onActiveCalloutChange?: (index: number | null) => void;
}) {
  if (image.callouts.length === 0) return null;

  return (
    <ol className="mt-3 grid gap-2 sm:grid-cols-2">
      {image.callouts.map((callout, index) => {
        const isActive = activeCallout === index;
        return (
        <li
          key={`${callout.x}-${callout.y}-${callout.label}`}
          data-active={isActive ? 'true' : undefined}
          tabIndex={0}
          onMouseEnter={() => onActiveCalloutChange?.(index)}
          onMouseLeave={() => onActiveCalloutChange?.(null)}
          onFocus={() => onActiveCalloutChange?.(index)}
          onBlur={() => onActiveCalloutChange?.(null)}
          className={`flex cursor-default items-start gap-2 rounded-xl border px-3 py-2.5 text-xs leading-5 transition ${isActive ? 'border-cyan-300/30 bg-cyan-300/[0.1] text-white shadow-[0_0_18px_rgba(34,211,238,0.08)]' : 'border-cyan-300/10 bg-cyan-300/[0.045] text-slate-300 hover:border-cyan-300/25 hover:bg-cyan-300/[0.08]'}`}
        >
          <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ring-1 transition ${isActive ? 'bg-cyan-300 text-slate-950 ring-cyan-100/60' : 'bg-cyan-400/15 text-cyan-200 ring-cyan-300/20'}`}>
            {index + 1}
          </span>
          <span>{callout.label}</span>
        </li>
        );
      })}
    </ol>
  );
}

export function WikiGuideImageViewer({ image, onClose }: WikiGuideImageViewerProps) {
  const { t } = useTranslation();
  const [zoom, setZoom] = useState(MIN_ZOOM);
  const [activeCallout, setActiveCallout] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const dragStateRef = useRef<DragState | null>(null);
  const pinchStateRef = useRef<PinchState | null>(null);
  const activePointersRef = useRef(new Map<number, PointerPosition>());
  const zoomRef = useRef(MIN_ZOOM);
  const scrollFrameRef = useRef<number | null>(null);

  useEffect(() => {
    setZoom(MIN_ZOOM);
    zoomRef.current = MIN_ZOOM;
    setActiveCallout(null);
    setIsDragging(false);
    dragStateRef.current = null;
    pinchStateRef.current = null;
    activePointersRef.current.clear();
    if (scrollFrameRef.current !== null) {
      window.cancelAnimationFrame(scrollFrameRef.current);
      scrollFrameRef.current = null;
    }
    if (scrollAreaRef.current) {
      scrollAreaRef.current.scrollLeft = 0;
      scrollAreaRef.current.scrollTop = 0;
    }

    return () => {
      if (scrollFrameRef.current !== null) {
        window.cancelAnimationFrame(scrollFrameRef.current);
      }
    };
  }, [image?.src]);

  if (!image) return null;

  const setZoomAroundImagePoint = (
    nextZoom: number,
    imageX: number,
    imageY: number,
    clientX: number,
    clientY: number,
  ) => {
    const clampedZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, nextZoom));
    const scrollArea = scrollAreaRef.current;
    if (!scrollArea) {
      zoomRef.current = clampedZoom;
      setZoom(clampedZoom);
      return;
    }

    const bounds = scrollArea.getBoundingClientRect();
    const viewportX = clientX - bounds.left;
    const viewportY = clientY - bounds.top;

    if (clampedZoom !== zoomRef.current) {
      zoomRef.current = clampedZoom;
      setZoom(clampedZoom);
    }
    if (scrollFrameRef.current !== null) {
      window.cancelAnimationFrame(scrollFrameRef.current);
    }
    scrollFrameRef.current = window.requestAnimationFrame(() => {
      scrollArea.scrollLeft = imageX * clampedZoom - viewportX;
      scrollArea.scrollTop = imageY * clampedZoom - viewportY;
      scrollFrameRef.current = null;
    });
  };

  const setClampedZoom = (nextZoom: number, clientX?: number, clientY?: number) => {
    const currentZoom = zoomRef.current;
    const clampedZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, nextZoom));
    if (clampedZoom === currentZoom) return;

    const scrollArea = scrollAreaRef.current;
    if (!scrollArea) {
      zoomRef.current = clampedZoom;
      setZoom(clampedZoom);
      return;
    }

    const bounds = scrollArea.getBoundingClientRect();
    const pointerX = clientX === undefined ? bounds.left + bounds.width / 2 : clientX;
    const pointerY = clientY === undefined ? bounds.top + bounds.height / 2 : clientY;
    const viewportX = pointerX - bounds.left;
    const viewportY = pointerY - bounds.top;
    const imageX = (scrollArea.scrollLeft + viewportX) / currentZoom;
    const imageY = (scrollArea.scrollTop + viewportY) / currentZoom;

    setZoomAroundImagePoint(clampedZoom, imageX, imageY, pointerX, pointerY);
  };

  const startPinch = (scrollArea: HTMLDivElement) => {
    const entries = Array.from(activePointersRef.current.entries());
    if (entries.length < 2) return false;

    const [[firstId, first], [secondId, second]] = entries;
    const midpoint = pointerMidpoint(first, second);
    const bounds = scrollArea.getBoundingClientRect();
    const currentZoom = zoomRef.current;
    pinchStateRef.current = {
      pointerIds: [firstId, secondId],
      startDistance: Math.max(pointerDistance(first, second), 1),
      startZoom: currentZoom,
      imageX: (scrollArea.scrollLeft + midpoint.x - bounds.left) / currentZoom,
      imageY: (scrollArea.scrollTop + midpoint.y - bounds.top) / currentZoom,
    };
    dragStateRef.current = null;
    setIsDragging(true);
    return true;
  };

  const stopPointer = (event: React.PointerEvent<HTMLDivElement>) => {
    activePointersRef.current.delete(event.pointerId);
    const pinchEnded = pinchStateRef.current?.pointerIds.includes(event.pointerId) ?? false;
    if (pinchEnded) {
      pinchStateRef.current = null;
    }
    if (dragStateRef.current?.pointerId === event.pointerId) {
      dragStateRef.current = null;
    }
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    if (pinchEnded || activePointersRef.current.size === 0 || zoomRef.current <= MIN_ZOOM) {
      setIsDragging(false);
    }
  };

  return (
    <ModalOverlay onClose={onClose} className="bg-[#030712]/90" contentClassName="min-h-full flex items-center justify-center p-2 sm:p-4">
      <section role="dialog" aria-modal="true" aria-label={t('wikiGuide.imageViewer')} className="flex max-h-[96vh] w-full max-w-[96rem] flex-col overflow-hidden rounded-2xl border border-white/15 bg-[#07111f] shadow-2xl shadow-black/60">
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-white/10 bg-[#0b1524]/95 px-3 py-3 backdrop-blur-xl sm:px-5">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-white">{image.alt}</p>
            <p className="mt-0.5 max-w-3xl text-[11px] leading-4 text-slate-500 sm:text-xs">{Math.round(zoom * 100)}% · {t('wikiGuide.imageViewerHint')}</p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <button type="button" onClick={() => setClampedZoom(zoom - ZOOM_STEP)} disabled={zoom <= MIN_ZOOM} aria-label={t('wikiGuide.zoomOut')} className="rounded-lg border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white disabled:opacity-30">
              <ZoomOut className="h-4 w-4" />
            </button>
            <button type="button" onClick={() => setClampedZoom(zoom + ZOOM_STEP)} disabled={zoom >= MAX_ZOOM} aria-label={t('wikiGuide.zoomIn')} className="rounded-lg border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white disabled:opacity-30">
              <ZoomIn className="h-4 w-4" />
            </button>
            <button type="button" onClick={() => setClampedZoom(MIN_ZOOM)} disabled={zoom === MIN_ZOOM} aria-label={t('wikiGuide.resetZoom')} className="rounded-lg border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white disabled:opacity-30">
              <RotateCcw className="h-4 w-4" />
            </button>
            <button type="button" onClick={onClose} aria-label={t('wikiGuide.closeImage')} className="ml-1 rounded-lg border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:bg-red-500/15 hover:text-red-200">
              <X className="h-4 w-4" />
            </button>
          </div>
        </header>

        <div
          ref={scrollAreaRef}
          data-testid="wiki-image-scroll-area"
          className={`scrollbar-contained min-h-0 flex-1 overflow-auto bg-black/35 p-2 sm:p-4 ${zoom > MIN_ZOOM ? (isDragging ? 'cursor-grabbing select-none' : 'cursor-grab') : ''}`}
          style={{ touchAction: 'none', overscrollBehavior: 'contain' }}
          onWheel={(event) => {
            if (!event.altKey) return;
            event.preventDefault();
            setClampedZoom(
              zoomRef.current * Math.exp(-event.deltaY * WHEEL_ZOOM_SENSITIVITY),
              event.clientX,
              event.clientY,
            );
          }}
          onPointerDown={(event) => {
            if (event.button !== 0 || (event.target as HTMLElement).closest('button')) return;
            activePointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
            event.currentTarget.setPointerCapture?.(event.pointerId);
            if (startPinch(event.currentTarget)) return;
            if (zoomRef.current <= MIN_ZOOM) return;
            dragStateRef.current = {
              pointerId: event.pointerId,
              startX: event.clientX,
              startY: event.clientY,
              scrollLeft: event.currentTarget.scrollLeft,
              scrollTop: event.currentTarget.scrollTop,
            };
            setIsDragging(true);
            event.preventDefault();
          }}
          onPointerMove={(event) => {
            if (activePointersRef.current.has(event.pointerId)) {
              activePointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
            }
            const pinchState = pinchStateRef.current;
            if (pinchState) {
              const first = activePointersRef.current.get(pinchState.pointerIds[0]);
              const second = activePointersRef.current.get(pinchState.pointerIds[1]);
              if (!first || !second) return;
              event.preventDefault();
              const midpoint = pointerMidpoint(first, second);
              const nextZoom = pinchState.startZoom
                * (pointerDistance(first, second) / pinchState.startDistance);
              setZoomAroundImagePoint(
                nextZoom,
                pinchState.imageX,
                pinchState.imageY,
                midpoint.x,
                midpoint.y,
              );
              return;
            }
            const dragState = dragStateRef.current;
            if (!dragState || dragState.pointerId !== event.pointerId) return;
            event.preventDefault();
            event.currentTarget.scrollLeft = dragState.scrollLeft - (event.clientX - dragState.startX);
            event.currentTarget.scrollTop = dragState.scrollTop - (event.clientY - dragState.startY);
          }}
          onPointerUp={stopPointer}
          onPointerCancel={stopPointer}
        >
          <div className="mx-auto transition-[width] duration-150" style={{ width: `${zoom * 100}%` }} onDoubleClick={(event) => setClampedZoom(zoomRef.current === MIN_ZOOM ? 2 : MIN_ZOOM, event.clientX, event.clientY)}>
            <WikiGuideImageCanvas image={image} activeCallout={activeCallout} onActiveCalloutChange={setActiveCallout} />
          </div>
        </div>

        {image.callouts.length > 0 && (
          <footer className="scrollbar-contained max-h-36 shrink-0 overflow-y-auto border-t border-white/10 bg-[#0b1524] px-3 pb-3 sm:px-5">
            <WikiGuideCalloutLegend image={image} activeCallout={activeCallout} onActiveCalloutChange={setActiveCallout} />
          </footer>
        )}
      </section>
    </ModalOverlay>
  );
}
