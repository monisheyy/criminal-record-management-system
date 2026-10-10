import React from 'react';

function getRiskColor(score) {
  if (score >= 75) return 'critical';
  if (score >= 55) return 'high';
  if (score >= 35) return 'medium';
  return 'low';
}

export function RiskBadge({ score, level, showBar = false }) {
  const lvl = level || getRiskColor(score);
  const colorMap = { critical: '#DC2626', high: '#EA580C', medium: '#D97706', low: '#16A34A' };
  const color = colorMap[lvl] || '#475467';

  return (
    <div className="risk-score-wrapper">
      <span className={`risk-score-num ${lvl}`}>
        {score?.toFixed ? score.toFixed(0) : score}
        {score !== undefined && <span style={{ fontSize: '0.7em', color: 'var(--text-muted)' }}>/100</span>}
      </span>
      {showBar && (
        <div className="risk-bar">
          <div
            className="risk-bar-fill"
            style={{ width: `${Math.min(100, Math.max(0, score || 0))}%`, backgroundColor: color }}
          />
        </div>
      )}
    </div>
  );
}

export default RiskBadge;

export function PriorityBadge({ priority }) {
  const p = (priority || '').toLowerCase();
  const map = {
    critical: ['badge-red', 'Critical'],
    high: ['badge-orange', 'High'],
    urgent: ['badge-red', 'Urgent'],
    medium: ['badge-amber', 'Medium'],
    low: ['badge-green', 'Low'],
    normal: ['badge-blue', 'Normal'],
  };
  const [cls, label] = map[p] || ['badge-gray', priority || 'Normal'];
  return (
    <span className={`badge ${cls}`}>
      <span className="badge-dot" />
      <span>{label}</span>
    </span>
  );
}

export function StatusBadge({ status }) {
  const map = {
    open: ['badge-blue', 'Open'],
    under_investigation: ['badge-amber', 'Under Inv.'],
    closed: ['badge-green', 'Closed'],
    archived: ['badge-gray', 'Archived'],
    pending: ['badge-amber', 'Pending'],
    confirmed: ['badge-green', 'Confirmed'],
    rejected: ['badge-red', 'Rejected'],
    overridden: ['badge-black', 'Overridden'],
    low: ['badge-green', 'Low Risk'],
    medium: ['badge-amber', 'Medium Risk'],
    high: ['badge-orange', 'High Risk'],
    critical: ['badge-red', 'Critical'],
  };
  const [cls, label] = map[status] || ['badge-gray', status];
  return (
    <span className={`badge ${cls}`}>
      <span className="badge-dot" />
      <span>{label}</span>
    </span>
  );
}
