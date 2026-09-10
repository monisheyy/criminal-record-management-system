import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Plus, Filter, AlertCircle, X, FileText, ChevronRight } from 'lucide-react';
import { casesAPI } from '../services/api';
import { StatusBadge, PriorityBadge } from '../components/RiskBadge';

const Cases = () => {
  const navigate = useNavigate();
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('All');
  
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    crimeType: '',
    location: '',
    incidentDate: '',
    priority: 'Medium'
  });

  useEffect(() => {
    fetchCases();
  }, []);

  const fetchCases = async () => {
    try {
      setLoading(true);
      const fn = casesAPI.list || casesAPI.getAll;
      const response = await fn();
      setCases(response.data || response || []);
    } catch (err) {
      setError(err.message || 'Failed to fetch case list.');
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await casesAPI.create({
        title: formData.title,
        description: formData.description,
        crime_type: formData.crimeType || formData.crime_type,
        location: formData.location,
        incident_date: formData.incidentDate,
        priority: formData.priority
      });
      setIsModalOpen(false);
      setFormData({
        title: '', description: '', crimeType: '', location: '', incidentDate: '', priority: 'Medium'
      });
      fetchCases();
    } catch (err) {
      alert('Failed to create case: ' + (err.response?.data?.detail || err.message || 'Unknown error'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const filteredCases = cases.filter(c => {
    const number = c.case_number || c.caseNumber || `CASE-${c.id}`;
    const title = c.title || '';
    const matchesSearch = title.toLowerCase().includes(searchTerm.toLowerCase()) || 
                          number.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = statusFilter === 'All' || c.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Cases &amp; FIR Workspace</h1>
          <p className="page-subtitle">Investigation case management, FIR logs, and officer assignments</p>
        </div>
        <button className="btn btn-primary" onClick={() => setIsModalOpen(true)}>
          <Plus size={14} /> Register New Case
        </button>
      </div>

      <div className="table-container">
        <div className="table-toolbar">
          <div style={{ position: 'relative', flex: 1, maxWidth: '360px' }}>
            <Search size={13} style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input 
              className="form-control"
              style={{ paddingLeft: '30px', fontSize: '0.78rem' }}
              type="text"
              placeholder="Search case # or title..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Filter size={13} style={{ color: 'var(--text-muted)' }} />
            <select 
              className="form-select"
              style={{ width: 'auto', fontSize: '0.78rem' }}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="All">All Statuses</option>
              <option value="open">Open</option>
              <option value="under_investigation">Under Investigation</option>
              <option value="closed">Closed</option>
              <option value="archived">Archived</option>
            </select>
          </div>
        </div>

        {loading ? (
          <div className="empty-state" style={{ padding: '36px' }}>
            <div className="spinner" style={{ marginBottom: 10 }} />
            <div className="empty-state-title">Loading case files...</div>
          </div>
        ) : error ? (
          <div className="alert alert-error" style={{ margin: 16 }}>
            <AlertCircle size={14} />
            <span>{error}</span>
          </div>
        ) : filteredCases.length === 0 ? (
          <div className="empty-state">
            <FileText size={28} style={{ opacity: 0.3 }} />
            <div className="empty-state-title">No matching cases found</div>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 4 }}>
              Adjust search filters or register a new case file.
            </p>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Case #</th>
                <th>Title</th>
                <th>Crime Category</th>
                <th>Incident Date</th>
                <th>Priority</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredCases.map((c) => {
                const caseId = c.id || c._id;
                const caseNum = c.case_number || c.caseNumber || `CASE-${caseId}`;
                const crime = c.crime_type || c.crimeType || 'Unclassified';
                const dateStr = c.incident_date || c.incidentDate;

                return (
                  <tr key={caseId} style={{ cursor: 'pointer' }} onClick={() => navigate(`/cases/${caseId}`)}>
                    <td className="td-mono">{caseNum}</td>
                    <td className="td-primary">{c.title}</td>
                    <td>{crime}</td>
                    <td className="mono" style={{ fontSize: '0.78rem' }}>
                      {dateStr ? new Date(dateStr).toLocaleDateString() : 'N/A'}
                    </td>
                    <td>
                      <PriorityBadge priority={c.priority || 'Medium'} />
                    </td>
                    <td>
                      <StatusBadge status={c.status || 'open'} />
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="btn btn-secondary btn-sm" onClick={(e) => { e.stopPropagation(); navigate(`/cases/${caseId}`); }}>
                        Workspace <ChevronRight size={11} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* New Case Modal */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <span className="modal-title">Register Investigation Case File</span>
              <button className="btn btn-ghost btn-icon" onClick={() => setIsModalOpen(false)}>
                <X size={15} />
              </button>
            </div>
            
            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Case Title *</label>
                  <input className="form-control" required type="text" name="title" value={formData.title} onChange={handleInputChange} />
                </div>
                
                <div className="form-group">
                  <label className="form-label">FIR Summary &amp; Description *</label>
                  <textarea className="form-control" required rows={3} name="description" value={formData.description} onChange={handleInputChange} />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div className="form-group">
                    <label className="form-label">Crime Category *</label>
                    <select className="form-select" required name="crimeType" value={formData.crimeType} onChange={handleInputChange}>
                      <option value="">Select Category...</option>
                      <option value="Robbery">Robbery</option>
                      <option value="Assault">Assault</option>
                      <option value="Murder">Murder</option>
                      <option value="Fraud">Fraud</option>
                      <option value="Cybercrime">Cybercrime</option>
                      <option value="Drug Trafficking">Drug Trafficking</option>
                      <option value="Other">Other</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Priority Rating *</label>
                    <select className="form-select" required name="priority" value={formData.priority} onChange={handleInputChange}>
                      <option value="Low">Low</option>
                      <option value="Medium">Medium</option>
                      <option value="High">High</option>
                      <option value="Critical">Critical</option>
                    </select>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div className="form-group">
                    <label className="form-label">Incident Location *</label>
                    <input className="form-control" required type="text" name="location" value={formData.location} onChange={handleInputChange} />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Incident Date &amp; Time *</label>
                    <input className="form-control" required type="datetime-local" name="incidentDate" value={formData.incidentDate} onChange={handleInputChange} />
                  </div>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setIsModalOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
                  {isSubmitting ? <><span className="spinner" /> Saving...</> : 'Create Case File'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Cases;
