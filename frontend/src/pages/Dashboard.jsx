import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  ArcElement, BarElement, CategoryScale, Chart as ChartJS, Filler, Legend, LinearScale, LineElement, PointElement,
  Tooltip,
} from 'chart.js';
import { Bar, Doughnut, Line } from 'react-chartjs-2';
import {
  Activity, AlertTriangle, ArrowRight, Brain, Download, FileText, FolderPlus, Gauge, Shield, Siren, UserPlus, Users,
} from 'lucide-react';
import { adminAPI, getErrorMessage, saveBlob } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { ErrorState, LoadingState } from '../components/ui';

ChartJS.register(CategoryScale, LinearScale, BarElement, ArcElement, LineElement, PointElement, Filler, Tooltip, Legend);

const PALETTE = ['#6366F1', '#8B5CF6', '#0EA5E9', '#10B981', '#F59E0B', '#F43F5E', '#14B8A6', '#A855F7'];
const STATUS_COLORS = { open: '#6366F1', under_investigation: '#F59E0B', closed: '#10B981', archived: '#94A3B8' };
const FONT = { family: 'Inter, system-ui, sans-serif', size: 11 };

const baseOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: '#0E1424', titleFont: { ...FONT, weight: '600' }, bodyFont: FONT,
      padding: 10, cornerRadius: 10, displayColors: false,
    },
  },
  scales: {
    x: { ticks: { color: '#8A93AD', font: FONT }, grid: { display: false }, border: { display: false } },
    y: { ticks: { color: '#8A93AD', font: FONT, precision: 0 }, grid: { color: '#EEF0F6' }, border: { display: false } },
  },
};

function greeting(now = new Date()) {
  const h = now.getHours();
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}

function StatCard({ icon: Icon, value, label, subtext, tone, onClick }) {
  const clickable = Boolean(onClick);
  const Tag = clickable ? 'button' : 'div';
  return (
    <Tag type={clickable ? 'button' : undefined} className={`stat-card tone-${tone}`} onClick={onClick}
      style={{ cursor: clickable ? 'pointer' : 'default', textAlign: 'left', font: 'inherit', width: '100%' }}>
      <div className="stat-card-header">
        <span className="stat-label">{label}</span>
        <span className="stat-icon" aria-hidden="true"><Icon size={17} /></span>
      </div>
      <div className="stat-value">{(value ?? 0).toLocaleString()}</div>
      <div className="stat-subtext">{subtext}</div>
    </Tag>
  );
}

export default function Dashboard() {
  const { user, isAdmin, isOfficer, isClerk } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = () => {
    setLoading(true);
    setError('');
    adminAPI.dashboard()
      .then((r) => setStats(r.data))
      .catch((err) => setError(getErrorMessage(err, 'Failed to load dashboard statistics.')))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const exportAnalytics = async (format) => {
    try {
      const res = format === 'excel' ? await adminAPI.dashboardExcel() : await adminAPI.dashboardPdf();
      saveBlob(res, `ai_crms_dashboard_analytics.${format === 'excel' ? 'xlsx' : 'pdf'}`);
      toast.success(`${format === 'excel' ? 'Excel' : 'PDF'} analytics exported.`);
    } catch (err) {
      toast.error(getErrorMessage(err, `Failed to export ${format === 'excel' ? 'Excel' : 'PDF'} analytics.`));
    }
  };

  if (loading) return <LoadingState label="Loading dashboard…" minHeight="50vh" />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const crimeEntries = Object.entries(stats?.crimes_by_type || {}).sort(([, a], [, b]) => b - a).slice(0, 8);
  const statusEntries = Object.entries(stats?.cases_by_status || {});
  const monthly = stats?.monthly_cases || [];
  const workload = stats?.officer_workload || [];
  const totalCases = statusEntries.reduce((sum, [, v]) => sum + v, 0);
  const agreement = stats?.reviewed_predictions ? stats.reviewer_agreement_rate : null;
  const firstName = user?.full_name?.split(' ')[0] || user?.username;
  const today = new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

  const lineData = {
    labels: monthly.map((m) => m.month),
    datasets: [{
      label: 'Cases filed',
      data: monthly.map((m) => m.cases),
      borderColor: '#6366F1',
      borderWidth: 2.5,
      tension: 0.35,
      fill: true,
      backgroundColor: (ctx) => {
        const { chart } = ctx;
        if (!chart.chartArea) return 'rgba(99,102,241,0.12)';
        const g = chart.ctx.createLinearGradient(0, chart.chartArea.top, 0, chart.chartArea.bottom);
        g.addColorStop(0, 'rgba(99,102,241,0.28)');
        g.addColorStop(1, 'rgba(99,102,241,0)');
        return g;
      },
      pointRadius: 4, pointHoverRadius: 6, pointBackgroundColor: '#fff', pointBorderColor: '#6366F1', pointBorderWidth: 2,
    }],
  };

  const barData = {
    labels: crimeEntries.map(([k]) => k),
    datasets: [{
      data: crimeEntries.map(([, v]) => v),
      backgroundColor: crimeEntries.map((_, i) => PALETTE[i % PALETTE.length]),
      borderRadius: 8, borderSkipped: false, barThickness: 14,
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
      backgroundColor: 'rgba(139,92,246,0.85)', hoverBackgroundColor: '#7C3AED',
      borderRadius: 8, borderSkipped: false, maxBarThickness: 36,
    }],
  };

  return (
    <div>
      <section className="hero" aria-label="Overview">
        <div>
          <div className="hero-eyebrow">{today}</div>
          <h1 className="hero-title">{greeting()}, {firstName}</h1>
          <p className="hero-sub">
            {stats.open_cases} open investigation{stats.open_cases === 1 ? '' : 's'} · {stats.total_criminals} offender records
            {!isClerk && <> · {stats.pending_reviews} AI output{stats.pending_reviews === 1 ? '' : 's'} awaiting review</>}
          </p>
        </div>
        <div className="hero-actions">
          <button type="button" className="btn btn-glass" onClick={() => exportAnalytics('pdf')}><Download size={14} aria-hidden="true" /> Export PDF</button>
          <button type="button" className="btn btn-glass" onClick={() => exportAnalytics('excel')}><Download size={14} aria-hidden="true" /> Export Excel</button>
          <button type="button" className="btn btn-glass" onClick={() => navigate('/criminals')}><UserPlus size={14} aria-hidden="true" /> Add offender</button>
          {(isAdmin || isOfficer) && (
            <button type="button" className="btn btn-light" onClick={() => navigate('/cases')}><FolderPlus size={14} aria-hidden="true" /> New case</button>
          )}
        </div>
      </section>

      {!isClerk && stats.pending_reviews > 0 && (
        <div className="attention-strip" role="status">
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <span className="attention-icon" aria-hidden="true"><AlertTriangle size={18} /></span>
            <div>
              <div style={{ fontWeight: 650, color: 'var(--text-primary)' }}>
                {stats.pending_reviews} AI output{stats.pending_reviews === 1 ? '' : 's'} need{stats.pending_reviews === 1 ? 's' : ''} a human decision
              </div>
              <div className="td-sub">Model outputs are advisory until a reviewer records a reasoned decision.</div>
            </div>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => navigate('/ai-predictions')}>
            Open review queue <ArrowRight size={13} aria-hidden="true" />
          </button>
        </div>
      )}

      <div className="stats-grid kpi-grid">
        <StatCard tone="indigo" icon={Shield} value={stats.total_criminals} label="Offender records" subtext="Registered profiles" onClick={() => navigate('/criminals')} />
        <StatCard tone="sky" icon={FileText} value={stats.total_cases} label="Total cases" subtext="FIR & case files" onClick={() => navigate('/cases')} />
        <StatCard tone="emerald" icon={Activity} value={stats.open_cases} label="Open cases" subtext="Awaiting investigation" onClick={() => navigate('/cases?status=open')} />
        <StatCard tone="rose" icon={AlertTriangle} value={stats.high_risk_criminals} label="High risk" subtext="Officer-recorded score ≥ 75" onClick={() => navigate('/criminals?sort=-prior_convictions')} />
        <StatCard tone="violet" icon={Brain} value={stats.pending_reviews} label="AI reviews" subtext="Pending human decision" onClick={isClerk ? undefined : () => navigate('/ai-predictions')} />
        <StatCard tone="amber" icon={Siren} value={stats.unread_alerts} label="Unread alerts" subtext="Operational flags for you" onClick={() => navigate('/alerts')} />
      </div>

      <div className="dashboard-split">
        <div className="card chart-card" style={{ margin: 0, textAlign: 'center' }}>
          <div className="card-title" style={{ justifyContent: 'center' }}><Gauge size={16} aria-hidden="true" style={{ color: 'var(--brand-500)' }} /> Reviewer agreement</div>
          <div className="gauge" style={{ '--value': agreement ?? 0 }} role="img"
            aria-label={agreement == null ? 'No reviewed AI outputs yet' : `Reviewers confirmed ${agreement}% of reviewed AI outputs`}>
            <div className="gauge-inner"><span className="gauge-value">{agreement == null ? '—' : `${agreement}%`}</span></div>
          </div>
          <p className="td-sub" style={{ marginTop: 12, maxWidth: 240, marginInline: 'auto' }}>
            Share of {stats.reviewed_predictions} reviewed AI outputs that reviewers confirmed. Not a measure of model accuracy.
          </p>
        </div>

        <div className="card chart-card" style={{ margin: 0 }}>
          <div className="card-title"><Activity size={16} aria-hidden="true" style={{ color: 'var(--brand-500)' }} /> Case filings</div>
          <div className="chart-sub">New case files per month, last six months</div>
          <div style={{ height: 190 }} role="img" aria-label={`Monthly case filings: ${monthly.map((m) => `${m.month} ${m.cases}`).join(', ')}`}>
            <Line data={lineData} options={baseOptions} />
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
        <div className="card chart-card" style={{ margin: 0 }}>
          <div className="card-title"><Shield size={16} aria-hidden="true" style={{ color: 'var(--brand-500)' }} /> Offence distribution</div>
          <div className="chart-sub">Records by primary offence (top 8)</div>
          <div style={{ height: 240 }} role="img" aria-label={`Offence distribution: ${crimeEntries.map(([k, v]) => `${k} ${v}`).join(', ')}`}>
            <Bar data={barData} options={{ ...baseOptions, indexAxis: 'y', scales: {
              x: { ...baseOptions.scales.y }, y: { ...baseOptions.scales.x, ticks: { ...baseOptions.scales.x.ticks, color: '#4A5470' } },
            } }} />
          </div>
        </div>

        <div className="card chart-card" style={{ margin: 0 }}>
          <div className="card-title"><FileText size={16} aria-hidden="true" style={{ color: 'var(--brand-500)' }} /> Case status</div>
          <div className="chart-sub">{totalCases} case files by lifecycle stage</div>
          <div style={{ height: 240, position: 'relative' }} role="img"
            aria-label={`Case status: ${statusEntries.map(([k, v]) => `${k.replace('_', ' ')} ${v}`).join(', ')}`}>
            <Doughnut data={doughnutData} options={{
              ...baseOptions, scales: undefined, cutout: '72%',
              plugins: { ...baseOptions.plugins, legend: { display: true, position: 'bottom', labels: { usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 14, color: '#4A5470', font: FONT } } },
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
          <div className="card-title"><Users size={16} aria-hidden="true" style={{ color: 'var(--brand-500)' }} /> Officer workload</div>
          <div className="chart-sub">Active (open + under investigation) cases per officer</div>
          <div style={{ height: 240 }} role="img" aria-label={`Active cases per officer: ${workload.map((o) => `${o.officer} ${o.cases}`).join(', ')}`}>
            <Bar data={officerData} options={baseOptions} />
          </div>
        </div>
      </div>
    </div>
  );
}
