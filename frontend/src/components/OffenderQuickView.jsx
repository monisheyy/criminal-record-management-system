import { useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import { ArrowUpRight, ChevronLeft, ChevronRight, X } from 'lucide-react';
import { criminalPhotoUrl } from '../services/api';
import { useDialog } from '../utils/useDialog';

function ageFrom(dob, now = new Date()) {
  if (!dob) return null;
  const birth = new Date(dob);
  if (Number.isNaN(birth.getTime())) return null;
  let age = now.getFullYear() - birth.getFullYear();
  if (now < new Date(now.getFullYear(), birth.getMonth(), birth.getDate())) age -= 1;
  return age;
}

function Portrait({ criminal }) {
  // Remember which photo failed so a different one (next offender) still loads.
  const [failed, setFailed] = useState('');
  const initials = `${criminal.first_name?.[0] || ''}${criminal.last_name?.[0] || ''}`.toUpperCase();
  if (!criminal.photo_sha256 || failed === criminal.photo_sha256) {
    return <div className="qv-photo qv-photo-empty"><span aria-hidden="true">{initials}</span><small>No photo on file</small></div>;
  }
  return (
    <img key={criminal.photo_sha256} className="qv-photo" src={criminalPhotoUrl(criminal.id, criminal.photo_sha256)}
      alt={`Photo of ${criminal.first_name} ${criminal.last_name}`} onError={() => setFailed(criminal.photo_sha256)} />
  );
}

/**
 * Pop-up offender card: a large photo beside the facts an officer needs at a
 * glance. ← / → step through the rows of the current page.
 */
export default function OffenderQuickView({ rows, index, onIndexChange, onClose }) {
  const titleId = useId();
  const cardRef = useRef(null);
  const criminal = rows[index];
  const hasPrev = index > 0;
  const hasNext = index < rows.length - 1;
  useDialog(cardRef, {
    onClose,
    onKey: (event) => {
      if (event.key === 'ArrowLeft' && hasPrev) onIndexChange(index - 1);
      if (event.key === 'ArrowRight' && hasNext) onIndexChange(index + 1);
    },
  });
  if (!criminal) return null;

  const age = ageFrom(criminal.date_of_birth);
  const threat = criminal.threat_level || 'low';
  const facts = [
    ['Age', age === null ? '—' : `${age} yrs`],
    ['Gender', criminal.gender || '—'],
    ['Primary offence', criminal.crime_type || 'Not classified'],
    ['Prior convictions', criminal.prior_convictions ?? 0],
    ['Gang', criminal.gang ? `${criminal.gang.name}${criminal.gang_rank ? ` · ${criminal.gang_rank}` : ''}` : 'None known'],
    ['Occupation', criminal.occupation || '—'],
  ];

  // Portalled to <body> so the page's transition layer can't trap it under the sidebar.
  return createPortal(
    <div className="qv-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="qv-card" role="dialog" aria-modal="true" aria-labelledby={titleId} ref={cardRef}>
        <div className="qv-media">
          <Portrait criminal={criminal} />
        </div>

        <div className="qv-info">
          <div className="qv-top">
            <span className="qv-crn">{criminal.crn}</span>
            <button type="button" className="qv-icon-btn" onClick={onClose} aria-label="Close">
              <X size={16} aria-hidden="true" />
            </button>
          </div>

          <h2 className="qv-name" id={titleId}>{criminal.first_name} {criminal.last_name}</h2>
          {criminal.alias && <p className="qv-alias">aka “{criminal.alias}”</p>}

          <div className="qv-tags">
            {criminal.is_wanted && <span className="qv-tag qv-tag-wanted">Wanted</span>}
            {criminal.is_incarcerated && <span className="qv-tag">Incarcerated</span>}
            {!criminal.is_wanted && !criminal.is_incarcerated && <span className="qv-tag">On record</span>}
            <span className={`qv-tag qv-threat-${threat}`}>{threat} threat</span>
          </div>

          <dl className="qv-facts">
            {facts.map(([label, value]) => (
              <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
            ))}
            <div className="qv-wide"><dt>Last known address</dt><dd>{criminal.address || '—'}</dd></div>
          </dl>

          <div className="qv-actions">
            <div className="qv-pager">
              <button type="button" className="qv-icon-btn" onClick={() => onIndexChange(index - 1)} disabled={!hasPrev}
                aria-label="Previous offender">
                <ChevronLeft size={16} aria-hidden="true" />
              </button>
              <span aria-live="polite">{index + 1} of {rows.length}</span>
              <button type="button" className="qv-icon-btn" onClick={() => onIndexChange(index + 1)} disabled={!hasNext}
                aria-label="Next offender">
                <ChevronRight size={16} aria-hidden="true" />
              </button>
            </div>
            <Link to={`/criminals/${criminal.id}`} className="qv-open">
              Full record <ArrowUpRight size={14} aria-hidden="true" />
            </Link>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
