import { useEffect, useId, useRef, useState } from 'react';
import { AlertCircle, AlertTriangle, ChevronLeft, ChevronRight, Inbox, RefreshCw, X } from 'lucide-react';
import { pageCount } from '../utils/format';

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Accessible modal dialog: labelled, traps focus, closes on Escape and
 * returns focus to the element that opened it.
 */
export function Modal({ title, onClose, children, footer, maxWidth = 540, busy = false }) {
  const titleId = useId();
  const cardRef = useRef(null);
  // Refs keep the mount-only effect below stable even though callers pass
  // inline callbacks (re-running it would steal focus on every keystroke).
  const onCloseRef = useRef(onClose);
  const busyRef = useRef(busy);
  useEffect(() => {
    onCloseRef.current = onClose;
    busyRef.current = busy;
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
      }
      if (event.key === 'Tab' && card) {
        const items = [...card.querySelectorAll(FOCUSABLE)];
        if (!items.length) return;
        const firstItem = items[0];
        const lastItem = items[items.length - 1];
        if (event.shiftKey && document.activeElement === firstItem) { event.preventDefault(); lastItem.focus(); }
        else if (!event.shiftKey && document.activeElement === lastItem) { event.preventDefault(); firstItem.focus(); }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      previouslyFocused?.focus?.();
    };
  }, []);

  return (
    <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}>
      <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby={titleId} ref={cardRef} style={{ maxWidth }}>
        <div className="modal-header">
          <h2 className="modal-title" id={titleId}>{title}</h2>
          <button type="button" className="btn btn-ghost btn-icon" onClick={onClose} disabled={busy} aria-label="Close dialog">
            <X size={16} aria-hidden="true" />
          </button>
        </div>
        {children}
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}

export function ConfirmDialog({ title, message, confirmLabel = 'Confirm', danger = false, requireReason = false,
  reasonLabel = 'Reason (recorded in the audit log)', onConfirm, onCancel }) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const invalid = requireReason && reason.trim().length < 5;
  const submit = async (e) => {
    e.preventDefault();
    if (invalid) return;
    setBusy(true);
    try { await onConfirm(reason.trim()); } finally { setBusy(false); }
  };
  return (
    <Modal title={title} onClose={onCancel} busy={busy} maxWidth={460}>
      <form onSubmit={submit}>
        <div className="modal-body">
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', lineHeight: 1.5 }}>{message}</p>
          {requireReason && (
            <div className="form-group" style={{ marginTop: 14, marginBottom: 0 }}>
              <label className="form-label" htmlFor="confirm-reason">{reasonLabel} *</label>
              <textarea id="confirm-reason" className="form-control" rows={3} value={reason}
                onChange={(e) => setReason(e.target.value)} minLength={5} maxLength={500} required />
              <FieldHint>At least 5 characters.</FieldHint>
            </div>
          )}
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>Cancel</button>
          <button type="submit" className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`} disabled={busy || invalid}>
            {busy ? <><span className="spinner" aria-hidden="true" /> Working…</> : confirmLabel}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function LoadingState({ label = 'Loading…', minHeight }) {
  return (
    <div className="empty-state" role="status" aria-live="polite" style={minHeight ? { minHeight } : undefined}>
      <div className="spinner" aria-hidden="true" style={{ marginBottom: 12 }} />
      <div className="empty-state-title">{label}</div>
    </div>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="empty-state" role="alert">
      <AlertCircle size={28} aria-hidden="true" style={{ color: 'var(--status-red)' }} />
      <div className="empty-state-title">Could not load this data</div>
      <p style={{ fontSize: '0.8rem', marginTop: 4 }}>{message}</p>
      {onRetry && (
        <button type="button" className="btn btn-secondary btn-sm" style={{ marginTop: 12 }} onClick={onRetry}>
          <RefreshCw size={13} aria-hidden="true" /> Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ icon: Icon = Inbox, title, children }) {
  return (
    <div className="empty-state">
      <Icon size={28} aria-hidden="true" style={{ opacity: 0.35 }} />
      <div className="empty-state-title">{title}</div>
      {children && <div style={{ fontSize: '0.8rem', marginTop: 4 }}>{children}</div>}
    </div>
  );
}

export function Pagination({ page, pageSize, total, onPageChange, label = 'records' }) {
  const pages = pageCount(total, pageSize);
  const start = total === 0 ? 0 : page * pageSize + 1;
  const end = Math.min(total, (page + 1) * pageSize);
  return (
    <nav className="pagination" aria-label="Pagination">
      <span className="mono" aria-live="polite">{start}–{end} of {total} {label}</span>
      <div style={{ display: 'flex', gap: 6 }}>
        <button type="button" className="btn btn-secondary btn-sm" disabled={page === 0} onClick={() => onPageChange(page - 1)}>
          <ChevronLeft size={14} aria-hidden="true" /> Previous
        </button>
        <span className="mono" style={{ alignSelf: 'center' }}>Page {page + 1} / {pages}</span>
        <button type="button" className="btn btn-secondary btn-sm" disabled={page + 1 >= pages} onClick={() => onPageChange(page + 1)}>
          Next <ChevronRight size={14} aria-hidden="true" />
        </button>
      </div>
    </nav>
  );
}

export function FieldHint({ children }) {
  return <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 4 }}>{children}</div>;
}

export function FieldError({ id, children }) {
  if (!children) return null;
  return <div id={id} role="alert" style={{ fontSize: '0.75rem', color: 'var(--status-red)', marginTop: 4 }}>{children}</div>;
}

export function AIAdvisoryBanner({ status, compact = false }) {
  const demo = !status || status.mode === 'demo';
  return (
    <div className="alert alert-warning" role="note" style={{ alignItems: 'flex-start' }}>
      <AlertTriangle size={16} aria-hidden="true" style={{ flexShrink: 0, marginTop: 2 }} />
      <div>
        <strong>{demo ? 'DEMO / RESEARCH MODE — ' : ''}Unverified decision support, not evidence.</strong>
        {!compact && (
          <div style={{ marginTop: 4, color: 'var(--text-secondary)' }}>
            {demo
              ? 'The active model was trained on synthetic demonstration data and has no established real-world validity. '
              : ''}
            Outputs are not findings of guilt or dangerousness and must never be the sole basis for any action. A qualified
            reviewer must assess every output against the underlying record and record a reasoned decision.
            {status?.predictions_enabled === false && <> <strong>Predictions are currently disabled.</strong></>}
          </div>
        )}
      </div>
    </div>
  );
}
