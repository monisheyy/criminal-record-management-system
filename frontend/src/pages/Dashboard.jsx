import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  ArcElement, BarElement, CategoryScale, Chart as ChartJS, Filler, Legend, LinearScale, LineElement, PointElement,
  Tooltip,
} from 'chart.js';
import { Bar, Doughnut, Line } from 'react-chartjs-2';
import {
  Activity, AlertTriangle, Brain, FileText, Gauge, Shield, Siren, Users,
} from 'lucide-react';
import { adminAPI, getErrorMessage, saveBlob } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { ErrorState, LoadingState } from '../components/ui';
import { useApiQuery } from '../utils/useApiQuery';

ChartJS.register(CategoryScale, LinearScale, BarElement, ArcElement, LineElement, PointElement, Filler, Tooltip, Legend);

const ACCENT = '#0071E3';
const QUIET = '#D2D2D7';
const STATUS_COLORS = { open: '#0071E3', under_investigation: '#FF9F0A', closed: '#34C759', archived: '#C7C7CC' };
const FONT = { family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif', size: 12 };

const baseOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: 'rgba(29,29,31,0.92)', titleFont: { ...FONT, weight: '600' }, bodyFont: FONT,
      padding: 10, cornerRadius: 10, displayColors: false,
    },
  },
  scales: {
    x: { ticks: { color: '#86868B', font: FONT }, grid: { display: false }, border: { display: false } },
    y: { ticks: { color: '#86868B', font: FONT, precision: 0 }, grid: { color: '#F0F0F2' }, border: { display: false } },
  },
};

function greeting(now = new Date()) {
  const h = now.getHours();
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}

function StatCard({ icon: Icon, value, label, subtext, onClick }) {
  const clickable = Boolean(onClick);
  const Tag = clickable ? 'button' : 'div';
  return (
    <Tag type={clickable ? 'button' : undefined} className="stat-card" onClick={onClick}
      style={{ cursor: clickable ? 'pointer' : 'default', textAlign: 'left', font: 'inherit', width: '100%' }}>
      <div className="stat-card-header">
        <span className="stat-label">{label}</span>
        <span className="stat-icon" aria-hidden="true"><Icon size={18} strokeWidth={1.6} /></span>
      </div>
      <div className="stat-value">{(value ?? 0).toLocaleString()}</div>
      <div className="stat-subtext">{subtext}</div>
    </Tag>
  );
}

export default function Dashboard() {
  const { user, isAdmin, isOfficer, isClerk } = useAuth();
  const navigate = useNavigate();
  const { data: stats, loading, error, reload: load } = useApiQuery(adminAPI.dashboard, {
    fallbackError: 'Failed to load dashboard statistics.',
  });
  // Read the clock once per visit, not on every render.
  const [today] = useState(() => new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }));

  const exportAnalytics = async (format) => {
    try {
      const res = format === 'excel' ? await adminAPI.dashboardExcel() : await adminAPI.dashboardPdf();
      saveBlob(res, `ai_crms_dashboard_analytics.${format === 'excel' ? 'xlsx' : 'pdf'}`);
      toast.success(`${format === 'excel' ? 'Excel' : 'PDF'} analytics exported.`);
    } catch (err) {
      toast.error(getErrorMessage(err, `Failed to export ${format === 'excel' ? 'Excel' : 'PDF'} analytics.`));
    }
  };

  if (loading && !stats) return <LoadingState label="Loading dashboard…" minHeight="50vh" />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const crimeEntries = Object.entries(stats?.crimes_by_type || {}).sort(([, a], [, b]) => b - a).slice(0, 8);
  const statusEntries = Object.entries(stats?.cases_by_status || {});
  const monthly = stats?.monthly_cases || [];
  const workload = stats?.officer_workload || [];
  const totalCases = statusEntries.reduce((sum, [, v]) => sum + v, 0);
  const agreement = stats?.reviewed_predictions ? stats.reviewer_agreement_rate : null;
  const firstName = user?.full_name?.split(' ')[0] || user?.username;

  const lineData = {
    labels: monthly.map((m) => m.month),
    datasets: [{
      label: 'Cases filed',
      data: monthly.map((m) => m.cases),
      borderColor: ACCENT,
      borderWidth: 2,
      tension: 0.35,
      fill: true,
      backgroundColor: (ctx) => {
        const { chart } = ctx;
        if (!chart.chartArea) return 'rgba(0,113,227,0.08)';
        const g = chart.ctx.createLinearGradient(0, chart.chartArea.top, 0, chart.chartArea.bottom);
        g.addColorStop(0, 'rgba(0,113,227,0.14)');
        g.addColorStop(1, 'rgba(0,113,227,0)');
        return g;
      },
      pointRadius: 0, pointHoverRadius: 5, pointBackgroundColor: ACCENT, pointBorderColor: '#fff', pointBorderWidth: 2,
    }],
  };

  const barData = {
    labels: crimeEntries.map(([k]) => k),
    datasets: [{
      data: crimeEntries.map(([, v]) => v),
      backgroundColor: crimeEntries.map((_, i) => (i === 0 ? ACCENT : QUIET)),
      borderRadius: 6, borderSkipped: false, barThickness: 12,
    }],
  };

  const doughnutData = {
    labels: statusEntries.map(([s]) => s.replace('_', ' ')),
    datasets: [{
      data: statusEntries.map(([, v]) => v),
      backgroundColor: statusEntries.map(([s]) => STATUS_COLORS[s] || '#94A3B8'),
      borderWidth: 3, borderColor: '#fff', hoverOffset: 6,
    }],
  };

  const officerData = {
    labels: workload.map((o) => o.officer.split(' ').slice(-1)[0]),
    datasets: [{
      data: workload.map((o) => o.cases),
      backgroundColor: ACCENT, hoverBackgroundColor: '#0077ED',
      borderRadius: 6, borderSkipped: false, maxBarThickness: 28,
    }],
  };

  return (
    <div>
      <section className="hero" aria-label="Overview">
        <div>
          <div className="hero-eyebrow">{today}</div>
          <h1 className="hero-title">{greeting()}, {firstName}</h1>
          <p className="hero-sub">
            {stats.open_cases} open investigation{stats.open_cases === 1 ? '' : 's'}. {stats.total_criminals} offender records.
            
          </p>
        </div>
        <div className="hero-actions">
          <button type="button" className="btn btn-secondary" onClick={() => exportAnalytics('pdf')}>Export PDF</button>
          <button type="button" className="btn btn-secondary" onClick={() => exportAnalytics('excel')}>Export Excel</button>
          <button type="button" className="btn btn-secondary" onClick={() => navigate('/criminals')}>Add offender</button>
          {(isAdmin || isOfficer) && (
            <button type="button" className="btn btn-primary" onClick={() => navigate('/cases')}>New case</button>
          )}
        </div>
      </section>

      {!isClerk && stats.pending_reviews > 0 && (
        <div className="notice-row" role="status">
          <span>
            <strong>{stats.pending_reviews} AI output{stats.pending_reviews === 1 ? '' : 's'} awaiting review.</strong>{' '}
            Model outputs stay advisory until someone records a reasoned decision.
          </span>
          <button type="button" className="notice-link" onClick={() => navigate('/ai-predictions')}>Review now ›</button>
        </div>
      )}

      <div className="stats-grid kpi-grid">
        <StatCard icon={Shield} value={stats.total_criminals} label="Offender records" subtext="Registered profiles" onClick={() => navigate('/criminals')} />
        <StatCard icon={FileText} value={stats.total_cases} label="Total cases" subtext="FIR & case files" onClick={() => navigate('/cases')} />
        <StatCard icon={Activity} value={stats.open_cases} label="Open cases" subtext="Awaiting investigation" onClick={() => navigate('/cases?status=open')} />
        <StatCard icon={AlertTriangle} value={stats.high_risk_criminals} label="High risk" subtext="Officer-recorded score ≥ 75" onClick={() => navigate('/criminals?sort=-prior_convictions')} />
        <StatCard icon={Brain} value={stats.pending_reviews} label="AI reviews" subtext="Pending human decision" onClick={isClerk ? undefined : () => navigate('/ai-predictions')} />
        <StatCard icon={Siren} value={stats.unread_alerts} label="Unread alerts" subtext="Operational flags for you" onClick={() => navigate('/alerts')} />
      </div>

      <div className="dashboard-split">
        <div className="card chart-card" style={{ margin: 0, textAlign: 'center' }}>
          <div className="card-title" style={{ justifyContent: 'center' }}><Gauge size={16} aria-hidden="true" /> Reviewer agreement</div>
          <div className="gauge" style={{ '--value': agreement ?? 0 }} role="img"
            aria-label={agreement == null ? 'No reviewed AI outputs yet' : `Reviewers confirmed ${agreement}% of reviewed AI outputs`}>
            <div className="gauge-inner"><span className="gauge-value">{agreement == null ? '—' : `${agreement}%`}</span></div>
          </div>
          <p className="td-sub" style={{ marginTop: 12, maxWidth: 240, marginInline: 'auto' }}>
            Share of {stats.reviewed_predictions} reviewed AI outputs that reviewers confirmed. Not a measure of model accuracy.
          </p>
        </div>

        <div className="card chart-card" style={{ margin: 0 }}>
          <div className="card-title"><Activity size={16} aria-hidden="true" /> Case filings</div>
          <div className="chart-sub">New case files per month, last six months</div>
          <div style={{ height: 190 }} role="img" aria-label={`Monthly case filings: ${monthly.map((m) => `${m.month} ${m.cases}`).join(', ')}`}>
            <Line data={lineData} options={baseOptions} />
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
        <div className="card chart-card" style={{ margin: 0 }}>
          <div className="card-title"><Shield size={16} aria-hidden="true" /> Offence distribution</div>
          <div className="chart-sub">Records by primary offence (top 8)</div>
          <div style={{ height: 240 }} role="img" aria-label={`Offence distribution: ${crimeEntries.map(([k, v]) => `${k} ${v}`).join(', ')}`}>
            <Bar data={barData} options={{ ...baseOptions, indexAxis: 'y', scales: {
              x: { ...baseOptions.scales.y }, y: { ...baseOptions.scales.x, ticks: { ...baseOptions.scales.x.ticks, color: '#424245' } },
            } }} />
          </div>
        </div>

        <div className="card chart-card" style={{ margin: 0 }}>
          <div className="card-title"><FileText size={16} aria-hidden="true" /> Case status</div>
          <div className="chart-sub">{totalCases} case files by lifecycle stage</div>
          <div style={{ height: 240, position: 'relative' }} role="img"
            aria-label={`Case status: ${statusEntries.map(([k, v]) => `${k.replace('_', ' ')} ${v}`).join(', ')}`}>
            <Doughnut data={doughnutData} options={{
              ...baseOptions, scales: undefined, cutout: '72%',
              plugins: { ...baseOptions.plugins, legend: { display: true, position: 'bottom', labels: { usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 14, color: '#424245', font: FONT } } },
            }} />
            <div style={{ position: 'absolute', inset: '0 0 44px 0', display: 'grid', placeItems: 'center', pointerEvents: 'none' }}>
              <div style={{ textAlign: 'center' }}>
                <div className="gauge-value">{totalCases}</div>
                <div className="td-sub">cases</div>
              </div>
            </div>
          </div>
        </div>

        <div className="card chart-card" style={{ margin: 0 }}>
          <div className="card-title"><Users size={16} aria-hidden="true" /> Officer workload</div>
          <div className="chart-sub">Active (open + under investigation) cases per officer</div>
          <div style={{ height: 240 }} role="img" aria-label={`Active cases per officer: ${workload.map((o) => `${o.officer} ${o.cases}`).join(', ')}`}>
            <Bar data={officerData} options={baseOptions} />
          </div>
        </div>
      </div>
    </div>
  );
}
