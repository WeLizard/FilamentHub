import { StrictMode, useRef, useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { createPortal } from 'react-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ModalOverlay } from './ModalOverlay';

function pageRoot(): HTMLDivElement {
  const root = document.createElement('div');
  root.id = 'root';
  document.body.appendChild(root);
  return root;
}

describe('ModalOverlay focus lifecycle', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.body.style.overflow = '';
  });

  it('preserves React autoFocus and supports an explicit initial focus target', () => {
    const root = pageRoot();
    const { unmount } = render(
      <ModalOverlay onClose={vi.fn()}>
        <input aria-label="automatic" autoFocus />
        <button type="button">Later</button>
      </ModalOverlay>,
      { container: root },
    );
    expect(screen.getByLabelText('automatic')).toHaveFocus();
    unmount();
    const explicitRoot = pageRoot();

    function ExplicitFocus() {
      const preferred = useRef<HTMLButtonElement>(null);
      return (
        <ModalOverlay onClose={vi.fn()} initialFocusRef={preferred}>
          <button type="button">First</button>
          <button ref={preferred} type="button">Preferred</button>
        </ModalOverlay>
      );
    }
    render(<ExplicitFocus />, { container: explicitRoot });
    expect(screen.getByRole('button', { name: 'Preferred' })).toHaveFocus();
  });

  it('wraps Tab in both directions and recomputes available controls', () => {
    const root = pageRoot();
    const { rerender } = render(
      <ModalOverlay onClose={vi.fn()}>
        <button type="button">First</button>
        <button type="button">Last</button>
      </ModalOverlay>,
      { container: root },
    );
    const first = screen.getByRole('button', { name: 'First' });
    const last = screen.getByRole('button', { name: 'Last' });
    expect(first).toHaveFocus();

    last.focus();
    fireEvent.keyDown(last, { key: 'Tab' });
    expect(first).toHaveFocus();
    fireEvent.keyDown(first, { key: 'Tab', shiftKey: true });
    expect(last).toHaveFocus();

    rerender(
      <ModalOverlay onClose={vi.fn()}>
        <button type="button">First</button>
        <button type="button" disabled>Last</button>
      </ModalOverlay>,
    );
    fireEvent.keyDown(first, { key: 'Tab' });
    expect(first).toHaveFocus();
  });

  it('keeps controls from React-owned body portals in the active focus cycle', () => {
    const root = pageRoot();
    function PortaledControl() {
      return createPortal(
        <div data-modal-portal="" data-testid="owned-portal">
          <button type="button">Portal action</button>
        </div>,
        document.body,
      );
    }
    render(
      <ModalOverlay onClose={vi.fn()}>
        <button type="button">Inside action</button>
        <PortaledControl />
      </ModalOverlay>,
      { container: root },
    );
    const inside = screen.getByRole('button', { name: 'Inside action' });
    const portaled = screen.getByRole('button', { name: 'Portal action' });
    expect(inside).toHaveFocus();
    portaled.focus();
    expect(portaled).toHaveFocus();
    fireEvent.keyDown(portaled, { key: 'Tab' });
    expect(inside).toHaveFocus();
    fireEvent.keyDown(inside, { key: 'Tab', shiftKey: true });
    expect(portaled).toHaveFocus();
  });

  it('restores the prior isolation state of an explicitly owned portal root', () => {
    const root = pageRoot();
    let portalRoot: HTMLDivElement | null = null;
    function ExistingPortal() {
      return createPortal(
        <div
          ref={(element) => {
            if (element) {
              element.setAttribute('inert', 'existing');
              portalRoot = element;
            }
          }}
          data-modal-portal=""
          aria-hidden="false"
        >
          <button type="button">Portal action</button>
        </div>,
        document.body,
      );
    }
    const { unmount } = render(
      <ModalOverlay onClose={vi.fn()}>
        <button type="button">Inside action</button>
        <ExistingPortal />
      </ModalOverlay>,
      { container: root },
    );
    expect(portalRoot).not.toBeNull();
    expect(portalRoot!).not.toHaveAttribute('aria-hidden');
    expect(portalRoot!).not.toHaveAttribute('inert');
    const detachedPortalRoot = portalRoot!;
    unmount();
    expect(detachedPortalRoot).toHaveAttribute('aria-hidden', 'false');
    expect(detachedPortalRoot).toHaveAttribute('inert', 'existing');
  });

  it('keeps focus on its scope when no controls are focusable', () => {
    const root = pageRoot();
    render(
      <ModalOverlay onClose={vi.fn()}><p>Nothing interactive</p></ModalOverlay>,
      { container: root },
    );
    const scope = screen.getByText('Nothing interactive').parentElement as HTMLElement;
    expect(scope).toHaveFocus();
    fireEvent.keyDown(scope, { key: 'Tab' });
    expect(scope).toHaveFocus();
  });

  it('skips inaccessible controls and treats a radio group as one Tab stop', () => {
    const root = pageRoot();
    render(
      <ModalOverlay onClose={vi.fn()}>
        <button type="button">First</button>
        <div style={{ display: 'none' }}><button type="button">Hidden ancestor</button></div>
        <button type="button" tabIndex={-2}>Negative tab index</button>
        <details><button type="button">Closed details</button></details>
        <input type="radio" name="choice" aria-label="Unchecked radio" />
        <input type="radio" name="choice" aria-label="Checked radio" defaultChecked />
      </ModalOverlay>,
      { container: root },
    );
    const first = screen.getByRole('button', { name: 'First' });
    const checked = screen.getByRole('radio', { name: 'Checked radio' });
    checked.focus();
    fireEvent.keyDown(checked, { key: 'Tab' });
    expect(first).toHaveFocus();
    first.focus();
    fireEvent.keyDown(first, { key: 'Tab', shiftKey: true });
    expect(checked).toHaveFocus();
  });

  it('contains programmatic focus and restores the opener on unmount', () => {
    const root = pageRoot();
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>Open</button>
          <button type="button">Background</button>
          {open && (
            <ModalOverlay onClose={() => setOpen(false)}>
              <button type="button" onClick={() => setOpen(false)}>Close</button>
            </ModalOverlay>
          )}
        </>
      );
    }
    render(<Harness />, { container: root });
    const opener = screen.getByRole('button', { name: 'Open' });
    opener.focus();
    fireEvent.click(opener);
    const close = screen.getByRole('button', { name: 'Close' });
    expect(close).toHaveFocus();
    screen.getByText('Background').focus();
    expect(close).toHaveFocus();
    fireEvent.click(close);
    expect(opener).toHaveFocus();
  });

  it('does not attempt to restore focus to an opener removed with the modal', () => {
    const root = pageRoot();
    function Harness() {
      const [visible, setVisible] = useState(true);
      const [open, setOpen] = useState(false);
      return visible ? (
        <>
          <button type="button" onClick={() => setOpen(true)}>Open</button>
          {open && (
            <ModalOverlay onClose={() => setVisible(false)}>
              <button type="button" onClick={() => setVisible(false)}>Remove all</button>
            </ModalOverlay>
          )}
        </>
      ) : <p>Gone</p>;
    }
    render(<Harness />, { container: root });
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    fireEvent.click(screen.getByRole('button', { name: 'Remove all' }));
    expect(screen.getByText('Gone')).toBeInTheDocument();
    expect(document.activeElement).toBe(document.body);
  });

  it('makes only the top layer active and restores its parent and page focus', () => {
    const root = pageRoot();
    const outerClose = vi.fn();
    function NestedHarness() {
      const [outer, setOuter] = useState(false);
      const [inner, setInner] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOuter(true)}>Open outer</button>
          {outer && (
            <ModalOverlay onClose={() => { outerClose(); setOuter(false); }}>
              <button type="button" onClick={() => setInner(true)}>Open inner</button>
              {inner && (
                <ModalOverlay onClose={() => setInner(false)}>
                  <button type="button">Inner action</button>
                </ModalOverlay>
              )}
            </ModalOverlay>
          )}
        </>
      );
    }
    render(<NestedHarness />, { container: root });
    const pageOpener = screen.getByRole('button', { name: 'Open outer' });
    pageOpener.focus();
    fireEvent.click(pageOpener);
    const parentOpener = screen.getByRole('button', { name: 'Open inner' });
    fireEvent.click(parentOpener);

    const overlays = document.querySelectorAll<HTMLElement>('[data-modal-overlay]');
    expect(overlays).toHaveLength(2);
    expect(overlays[0]).toHaveAttribute('inert');
    expect(overlays[0]).toHaveAttribute('aria-hidden', 'true');
    expect(overlays[1]).not.toHaveAttribute('inert');
    expect(screen.getByRole('button', { name: 'Inner action' })).toHaveFocus();

    fireEvent.pointerDown(overlays[0], { pointerId: 1 });
    fireEvent.pointerUp(overlays[0], { pointerId: 1 });
    expect(outerClose).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Inner action' })).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('button', { name: 'Inner action' })).not.toBeInTheDocument();
    expect(parentOpener).toHaveFocus();
    expect(overlays[0]).not.toHaveAttribute('inert');

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('button', { name: 'Open inner' })).not.toBeInTheDocument();
    expect(pageOpener).toHaveFocus();
  });

  it('does not let Escape fall through a nonclosable top layer', () => {
    const root = pageRoot();
    const outerClose = vi.fn();
    const innerClose = vi.fn();
    render(
      <ModalOverlay onClose={outerClose}>
        <button type="button">Outer</button>
        <ModalOverlay onClose={innerClose} closeOnEscape={false}>
          <button type="button">Inner</button>
        </ModalOverlay>
      </ModalOverlay>,
      { container: root },
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(innerClose).not.toHaveBeenCalled();
    expect(outerClose).not.toHaveBeenCalled();
  });

  it('keeps the page isolated and resumes the last modal focus after suspension', () => {
    const root = pageRoot();
    const external = document.createElement('button');
    external.textContent = 'External dialog';
    document.body.appendChild(external);
    const { rerender } = render(
      <ModalOverlay onClose={vi.fn()}>
        <button type="button">Modal action</button>
      </ModalOverlay>,
      { container: root },
    );
    const action = screen.getByRole('button', { name: 'Modal action' });
    expect(action).toHaveFocus();
    expect(root).toHaveAttribute('inert');
    expect(root).toHaveAttribute('aria-hidden', 'true');

    rerender(
      <ModalOverlay onClose={vi.fn()} suspended>
        <button type="button">Modal action</button>
      </ModalOverlay>,
    );
    external.focus();
    expect(external).toHaveFocus();
    rerender(
      <ModalOverlay onClose={vi.fn()}>
        <button type="button">Modal action</button>
      </ModalOverlay>,
    );
    expect(action).toHaveFocus();
  });

  it('restores existing root attributes and body overflow after nested StrictMode cleanup', () => {
    const root = pageRoot();
    root.setAttribute('aria-hidden', 'false');
    root.setAttribute('inert', 'existing');
    document.body.style.overflow = 'clip';
    const { unmount } = render(
      <StrictMode>
        <ModalOverlay onClose={vi.fn()}>
          <ModalOverlay onClose={vi.fn()}><button type="button">Top</button></ModalOverlay>
        </ModalOverlay>
      </StrictMode>,
      { container: root },
    );
    expect(document.body.style.overflow).toBe('hidden');
    unmount();
    expect(document.body.style.overflow).toBe('clip');
    expect(root).toHaveAttribute('aria-hidden', 'false');
    expect(root).toHaveAttribute('inert', 'existing');
  });

  it('isolates unrelated body roots and restores their existing accessibility state', () => {
    const root = pageRoot();
    const widget = document.createElement('aside');
    widget.setAttribute('aria-hidden', 'false');
    widget.setAttribute('inert', 'existing');
    document.body.appendChild(widget);
    const { unmount } = render(
      <ModalOverlay onClose={vi.fn()}><button type="button">Action</button></ModalOverlay>,
      { container: root },
    );
    expect(widget).toHaveAttribute('aria-hidden', 'true');
    expect(widget).toHaveAttribute('inert');
    const toast = document.createElement('div');
    document.body.appendChild(toast);
    return Promise.resolve().then(() => {
      expect(toast).toHaveAttribute('aria-hidden', 'true');
      expect(toast).toHaveAttribute('inert');
      unmount();
      expect(widget).toHaveAttribute('aria-hidden', 'false');
      expect(widget).toHaveAttribute('inert', 'existing');
      expect(toast).not.toHaveAttribute('aria-hidden');
      expect(toast).not.toHaveAttribute('inert');
    });
  });

  it('closes only after a same-pointer press and release on the top backdrop', () => {
    const root = pageRoot();
    const onClose = vi.fn();
    render(
      <ModalOverlay onClose={onClose}>
        <button type="button">Content</button>
      </ModalOverlay>,
      { container: root },
    );
    const content = screen.getByRole('button', { name: 'Content' });
    const backdrop = content.parentElement as HTMLElement;
    fireEvent.pointerDown(content, { pointerId: 1 });
    fireEvent.pointerUp(backdrop, { pointerId: 1 });
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.pointerDown(backdrop, { pointerId: 2 });
    fireEvent.pointerUp(content, { pointerId: 2 });
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.pointerDown(backdrop, { pointerId: 3 });
    fireEvent.pointerCancel(backdrop, { pointerId: 3 });
    fireEvent.pointerUp(backdrop, { pointerId: 3 });
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.pointerDown(backdrop, { pointerId: 4, pointerType: 'touch' });
    fireEvent.pointerUp(backdrop, { pointerId: 5, pointerType: 'touch' });
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.pointerDown(backdrop, { pointerId: 6, pointerType: 'touch' });
    fireEvent.pointerUp(backdrop, { pointerId: 6, pointerType: 'touch' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
