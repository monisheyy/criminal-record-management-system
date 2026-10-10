import { useEffect, useRef } from 'react';

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Dialog behaviour shared by every modal: focuses the first control, traps
 * Tab inside the card, closes on Escape and returns focus to the opener.
 * `onKey` sees every other keydown (used for arrow-key paging).
 */
export function useDialog(cardRef, { onClose, busy = false, onKey: extraKey } = {}) {
  // Refs keep the mount-only effect below stable even though callers pass
  // inline callbacks (re-running it would steal focus on every keystroke).
  const onCloseRef = useRef(onClose);
  const busyRef = useRef(busy);
  const extraKeyRef = useRef(extraKey);
  useEffect(() => {
    onCloseRef.current = onClose;
    busyRef.current = busy;
    extraKeyRef.current = extraKey;
  });

  useEffect(() => {
    const previouslyFocused = document.activeElement;
    const card = cardRef.current;
    const first = card?.querySelector('input, select, textarea') || card?.querySelector(FOCUSABLE);
    first?.focus();

    const onKey = (event) => {
      if (event.key === 'Escape' && !busyRef.current) {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key === 'Tab' && card) {
        const items = [...card.querySelectorAll(FOCUSABLE)];
        if (!items.length) return;
        const firstItem = items[0];
        const lastItem = items[items.length - 1];
        if (event.shiftKey && document.activeElement === firstItem) { event.preventDefault(); lastItem.focus(); }
        else if (!event.shiftKey && document.activeElement === lastItem) { event.preventDefault(); firstItem.focus(); }
        return;
      }
      extraKeyRef.current?.(event);
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      previouslyFocused?.focus?.();
    };
  }, [cardRef]);
}
