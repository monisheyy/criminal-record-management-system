import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { MapPin } from 'lucide-react';
import { intelligenceAPI } from '../services/api';
import { EmptyState, ErrorState, LoadingState } from '../components/ui';
import { CASE_STATUSES } from '../utils/constants';
import { formatDate } from '../utils/format';
import { useApiQuery } from '../utils/useApiQuery';

// One colour per crime category (backend/app/constants.py CRIME_CATEGORIES).
const CATEGORY_COLORS = {
  Violent: '#D23B3B',
  Narcotics: '#7E3FB8',
  Weapons: '#B4521C',
  'Organized Crime': '#A8751B',
  Financial: '#1F6FD1',
  Property: '#23935A',
  Technology: '#0F8C9E',
};
const OTHER_COLOR = '#6B7280';
const colorFor = (category) => CATEGORY_COLORS[category] || OTHER_COLOR;

const INDIA_CENTER = [22.6, 79.0];
const INDIA_ZOOM = 5;

/** Fly to a city when it is picked from the list beside the map. */
function FocusCity({ focus }) {
  const map = useMap();
  useEffect(() => {
    if (focus) map.flyTo([focus.lat, focus.lng], focus.zoom, { duration: 0.8 });
  }, [map, focus]);
  return null;
}

export default function IncidentMap() {
  const [status, setStatus] = useState('');
  const [focus, setFocus] = useState(null);
  const fetcher = useCallback(() => intelligenceAPI.incidentMap({ status }), [status]);
  const { data, error, loading, reload } = useApiQuery(fetcher, { fallbackError: 'Failed to load the incident map.' });

  const incidents = useMemo(() => data?.incidents ?? [], [data]);
  const categories = useMemo(() => {
    const seen = new Map();
    incidents.forEach((i) => seen.set(i.crime_category || 'Other', (seen.get(i.crime_category || 'Other') || 0) + 1));
    return [...seen.entries()].sort((a, b) => b[1] - a[1]);
  }, [incidents]);

  const focusCity = (city) => {
    const points = incidents.filter((i) => i.city === city);
    if (!points.length) return;
    const lat = points.reduce((s, p) => s + p.lat, 0) / points.length;
    const lng = points.reduce((s, p) => s + p.lng, 0) / points.length;
    setFocus({ lat, lng, zoom: 11 });
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Incident Map</h1>
          <p className="page-subtitle">
            {loading && !data ? 'Loading cases…'
              : `${incidents.length} case${incidents.length === 1 ? '' : 's'} on the map`
                + (data?.unmapped ? `, ${data.unmapped} with a location the map does not recognise` : '')}
          </p>
        </div>
        <div className="toolbar-filters">
          <label className="sr-only" htmlFor="map-status">Case status</label>
          <select id="map-status" className="form-select" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            {CASE_STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </div>
      </div>

      {error ? <ErrorState message={error} onRetry={reload} /> : (
        <div className="incident-map-layout">
          <div className="card incident-map-card">
            {loading && !data ? <LoadingState label="Loading map…" minHeight={520} /> : (
              <MapContainer center={INDIA_CENTER} zoom={INDIA_ZOOM} minZoom={4} maxZoom={16} scrollWheelZoom
                className="incident-map" aria-label="Map of India showing case locations">
                <TileLayer
                  attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />
                <FocusCity focus={focus} />
                {incidents.map((i) => (
                  <CircleMarker key={i.case_id} center={[i.lat, i.lng]}
                    radius={i.priority === 'critical' ? 10 : i.priority === 'high' ? 8 : 6}
                    pathOptions={{ color: '#fff', weight: 1.5, fillColor: colorFor(i.crime_category), fillOpacity: 0.9 }}>
                    <Popup>
                      <div className="map-popup">
                        <div className="td-mono">{i.case_number}</div>
                        <strong>{i.title}</strong>
                        <div>{i.crime_type || 'Unclassified'} · {i.location}</div>
                        <div className="td-sub">
                          {i.status.replace('_', ' ')} · priority {i.priority}
                          {i.incident_date ? ` · ${formatDate(i.incident_date)}` : ''}
                          {i.precision === 'city' ? ' · placed at city centre' : ''}
                        </div>
                        <Link to={`/cases/${i.case_id}`}>Open case file</Link>
                      </div>
                    </Popup>
                  </CircleMarker>
                ))}
              </MapContainer>
            )}
          </div>

          <aside className="incident-map-side">
            <div className="card">
              <h2 className="card-title">Cases by city</h2>
              {data && !data.by_city.length ? (
                <EmptyState icon={MapPin} title="No mapped cases">Cases appear here once their location names a known city.</EmptyState>
              ) : (
                <ul className="city-list">
                  {(data?.by_city ?? []).map((c) => (
                    <li key={c.city}>
                      <button type="button" className="city-row" onClick={() => focusCity(c.city)}>
                        <span>{c.city}</span>
                        <span className="city-bar" aria-hidden="true">
                          <span style={{ width: `${(c.count / data.by_city[0].count) * 100}%` }} />
                        </span>
                        <span className="td-mono">{c.count}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="card">
              <h2 className="card-title">Crime category</h2>
              <ul className="map-legend">
                {categories.map(([name, count]) => (
                  <li key={name}><span className="map-dot" style={{ background: colorFor(name) }} aria-hidden="true" />{name}<span className="td-mono">{count}</span></li>
                ))}
              </ul>
              <p className="td-sub">Larger circles are high and critical priority cases.</p>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
