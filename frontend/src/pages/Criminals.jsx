import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Search, Plus, AlertTriangle, Eye, X, Shield } from 'lucide-react';
import toast from 'react-hot-toast';
import { criminalsAPI } from '../services/api';
import { RiskBadge, StatusBadge } from '../components/RiskBadge';

const Criminals = () => {
  const navigate = useNavigate();
  const [criminals, setCriminals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [duplicateWarning, setDuplicateWarning] = useState(false);
  const [formData, setFormData] = useState({
    firstName: '',
    lastName: '',
    dob: '',
    gender: '',
    crimeType: '',
    crn: ''
  });

  useEffect(() => {
    fetchCriminals();
  }, []);

  const fetchCriminals = async () => {
    setLoading(true);
    try {
      const response = criminalsAPI.getAll ? await criminalsAPI.getAll() : await criminalsAPI.list();
      setCriminals(response.data || []);
    } catch (error) {
      toast.error('Failed to fetch criminal records');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const checkDup = async () => {
      if (formData.firstName.length >= 2 && formData.lastName.length >= 2) {
        try {
          const response = await criminalsAPI.checkDuplicate({ 
            firstName: formData.firstName, 
            lastName: formData.lastName 
          });
          if (response.data && response.data.matchFound) {
            setDuplicateWarning(true);
          } else {
            setDuplicateWarning(false);
          }
        } catch (error) {
          console.error("Duplicate check failed", error);
        }
      } else {
        setDuplicateWarning(false);
      }
    };
    
    const timer = setTimeout(checkDup, 400);
    return () => clearTimeout(timer);
  }, [formData.firstName, formData.lastName]);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await criminalsAPI.create({
        first_name: formData.firstName,
        last_name: formData.lastName,
        date_of_birth: formData.dob,
        gender: formData.gender,
        crime_type: formData.crimeType,
        crn: formData.crn || undefined
      });
      toast.success('Criminal record created successfully');
      setIsModalOpen(false);
      setFormData({ firstName: '', lastName: '', dob: '', gender: '', crimeType: '', crn: '' });
      fetchCriminals();
    } catch (error) {
      toast.error('Failed to create criminal record');
      console.error(error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const filteredCriminals = criminals.filter(c => {
    const name = `${c.first_name || c.firstName || ''} ${c.last_name || c.lastName || ''}`.toLowerCase();
    const crn = (c.crn || '').toLowerCase();
    const crime = (c.crime_type || c.crimeType || '').toLowerCase();
    const query = searchQuery.toLowerCase();
    return name.includes(query) || crn.includes(query) || crime.includes(query);
  });

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Offender Records Directory</h1>
          <p className="page-subtitle">Central intelligence database of offender dossiers and criminal profiles</p>
        </div>
        <button className="btn btn-primary" onClick={() => setIsModalOpen(true)}>
          <Plus size={14} /> Register New Dossier
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
              placeholder="Search CRN, name, or crime type..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <div className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Showing {filteredCriminals.length} of {criminals.length} records
          </div>
        </div>

        {loading ? (
          <div className="empty-state" style={{ padding: '36px' }}>
            <div className="spinner" style={{ marginBottom: 10 }} />
            <div className="empty-state-title">Loading criminal records directory...</div>
          </div>
        ) : filteredCriminals.length === 0 ? (
          <div className="empty-state">
            <Shield size={28} style={{ opacity: 0.3 }} />
            <div className="empty-state-title">No matching offender records</div>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 4 }}>
              Try adjusting your search criteria or register a new offender dossier.
            </p>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>CRN Code</th>
                <th>Offender Full Name</th>
                <th>Primary Offence</th>
                <th>Threat Rating</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredCriminals.map(criminal => {
                const name = `${criminal.first_name || criminal.firstName || ''} ${criminal.last_name || criminal.lastName || ''}`;
                const crn = criminal.crn || `CRN-${criminal.id}`;
                const crime = criminal.crime_type || criminal.crimeType || 'Unclassified';
                const score = criminal.risk_score || (criminal.threatLevel === 'critical' ? 85 : criminal.threatLevel === 'high' ? 65 : criminal.threatLevel === 'medium' ? 45 : 20);

                return (
                  <tr key={criminal.id}>
                    <td className="td-mono">{crn}</td>
                    <td className="td-primary">{name}</td>
                    <td>{crime}</td>
                    <td>
                      <RiskBadge score={score} level={criminal.threat_level || criminal.threatLevel} showBar />
                    </td>
                    <td>
                      <StatusBadge status={criminal.is_wanted ? 'critical' : criminal.is_incarcerated ? 'medium' : 'low'} />
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <Link to={`/criminals/${criminal.id}`} className="btn btn-secondary btn-sm">
                        <Eye size={12} /> View Dossier
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Create Record Modal */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <span className="modal-title">Register Offender Dossier</span>
              <button className="btn btn-ghost btn-icon" onClick={() => setIsModalOpen(false)}>
                <X size={15} />
              </button>
            </div>
            
            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                {duplicateWarning && (
                  <div className="alert alert-warning">
                    <AlertTriangle size={14} />
                    <span>A record matching this full name already exists in database.</span>
                  </div>
                )}
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div className="form-group">
                    <label className="form-label">First Name *</label>
                    <input className="form-control" type="text" name="firstName" required value={formData.firstName} onChange={handleInputChange} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Last Name *</label>
                    <input className="form-control" type="text" name="lastName" required value={formData.lastName} onChange={handleInputChange} />
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div className="form-group">
                    <label className="form-label">Date of Birth *</label>
                    <input className="form-control" type="date" name="dob" required value={formData.dob} onChange={handleInputChange} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Gender *</label>
                    <select className="form-select" name="gender" required value={formData.gender} onChange={handleInputChange}>
                      <option value="">Select Gender</option>
                      <option value="Male">Male</option>
                      <option value="Female">Female</option>
                      <option value="Other">Other</option>
                    </select>
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Primary Offence Category *</label>
                  <input className="form-control" type="text" name="crimeType" placeholder="e.g. Cybercrime, Robbery" required value={formData.crimeType} onChange={handleInputChange} />
                </div>

                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">CRN Code (Optional)</label>
                  <input className="form-control" type="text" name="crn" placeholder="Auto-generated if left blank" value={formData.crn} onChange={handleInputChange} />
                </div>
              </div>
              
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setIsModalOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
                  {isSubmitting ? <><span className="spinner" /> Saving...</> : 'Save Dossier'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Criminals;
