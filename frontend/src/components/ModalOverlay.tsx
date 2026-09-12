/** Shared modal overlay — portal, focus lifecycle, backdrop, scroll lock, Escape. */

import {
  type ReactNode,
  type RefObject,
  useCallback,
  useLayoutEffect,
  useRef,
} from 'react';
import { createPortal } from 'react-dom';

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'area[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'iframe',
  'object',
  'embed',
  '[contenteditable="true"]',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

interface OverlayRecord {
  order: number;
  overlay: HTMLDivElement | null;
  scope: HTMLDivElement | null;
  bodyChildrenBeforeMount: Set<Element>;
  externalPortalRoots: Set<HTMLElement>;
  restoreTarget: HTMLElement | null;
  rootRestoreTarget: HTMLElement | null;
  lastFocused: HTMLElement | null;
  initialFocusRef?: RefObject<HTMLElement | null>;
  onClose: () => void;
  closeOnEscape: boolean;
  suspended: boolean;
}

interface RootIsolationSnapshot {
  element: HTMLElement;
  ariaHidden: string | null;
  inert: boolean;
  inertAttribute: string | null;
}

let nextOverlayOrder = 0;
const overlayStack: OverlayRecord[] = [];
let originalBodyOverflow: string | null = null;
let rootIsolation: RootIsolationSnapshot | null = null;
let redirectingFocus = false;
let bodyPortalObserver: MutationObserver | null = null;

function activeOverlay(): OverlayRecord | undefined {
  for (let index = overlayStack.length - 1; index >= 0; index -= 1) {
    if (!overlayStack[index].suspended) return overlayStack[index];
  }
  return undefined;
}

function setInert(element: HTMLElement, inert: boolean): void {
  element.inert = inert;
  if (inert) element.setAttribute('inert', '');
  else element.removeAttribute('inert');
}

function isolateApplication(): void {
  if (originalBodyOverflow === null) {
    originalBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
  }
  if (rootIsolation !== null) return;
  const root = document.getElementById('root');
  if (!root) return;
  rootIsolation = {
    element: root,
    ariaHidden: root.getAttribute('aria-hidden'),
    inert: root.inert,
    inertAttribute: root.getAttribute('inert'),
  };
  root.setAttribute('aria-hidden', 'true');
  setInert(root, true);
}

function restoreApplication(): void {
  if (originalBodyOverflow !== null) {
    document.body.style.overflow = originalBodyOverflow;
    originalBodyOverflow = null;
  }
  if (rootIsolation === null) return;
  const { element, ariaHidden, inert, inertAttribute } = rootIsolation;
  if (ariaHidden === null) element.removeAttribute('aria-hidden');
  else element.setAttribute('aria-hidden', ariaHidden);
  element.inert = inert;
  if (inertAttribute === null) element.removeAttribute('inert');
  else element.setAttribute('inert', inertAttribute);
  rootIsolation = null;
}

function applyLayerIsolation(): void {
  const active = activeOverlay();
  for (const record of overlayStack) {
    if (!record.overlay) continue;
    const inactive = record !== active;
    if (inactive) record.overlay.setAttribute('aria-hidden', 'true');
    else record.overlay.removeAttribute('aria-hidden');
    setInert(record.overlay, inactive);
    for (const portalRoot of record.externalPortalRoots) {
      if (inactive) portalRoot.setAttribute('aria-hidden', 'true');
      else portalRoot.removeAttribute('aria-hidden');
      setInert(portalRoot, inactive);
    }
  }
}

function isFocusable(element: HTMLElement | null | undefined): element is HTMLElement {
  if (!element || !element.isConnected) return false;
  if (element.closest('[inert], [aria-hidden="true"]')) return false;
  if (!element.matches(FOCUSABLE_SELECTOR) && !element.hasAttribute('tabindex')) return false;
  if (element.matches(':disabled') || element.hidden || element.getAttribute('aria-hidden') === 'true') {
    return false;
  }
  const style = window.getComputedStyle(element);
  return style.display !== 'none' && style.visibility !== 'hidden';
}

function focusableElements(record: OverlayRecord): HTMLElement[] {
  const containers = [record.scope, ...record.externalPortalRoots].filter(
    (element): element is HTMLElement => element !== null && element.isConnected,
  );
  return containers
    .flatMap((container) => Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)))
    .filter(isFocusable);
}

function recordContains(record: OverlayRecord, element: HTMLElement): boolean {
  return Boolean(
    record.scope?.contains(element)
    || [...record.externalPortalRoots].some((root) => root.contains(element)),
  );
}

function focusElement(element: HTMLElement): void {
  redirectingFocus = true;
  try {
    element.focus({ preventScroll: true });
  } finally {
    redirectingFocus = false;
  }
}

function focusOverlay(record: OverlayRecord, preferLastFocused = false): void {
  const scope = record.scope;
  if (!scope || record.suspended || activeOverlay() !== record) return;
  const current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  if (current && recordContains(record, current) && isFocusable(current)) {
    record.lastFocused = current;
    return;
  }
  const preferred = preferLastFocused && isFocusable(record.lastFocused)
    ? record.lastFocused
    : record.initialFocusRef?.current;
  const target = isFocusable(preferred)
    ? preferred
    : Array.from(scope.querySelectorAll<HTMLElement>('[data-modal-initial-focus]')).find(isFocusable)
      ?? focusableElements(record)[0]
      ?? scope;
  focusElement(target);
  record.lastFocused = target;
}

function restoreFocusAfterRemoval(record: OverlayRecord): void {
  const parent = activeOverlay();
  if (parent) {
    const immediate = record.restoreTarget;
    if (isFocusable(immediate) && recordContains(parent, immediate)) {
      focusElement(immediate);
      parent.lastFocused = immediate;
      return;
    }
    focusOverlay(parent, true);
    return;
  }
  const target = isFocusable(record.restoreTarget)
    ? record.restoreTarget
    : isFocusable(record.rootRestoreTarget) ? record.rootRestoreTarget : null;
  if (target) focusElement(target);
}

function handleDocumentKeyDown(event: KeyboardEvent): void {
  const record = activeOverlay();
  if (!record || event.defaultPrevented) return;
  if (event.key === 'Escape') {
    event.preventDefault();
    if (record.closeOnEscape) record.onClose();
    return;
  }
  if (event.key !== 'Tab' || !record.scope) return;
  const focusable = focusableElements(record);
  if (focusable.length === 0) {
    event.preventDefault();
    focusElement(record.scope);
    record.lastFocused = record.scope;
    return;
  }
  const current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const currentIndex = current ? focusable.indexOf(current) : -1;
  if (event.shiftKey && currentIndex <= 0) {
    event.preventDefault();
    focusElement(focusable[focusable.length - 1]);
  } else if (!event.shiftKey && currentIndex === focusable.length - 1) {
    event.preventDefault();
    focusElement(focusable[0]);
  } else if (currentIndex === -1) {
    event.preventDefault();
    focusElement(event.shiftKey ? focusable[focusable.length - 1] : focusable[0]);
  }
}

function handleDocumentFocusIn(event: FocusEvent): void {
  if (redirectingFocus) return;
  const record = activeOverlay();
  const target = event.target instanceof HTMLElement ? event.target : null;
  if (!record || !target || !record.scope) return;
  if (
    recordContains(record, target)
  ) {
    record.lastFocused = target;
    return;
  }
  const owningRecord = overlayStack.find((candidate) => candidate.overlay?.contains(target));
  if (!owningRecord && target.closest('[data-modal-overlay]')) return;
  focusOverlay(record, true);
}

function bodyChildFor(element: HTMLElement): HTMLElement | null {
  let candidate: HTMLElement = element;
  while (candidate.parentElement && candidate.parentElement !== document.body) {
    candidate = candidate.parentElement;
  }
  return candidate.parentElement === document.body ? candidate : null;
}

function assignExternalPortal(record: OverlayRecord, element: HTMLElement): void {
  if (element.id === 'root' || element.hasAttribute('data-modal-overlay')) return;
  for (const candidate of overlayStack) candidate.externalPortalRoots.delete(element);
  record.externalPortalRoots.add(element);
  applyLayerIsolation();
}

function discoverMountedPortals(record: OverlayRecord): void {
  for (const child of Array.from(document.body.children)) {
    if (!record.bodyChildrenBeforeMount.has(child) && child instanceof HTMLElement) {
      assignExternalPortal(activeOverlay() ?? record, child);
    }
  }
}

function startModalEnvironment(): void {
  if (overlayStack.length !== 1) return;
  isolateApplication();
  document.addEventListener('keydown', handleDocumentKeyDown);
  document.addEventListener('focusin', handleDocumentFocusIn);
  bodyPortalObserver = new MutationObserver((mutations) => {
    const record = activeOverlay();
    if (!record) return;
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (node instanceof HTMLElement && node.parentElement === document.body) {
          assignExternalPortal(record, node);
        }
      }
    }
  });
  bodyPortalObserver.observe(document.body, { childList: true });
}

function stopModalEnvironment(): void {
  if (overlayStack.length !== 0) return;
  document.removeEventListener('keydown', handleDocumentKeyDown);
  document.removeEventListener('focusin', handleDocumentFocusIn);
  bodyPortalObserver?.disconnect();
  bodyPortalObserver = null;
  restoreApplication();
}

interface ModalOverlayProps {
  onClose: () => void;
  children: ReactNode;
  /** Close when clicking outside the modal content (default: true) */
  closeOnOverlayClick?: boolean;
  /** Close on Escape key (default: true) */
  closeOnEscape?: boolean;
  /** Extra classes for the outer fixed overlay div */
  className?: string;
  /** Classes for the inner content container (default centers the modal; override for drawers) */
  contentClassName?: string;
  /** Prefer this element when focus first enters the modal. */
  initialFocusRef?: RefObject<HTMLElement | null>;
  /** Keep the current step mounted while a local credential dialog owns input. */
  suspended?: boolean;
}

export const ModalOverlay: React.FC<ModalOverlayProps> = ({
  onClose,
  children,
  closeOnOverlayClick = true,
  closeOnEscape = true,
  className = '',
  contentClassName = 'min-h-full flex items-center justify-center p-4',
  initialFocusRef,
  suspended = false,
}) => {
  const openerRef = useRef<HTMLElement | null>(
    document.activeElement instanceof HTMLElement ? document.activeElement : null,
  );
  const overlayRef = useRef<HTMLDivElement>(null);
  const scopeRef = useRef<HTMLDivElement>(null);
  const recordRef = useRef<OverlayRecord | null>(null);
  if (recordRef.current === null) {
    recordRef.current = {
      order: ++nextOverlayOrder,
      overlay: null,
      scope: null,
      bodyChildrenBeforeMount: new Set(document.body.children),
      externalPortalRoots: new Set(),
      restoreTarget: openerRef.current,
      rootRestoreTarget: openerRef.current,
      lastFocused: null,
      initialFocusRef,
      onClose,
      closeOnEscape,
      suspended,
    };
  }
  const record = recordRef.current;
  record.onClose = onClose;
  record.closeOnEscape = closeOnEscape;
  record.initialFocusRef = initialFocusRef;

  useLayoutEffect(() => {
    record.overlay = overlayRef.current;
    record.scope = scopeRef.current;
    const parent = activeOverlay();
    record.rootRestoreTarget = parent?.rootRestoreTarget ?? record.restoreTarget;
    overlayStack.push(record);
    overlayStack.sort((left, right) => left.order - right.order);
    startModalEnvironment();
    discoverMountedPortals(record);
    applyLayerIsolation();
    if (!record.suspended && activeOverlay() === record) focusOverlay(record);
    return () => {
      const wasActive = activeOverlay() === record;
      const index = overlayStack.indexOf(record);
      if (index >= 0) overlayStack.splice(index, 1);
      for (const root of record.externalPortalRoots) {
        root.removeAttribute('aria-hidden');
        setInert(root, false);
      }
      record.externalPortalRoots.clear();
      applyLayerIsolation();
      stopModalEnvironment();
      if (wasActive) restoreFocusAfterRemoval(record);
      record.overlay = null;
      record.scope = null;
    };
  }, [record]);

  useLayoutEffect(() => {
    if (record.suspended === suspended) return;
    if (
      suspended
      && document.activeElement instanceof HTMLElement
      && recordContains(record, document.activeElement)
    ) {
      record.lastFocused = document.activeElement as HTMLElement;
    }
    record.suspended = suspended;
    applyLayerIsolation();
    if (!suspended && activeOverlay() === record) focusOverlay(record, true);
  }, [record, suspended]);

  const pressStartedOnOverlay = useRef(false);
  const handleOverlayMouseDown = useCallback((event: React.MouseEvent) => {
    const isActive = activeOverlay() === record;
    pressStartedOnOverlay.current = isActive && event.target === event.currentTarget;
  }, [record]);
  const handleOverlayClick = useCallback((event: React.MouseEvent) => {
    if (
      closeOnOverlayClick
      && activeOverlay() === record
      && event.target === event.currentTarget
      && pressStartedOnOverlay.current
    ) {
      onClose();
    }
    pressStartedOnOverlay.current = false;
  }, [closeOnOverlayClick, onClose, record]);

  return createPortal(
    <div
      ref={overlayRef}
      data-modal-overlay=""
      className={`fixed inset-0 bg-black/50 backdrop-blur-sm z-[9999] overflow-y-auto ${className}`}
      style={suspended ? { visibility: 'hidden' } : undefined}
      aria-hidden={suspended || undefined}
      inert={suspended || undefined}
    >
      <div
        ref={scopeRef}
        tabIndex={-1}
        className={contentClassName}
        onFocusCapture={(event) => {
          const target = event.target as HTMLElement;
          if (!scopeRef.current?.contains(target)) {
            const portalRoot = bodyChildFor(target);
            if (portalRoot) assignExternalPortal(record, portalRoot);
          }
          record.lastFocused = target;
        }}
        onMouseDown={handleOverlayMouseDown}
        onClick={handleOverlayClick}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
};
