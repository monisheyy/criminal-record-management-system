import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  Download, UserPlus, FileText, Shield, Activity, MapPin, 
  Calendar, AlertCircle, X, Users, Paperclip, CheckCircle, ChevronLeft, Plus
} from 'lucide-react';
import toast from 'react-hot-toast';
import { casesAPI } from '../services/api';
import NetworkGraph from '../components/NetworkGraph';
import { StatusBadge, PriorityBadge } from '../components/RiskBadge';

const CaseDetails = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [caseDetails, setCaseDetails] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');

  const [modals, setModals] = useState({
    criminal: false,
    victim: false,
    evidence: false,
    assign: false
  });

  const [criminalForm, setCriminalForm] = useState({ id: '', role: 'Suspect' });
  const [evidenceForm, setEvidenceForm] = useState({ description: '', type: '', location: '', status: 'Collected' });
  const [victimForm, setVictimForm] = useState({ name: '', contactInfo: '', condition: '' });
  const [assignForm, setAssignForm] = useState({ officerId: '' });

  useEffect(() => {
    fetchCaseDetails();
  }, [id]);

  const fetchCaseDetails = async () => {
    try {
      setLoading(true);
      const fn = casesAPI.get || casesAPI.getById;
      const response = await fn(id);
      setCaseDetails(response.data || response);
    } catch (err) {
      setError(err.message || 'Failed to fetch case details.');
    } finally {
      setLoading(false);
    }
  };

  const toggleModal = (modalName, show) => {
    setModals(prev => ({ ...prev, [modalName]: show }));
  };

  const handleAddCriminal = async (e) => {
    e.preventDefault();
    try {
      if (casesAPI.addCriminal) {
        await casesAPI.addCriminal(id, criminalForm.id, criminalForm.role);
      }
      toast.success('Criminal linked to case.');
      toggleModal('criminal', false);
      fetchCaseDetails();
    } catch (err) {
      toast.error('Error linking criminal: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleAddEvidence = async (e) => {
    e.preventDefault();
    try {
      await casesAPI.addEvidence(id, evidenceForm);
      toast.success('Evidence item logged.');
      toggleModal('evidence', false);
      fetchCaseDetails();
    } catch (err) {
      toast.error('Error adding evidence: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleAddVictim = async (e) => {
    e.preventDefault();
    try {
      await casesAPI.addVictim(id, victimForm);
      toast.success('Victim information added.');
      toggleModal('victim', false);
      fetchCaseDetails();
    } catch (err) {
      toast.error('Error adding victim: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleAssignOfficer = async (e) => {
    e.preventDefault();
    try {
      if (casesAPI.assign) {
        await casesAPI.assign(id, assignForm.officerId);
      } else if (casesAPI.assignOfficer) {
        await casesAPI.assignOfficer(id, assignForm);
      }
      toast.success('Investigating officer assigned.');
      toggleModal('assign', false);
      fetchCaseDetails();
    } catch (err) {
      toast.error('Error assigning officer: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleDownloadReport = async (format = 'pdf') => {
    try {
      const res = format === 'excel' ? await casesAPI.reportExcel(id) : await casesAPI.report(id);
      const url = window.URL.createObjectURL(new Blob([res.data || res]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `case_report_${caseDetails.case_number || caseDetails.caseNumber || id}.${format === 'excel' ? 'xlsx' : 'pdf'}`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success(`Case ${format === 'excel' ? 'Excel' : 'PDF'} report downloaded.`);
    } catch (err) {
      toast.error(`Failed to download case ${format === 'excel' ? 'Excel' : 'PDF'} report.`);
    }
  };

  if (loading) return (
    <div className="empty-state" style={{ minHeight: '60vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
      <div className="spinner" style={{ width: 28, height: 28, marginBottom: 12 }} />
      <div className="empty-state-title">Loading Case Workspace...</div>
    </div>
  );

  if (error || !caseDetails) return (
    <div className="empty-state">
      <AlertCircle size={36} style={{ color: 'var(--status-red)' }} />
      <div className="empty-state-title">Error Loading Case File</div>
      <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 4 }}>{error || 'Case file not found'}</p>
      <button className="btn btn-secondary" style={{ marginTop: 16 }} onClick={() => navigate('/cases')}>
        Back to Cases Workspace
      </button>
    </div>
  );

  const caseNum = caseDetails.case_number || caseDetails.caseNumber || `CASE-${caseDetails.id}`;
  const crimeType = caseDetails.crime_type || caseDetails.crimeType || 'Unclassified';
  const incidentDate = caseDetails.incident_date || caseDetails.incidentDate;

  return (
    <div>
      {/* Header */}
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button className="btn btn-secondary btn-icon" onClick={() => navigate('/cases')}>
            <ChevronLeft size={16} />
          </button>
          <div>
            <h1 className="page-title">{caseDetails.title}</h1>
            <p className="page-subtitle">Case #: <span className="mono">{caseNum}</span> · {crimeType}</p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-secondary" onClick={() => handleDownloadReport('pdf')}>
            <Download size={14} /> PDF Report
          </button>
          <button className="btn btn-secondary" onClick={() => handleDownloadReport('excel')}>
            <FileText size={14} /> Excel Report
          </button>
          <button className="btn btn-primary" onClick={() => toggleModal('assign', true)}>
            <UserPlus size={14} /> Assign Officer
          </button>
        </div>
      </div>

      {/* Case Header Details Banner */}
      <div className="card">
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 16 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Activity size={14} style={{ color: 'var(--accent-blue)' }} /> Status: <StatusBadge status={caseDetails.status || 'open'} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Shield size={14} style={{ color: 'var(--accent-blue)' }} /> Priority: <PriorityBadge priority={caseDetails.priority || 'Medium'} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <MapPin size={14} style={{ color: 'var(--accent-blue)' }} /> Location: <strong style={{ color: 'var(--text-primary)' }}>{caseDetails.location || 'N/A'}</strong>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Calendar size={14} style={{ color: 'var(--accent-blue)' }} /> Incident: <span className="mono">{incidentDate ? new Date(incidentDate).toLocaleDateString() : 'N/A'}</span>
            </div>
          </div>
        </div>

        <div className="alert alert-info" style={{ marginBottom: 0 }}>
          <CheckCircle size={15} />
          <span>Assigned Officer: <strong>{caseDetails.assignedOfficer?.name || caseDetails.assigned_officer?.full_name || 'Unassigned'}</strong></span>
        </div>
      </div>

      <NetworkGraph caseId={Number(id)} depth={2} />

      {/* Navigation Tabs */}
      <div className="tab-nav">
        {[
          { id: 'overview', name: 'Case Overview', icon: FileText },
          { id: 'criminals', name: 'Criminals & Suspects', icon: Shield },
          { id: 'victims', name: 'Victims List', icon: Users },
          { id: 'evidence', name: 'Evidence Log', icon: Paperclip },
        ].map((t) => {
          const Icon = t.icon;
          return (
            <div
              key={t.id}
              className={`tab-item ${activeTab === t.id ? 'active' : ''}`}
              onClick={() => setActiveTab(t.id)}
              style={{ display: 'flex', alignItems: 'center', gap: 6 }}
            >
              <Icon size={14} /> {t.name}
            </div>
          );
        })}
      </div>

      {/* Tab Panels */}
      {activeTab === 'overview' && (
        <div className="card">
          <div className="card-title" style={{ marginBottom: 10 }}>FIR Summary & Case Description</div>
          <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
            {caseDetails.description || 'No detailed case summary provided.'}
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border-subtle)' }}>
            <div>
              <div className="form-label">Reporter Name</div>
              <div className="td-primary">{caseDetails.reporterName || caseDetails.reporter_name || 'N/A'}</div>
            </div>
            <div>
              <div className="form-label">Filing Officer</div>
              <div className="td-primary">{caseDetails.assignedOfficer?.name || 'Central Command'}</div>
            </div>
            <div>
              <div className="form-label">Last Updated</div>
              <div className="mono" style={{ fontSize: '0.8rem' }}>{new Date(caseDetails.updatedAt || caseDetails.created_at || Date.now()).toLocaleString()}</div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'criminals' && (
        <div className="table-container">
          <div className="table-toolbar">
            <span className="table-title">Linked Criminals & Suspects</span>
            <button className="btn btn-primary btn-sm" onClick={() => toggleModal('criminal', true)}>
              <Plus size={13} /> Link Criminal
            </button>
          </div>
          {caseDetails.criminals?.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Record ID</th>
                  <th>Suspect Name</th>
                  <th>Role in Case</th>
                </tr>
              </thead>
              <tbody>
                {caseDetails.criminals.map((c, i) => (
                  <tr key={i}>
                    <td className="td-mono">CRM-{c.id || c.criminal_id}</td>
                    <td className="td-primary">{c.name || c.full_name || `Record #${c.id}`}</td>
                    <td>
                      <span className="badge badge-red">{c.role || 'Suspect'}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty-state">
              <Shield size={28} style={{ opacity: 0.3 }} />
              <div className="empty-state-title">No suspects or criminals linked</div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'victims' && (
        <div className="table-container">
          <div className="table-toolbar">
            <span className="table-title">Victims Log</span>
            <button className="btn btn-primary btn-sm" onClick={() => toggleModal('victim', true)}>
              <Plus size={13} /> Add Victim
            </button>
          </div>
          {caseDetails.victims?.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Victim Name</th>
                  <th>Contact Information</th>
                  <th>Status / Condition</th>
                </tr>
              </thead>
              <tbody>
                {caseDetails.victims.map((v, i) => (
                  <tr key={i}>
                    <td className="td-primary">{v.name}</td>
                    <td>{v.contactInfo || v.contact_info || 'N/A'}</td>
                    <td>
                      <span className="badge badge-amber">{v.condition || 'Recorded'}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty-state">
              <Users size={28} style={{ opacity: 0.3 }} />
              <div className="empty-state-title">No victim records added</div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'evidence' && (
        <div className="table-container">
          <div className="table-toolbar">
            <span className="table-title">Evidence Inventory</span>
            <button className="btn btn-primary btn-sm" onClick={() => toggleModal('evidence', true)}>
              <Plus size={13} /> Log Evidence
            </button>
          </div>
          {caseDetails.evidence?.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Item Type</th>
                  <th>Description</th>
                  <th>Location Found</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {caseDetails.evidence.map((e, i) => (
                  <tr key={i}>
                    <td>
                      <span className="badge badge-purple">{e.type || 'Physical'}</span>
                    </td>
                    <td className="td-primary">{e.description}</td>
                    <td>{e.location}</td>
                    <td>
                      <span className="badge badge-green">{e.status || 'Collected'}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty-state">
              <Paperclip size={28} style={{ opacity: 0.3 }} />
              <div className="empty-state-title">No evidence items logged</div>
            </div>
          )}
        </div>
      )}

      {/* --- MODALS --- */}
      {modals.criminal && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <span className="modal-title">Link Criminal / Suspect</span>
              <button className="btn btn-ghost btn-icon" onClick={() => toggleModal('criminal', false)}><X size={16} /></button>
            </div>
            <form onSubmit={handleAddCriminal}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Criminal Record ID *</label>
                  <input className="form-control" required type="number" value={criminalForm.id} onChange={(e) => setCriminalForm({...criminalForm, id: e.target.value})} placeholder="e.g. 102" />
                </div>
                <div className="form-group">
                  <label className="form-label">Role in Case *</label>
                  <select className="form-select" value={criminalForm.role} onChange={(e) => setCriminalForm({...criminalForm, role: e.target.value})}>
                    <option value="Suspect">Suspect</option>
                    <option value="Accused">Accused</option>
                    <option value="Primary Offender">Primary Offender</option>
                    <option value="Accomplice">Accomplice</option>
                  </select>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => toggleModal('criminal', false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Link Record</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {modals.evidence && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <span className="modal-title">Log Evidence Item</span>
              <button className="btn btn-ghost btn-icon" onClick={() => toggleModal('evidence', false)}><X size={16} /></button>
            </div>
            <form onSubmit={handleAddEvidence}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Evidence Description *</label>
                  <input className="form-control" required type="text" value={evidenceForm.description} onChange={(e) => setEvidenceForm({...evidenceForm, description: e.target.value})} />
                </div>
                <div className="form-group">
                  <label className="form-label">Evidence Category *</label>
                  <select className="form-select" value={evidenceForm.type} onChange={(e) => setEvidenceForm({...evidenceForm, type: e.target.value})}>
                    <option value="">Select Category...</option>
                    <option value="Weapon">Weapon</option>
                    <option value="Document">Document</option>
                    <option value="Digital">Digital</option>
                    <option value="Biological">Biological</option>
                    <option value="Other">Other</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Location Found *</label>
                  <input className="form-control" required type="text" value={evidenceForm.location} onChange={(e) => setEvidenceForm({...evidenceForm, location: e.target.value})} />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => toggleModal('evidence', false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Save Item</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {modals.victim && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <span className="modal-title">Add Victim Details</span>
              <button className="btn btn-ghost btn-icon" onClick={() => toggleModal('victim', false)}><X size={16} /></button>
            </div>
            <form onSubmit={handleAddVictim}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Victim Full Name *</label>
                  <input className="form-control" required type="text" value={victimForm.name} onChange={(e) => setVictimForm({...victimForm, name: e.target.value})} />
                </div>
                <div className="form-group">
                  <label className="form-label">Contact Information *</label>
                  <input className="form-control" required type="text" value={victimForm.contactInfo} onChange={(e) => setVictimForm({...victimForm, contactInfo: e.target.value})} />
                </div>
                <div className="form-group">
                  <label className="form-label">Status / Condition *</label>
                  <input className="form-control" required type="text" value={victimForm.condition} onChange={(e) => setVictimForm({...victimForm, condition: e.target.value})} placeholder="e.g. Unharmed, Hospitalized" />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => toggleModal('victim', false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Save Victim</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {modals.assign && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <span className="modal-title">Assign Investigating Officer</span>
              <button className="btn btn-ghost btn-icon" onClick={() => toggleModal('assign', false)}><X size={16} /></button>
            </div>
            <form onSubmit={handleAssignOfficer}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Officer User ID *</label>
                  <input className="form-control" required type="number" value={assignForm.officerId} onChange={(e) => setAssignForm({ officerId: e.target.value })} placeholder="Enter Officer ID (e.g. 2)" />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => toggleModal('assign', false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Assign Officer</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default CaseDetails;
