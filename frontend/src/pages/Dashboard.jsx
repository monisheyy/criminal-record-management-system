import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { adminAPI, getErrorMessage, saveBlob } from '../services/api';
import { ErrorState, LoadingState } from '../components/ui';
import toast from 'react-hot-toast';
import { useAuth } from '../contexts/AuthContext';
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement,
  Title, Tooltip, Legend, ArcElement, LineElement, PointElement
} from 'chart.js';
import { Bar, Doughnut, Line } from 'react-chartjs-2';
import {
  Shield, FileText, AlertTriangle, Brain, Users, Siren,
  Activity, Plus, FolderPlus, Download
} from 'lucide-react';

ChartJS.register(
  CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend,
  ArcElement, LineElement, PointElement
);

const CHART_DEFAULTS = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      labels: { color: '#475467', font: { family: 'Inter', size: 11 } }
    }
  },
  scales: {
    x: { ticks: { color: '#98A2B3', font: { size: 10, family: 'Inter' } }, grid: { color: '#F2F4F7' } },
    y: { ticks: { color: '#98A2B3', font: { size: 10, family: 'Inter' } }, grid: { color: '#F2F4F7' } }
  }
};

function StatCard({ icon: Icon, value, label, subtext, onClick }) {
  return (
    <div className="stat-card" onClick={onClick} style={{ cursor: onClick ? 'pointer' : 'default' }}>
      <div className="stat-card-header">
        <span className="stat-label">{label}</span>
        <div className="stat-icon"><Icon size={14} /></div>
      </div>
      <div className="stat-value">{value?.toLocaleString?.() ?? value ?? 0}</div>
      {subtext && <div className="stat-subtext">{subtext}</div>}
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = () => {
    setLoading(true);
    setError('');
    adminAPI.dashboard()
      .then(r => setStats(r.data))
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

  const crimeTypes = stats?.crimes_by_type || {};
  const caseStatuses = stats?.cases_by_status || {};

  const barData = {
    labels: Object.keys(crimeTypes).slice(0, 8),
    datasets: [{
      label: 'Criminals',
      data: Object.values(crimeTypes).slice(0, 8),
      backgroundColor: '#2563EB',
      borderColor: '#1D4ED8',
      borderWidth: 0,
      borderRadius: 6,
    }]
  };

  const statusColors = {
    open: '#2563EB',
    under_investigation: '#D97706',
    closed: '#16A34A',
    archived: '#98A2B3',
  };

  const doughnutData = {
    labels: Object.keys(caseStatuses).map(s => s.replace('_', ' ')),
    datasets: [{
      data: Object.values(caseStatuses),
      backgroundColor: Object.keys(caseStatuses).map(s => statusColors[s] || '#98A2B3'),
      borderWidth: 0,
    }]
  };

  const lineData = {
    labels: (stats?.monthly_cases || []).map(m => m.month),
    datasets: [{
      label: 'Cases Filed',
      data: (stats?.monthly_cases || []).map(m => m.cases),
      borderColor: '#2563EB',
      backgroundColor: 'rgba(37, 99, 235, 0.05)',
      fill: true,
      tension: 0.2,
      pointBackgroundColor: '#2563EB',
      pointRadius: 3,
    }]
  };

  const officerData = {
    labels: (stats?.officer_workload || []).map(o => o.officer.split(' ').slice(-1)[0]),
    datasets: [{
      label: 'Active Cases',
      data: (stats?.officer_workload || []).map(o => o.cases),
      backgroundColor: '#6366F1',
      borderColor: '#4F46E5',
      borderWidth: 0,
      borderRadius: 6,
    }]
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Command Center</h1>
          <p className="page-subtitle">Welcome back, {user?.full_name}</p>
        </div>
        <div className="header-actions">
          <button className="btn btn-secondary" onClick={() => exportAnalytics('pdf')}>
            <Download size={14} /> Export PDF
          </button>
          <button className="btn btn-secondary" onClick={() => exportAnalytics('excel')}>
            <Download size={14} /> Export Excel
          </button>
          <button className="btn btn-secondary" onClick={() => navigate('/criminals')}>
            <Plus size={14} /> Add Offender
          </button>
          <button className="btn btn-primary" onClick={() => navigate('/cases')}>
            <FolderPlus size={14} /> New Case
          </button>
        </div>
      </div>

      {/* High-Risk Banner */}
      {stats?.high_risk_criminals > 0 && (
        <div className="alert alert-error" style={{ justifyContent: 'space-between', padding: '12px 16px', marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <AlertTriangle size={16} />
            <div>
              <div style={{ fontWeight: 600 }}>
                {stats.high_risk_criminals} record(s) with a high officer-recorded risk score
              </div>
              <div style={{ fontSize: '0.75rem', opacity: 0.85, marginTop: 1 }}>
                {stats.pending_reviews} AI output(s) awaiting human review
              </div>
            </div>
          </div>
          <button className="btn btn-danger btn-sm" onClick={() => navigate(user?.role === 'record_clerk' ? '/alerts' : '/ai-predictions')}>
            Review
          </button>
        </div>
      )}

      {/* Barometer KPI Grid */}
      <div className="stats-grid">
        <StatCard icon={Shield} value={stats?.total_criminals} label="Offender Dossiers" subtext="Registered profiles" onClick={() => navigate('/criminals')} />
        <StatCard icon={FileText} value={stats?.total_cases} label="Total Cases" subtext="FIR & case files" onClick={() => navigate('/cases')} />
        <StatCard icon={Activity} value={stats?.open_cases} label="Open Cases" subtext="Active investigations" onClick={() => navigate('/cases?status=open')} />
        <StatCard icon={AlertTriangle} value={stats?.high_risk_criminals} label="High Risk" subtext="Critical threat rating" onClick={() => navigate('/alerts')} />
        <StatCard icon={Brain} value={stats?.pending_reviews} label="AI Reviews" subtext="Pending human review" onClick={user?.role === 'record_clerk' ? undefined : () => navigate('/ai-predictions')} />
        <StatCard icon={Siren} value={stats?.unread_alerts} label="Alerts" subtext="Unread operational flags" onClick={() => navigate('/alerts')} />
      </div>

      {/* Reviewer agreement & filing trend */}
      <div className="dashboard-split">
        <div className="card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center', margin: 0 }}>
          <div style={{ fontSize: '0.68rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 8 }}>
            Reviewer agreement rate
          </div>
          <div style={{ fontSize: '2.4rem', fontWeight: 700, fontFamily: 'JetBrains Mono, monospace', color: 'var(--text-primary)', lineHeight: 1 }}>
            {stats?.reviewed_predictions ? `${stats?.reviewer_agreement_rate ?? 0}%` : '—'}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 8, maxWidth: 220 }}>
            Share of {stats?.reviewed_predictions ?? 0} reviewed AI outputs that reviewers confirmed. This is not a measure of model accuracy.
          </div>
        </div>

        <div className="card" style={{ margin: 0 }}>
          <div className="card-title" style={{ marginBottom: 12 }}>
            <Activity size={15} style={{ color: 'var(--accent-blue)' }} /> Monthly Case Filings
          </div>
          <div style={{ height: 130 }} role="img" aria-label={`Monthly case filings: ${(stats?.monthly_cases || []).map(m => `${m.month} ${m.cases}`).join(', ')}`}>
            <Line data={lineData} options={{ ...CHART_DEFAULTS, plugins: { ...CHART_DEFAULTS.plugins, legend: { display: false } } }} />
          </div>
        </div>
      </div>

      {/* Visual Analytics Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
        <div className="card" style={{ margin: 0 }}>
          <div className="card-title" style={{ marginBottom: 12 }}>
            <Shield size={15} style={{ color: 'var(--accent-blue)' }} /> Offence Distribution
          </div>
          <div style={{ height: 200 }} role="img" aria-label={`Offence distribution: ${Object.entries(crimeTypes).map(([k, v]) => `${k} ${v}`).join(', ')}`}>
            <Bar data={barData} options={{
              ...CHART_DEFAULTS,
              indexAxis: 'y',
              plugins: { ...CHART_DEFAULTS.plugins, legend: { display: false } }
            }} />
          </div>
        </div>

        <div className="card" style={{ margin: 0 }}>
          <div className="card-title" style={{ marginBottom: 12 }}>
            <FileText size={15} style={{ color: 'var(--accent-blue)' }} /> Case Status Breakdown
          </div>
          <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} role="img" aria-label={`Case status: ${Object.entries(caseStatuses).map(([k, v]) => `${k.replace('_', ' ')} ${v}`).join(', ')}`}>
            <Doughnut data={doughnutData} options={{
              ...CHART_DEFAULTS,
              cutout: '75%',
              scales: undefined
            }} />
          </div>
        </div>

        <div className="card" style={{ margin: 0 }}>
          <div className="card-title" style={{ marginBottom: 12 }}>
            <Users size={15} style={{ color: 'var(--accent-blue)' }} /> Officer Workload
          </div>
          <div style={{ height: 200 }} role="img" aria-label={`Open cases per officer: ${(stats?.officer_workload || []).map(o => `${o.officer} ${o.cases}`).join(', ')}`}>
            <Bar data={officerData} options={{
              ...CHART_DEFAULTS,
              plugins: { ...CHART_DEFAULTS.plugins, legend: { display: false } }
            }} />
          </div>
        </div>
      </div>
    </div>
  );
}
