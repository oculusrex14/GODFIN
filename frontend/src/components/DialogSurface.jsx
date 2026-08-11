import { forwardRef, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';

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

const openDialogs = [];
let bodyLockCount = 0;
let previousBodyOverflow = '';

function focusableElements(panel) {
  return [...panel.querySelectorAll(FOCUSABLE_SELECTOR)].filter((element) => {
    if (element.getAttribute('aria-hidden') === 'true' || element.closest('[inert]')) {
      return false;
    }
    const style = window.getComputedStyle(element);
    return style.visibility !== 'hidden' && style.display !== 'none';
  });
}

function isolateOutside(panel) {
  const changed = [];
  let branch = panel;
  while (branch?.parentElement) {
    const parent = branch.parentElement;
    for (const sibling of parent.children) {
      if (sibling === branch || sibling.tagName === 'SCRIPT' || sibling.tagName === 'STYLE') {
        continue;
      }
      const keepBackdropClickable = sibling.hasAttribute('data-godfin-dialog-backdrop');
      changed.push({
        element: sibling,
        inert: sibling.inert,
        ariaHidden: sibling.getAttribute('aria-hidden'),
        keepBackdropClickable,
      });
      if (!keepBackdropClickable) sibling.inert = true;
      sibling.setAttribute('aria-hidden', 'true');
    }
    if (parent === document.body) break;
    branch = parent;
  }
  return () => {
    for (const item of changed.reverse()) {
      if (!item.keepBackdropClickable) item.element.inert = item.inert;
      if (item.ariaHidden == null) item.element.removeAttribute('aria-hidden');
      else item.element.setAttribute('aria-hidden', item.ariaHidden);
    }
  };
}

function lockBodyScroll() {
  if (bodyLockCount === 0) {
    previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
  }
  bodyLockCount += 1;
  return () => {
    bodyLockCount = Math.max(0, bodyLockCount - 1);
    if (bodyLockCount === 0) document.body.style.overflow = previousBodyOverflow;
  };
}

const DialogSurface = forwardRef(function DialogSurface({
  as: Component = motion.div,
  onClose,
  initialFocusRef,
  labelledBy,
  describedBy,
  ariaLabel,
  escapeCloses = true,
  children,
  ...props
}, forwardedRef) {
  const panelRef = useRef(null);
  const closeRef = useRef(onClose);
  const tokenRef = useRef(Symbol('godfin-dialog'));

  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return undefined;

    const token = tokenRef.current;
    const previouslyFocused = document.activeElement;
    openDialogs.push({ token, panel });
    const restoreOutside = isolateOutside(panel);
    const restoreBodyScroll = lockBodyScroll();

    const focusTimer = window.requestAnimationFrame(() => {
      const target = initialFocusRef?.current
        || panel.querySelector('[data-dialog-autofocus]')
        || focusableElements(panel)[0]
        || panel;
      target.focus({ preventScroll: true });
    });

    function handleKeyDown(event) {
      if (openDialogs.at(-1)?.token !== token) return;
      if (event.key === 'Escape' && escapeCloses && closeRef.current) {
        event.preventDefault();
        event.stopPropagation();
        closeRef.current();
        return;
      }
      if (event.key !== 'Tab') return;

      const focusable = focusableElements(panel);
      if (focusable.length === 0) {
        event.preventDefault();
        panel.focus({ preventScroll: true });
        return;
      }
      const first = focusable[0];
      const last = focusable.at(-1);
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !panel.contains(active))) {
        event.preventDefault();
        last.focus({ preventScroll: true });
      } else if (!event.shiftKey && (active === last || !panel.contains(active))) {
        event.preventDefault();
        first.focus({ preventScroll: true });
      }
    }

    document.addEventListener('keydown', handleKeyDown, true);
    return () => {
      window.cancelAnimationFrame(focusTimer);
      document.removeEventListener('keydown', handleKeyDown, true);
      const index = openDialogs.findIndex((dialog) => dialog.token === token);
      if (index >= 0) openDialogs.splice(index, 1);
      restoreOutside();
      restoreBodyScroll();
      const newTop = openDialogs.at(-1)?.panel;
      if (newTop) {
        newTop.inert = false;
        newTop.removeAttribute('aria-hidden');
      }
      window.requestAnimationFrame(() => {
        if (previouslyFocused instanceof HTMLElement && previouslyFocused.isConnected) {
          previouslyFocused.focus({ preventScroll: true });
        }
      });
    };
  }, [escapeCloses, initialFocusRef]);

  return (
    <Component
      {...props}
      ref={(node) => {
        panelRef.current = node;
        if (typeof forwardedRef === 'function') forwardedRef(node);
        else if (forwardedRef) forwardedRef.current = node;
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      aria-label={ariaLabel}
      data-godfin-dialog="true"
      tabIndex={-1}
    >
      {children}
    </Component>
  );
});

export default DialogSurface;
