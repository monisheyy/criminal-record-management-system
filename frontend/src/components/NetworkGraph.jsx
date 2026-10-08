import { useCallback, useMemo, useRef, useState } from 'react';
import { Network, ZoomIn, ZoomOut, RotateCcw, ExternalLink } from 'lucide-react';
import { intelligenceAPI } from '../services/api';
import { useApiQuery } from '../utils/useApiQuery';

const EMPTY_GRAPH = { nodes: [], edges: [], metadata: null };

const TYPE_META = {
  criminal: { label: 'Criminal', stroke: '#FF3B30' },
  case: { label: 'Case', stroke: '#0071E3' },
  gang: { label: 'Gang', stroke: '#AF52DE' },
  officer: { label: 'Officer', stroke: '#34C759' },
};

function layoutNodes(nodes, width, height) {
  const groups = nodes.reduce((acc, n) => {
    (acc[n.type] ||= []).push(n);
    return acc;
  }, {});
  const order = ['case', 'criminal', 'gang', 'officer'];
  const positions = {};
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(width, height) * 0.34;
  const ordered = order.flatMap(t => groups[t] || []);
  ordered.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / Math.max(ordered.length, 1) - Math.PI / 2;
    positions[node.id] = {
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
    };
  });
  return positions;
}

export default function NetworkGraph({ criminalId, caseId, gangId, depth = 2, height = 520 }) {
  const fetchGraph = useCallback(
    () => intelligenceAPI.network({ criminal_id: criminalId, case_id: caseId, gang_id: gangId, depth }),
    [criminalId, caseId, gangId, depth],
  );
  const { data, loading, error } = useApiQuery(fetchGraph, { fallbackError: 'Unable to load network intelligence.' });
  const graph = data || EMPTY_GRAPH;
  const [selected, setSelected] = useState(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const drag = useRef(null);

  const width = 900;
  const positions = useMemo(() => layoutNodes(graph.nodes, width, height), [graph.nodes, height]);

  const handleWheel = (e) => {
    e.preventDefault();
    setZoom(z => Math.min(2.2, Math.max(0.55, z + (e.deltaY < 0 ? 0.12 : -0.12))));
  };

  const handlePointerDown = (e) => {
    drag.current = { x: e.clientX, y: e.clientY, pan };
    setDragging(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const handlePointerMove = (e) => {
    if (!drag.current) return;
    setPan({
      x: drag.current.pan.x + e.clientX - drag.current.x,
      y: drag.current.pan.y + e.clientY - drag.current.y,
    });
  };
  const handlePointerUp = () => { drag.current = null; setDragging(false); };

  const selectedNode = graph.nodes.find(n => n.id === selected);

  return (
    <div className="card" style={{ marginTop: 20 }}>
      <div className="card-title" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Network size={16} /> Network Intelligence</span>
        <div style={{ display: 'flex', gap: 5 }}>
          <button className="btn btn-secondary btn-icon" title="Zoom in" onClick={() => setZoom(z => Math.min(2.2, z + 0.15))}><ZoomIn size={14} /></button>
          <button className="btn btn-secondary btn-icon" title="Zoom out" onClick={() => setZoom(z => Math.max(0.55, z - 0.15))}><ZoomOut size={14} /></button>
          <button className="btn btn-secondary btn-icon" title="Reset view" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}><RotateCcw size={14} /></button>
        </div>
      </div>
      <div style={{ color: 'var(--text-muted)', fontSize: '0.78rem', margin: '5px 0 12px' }}>
        Relationship graph built from stored criminal, case, gang and officer records. Drag to pan; scroll to zoom.
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 10 }}>
        {Object.entries(TYPE_META).map(([type, meta]) => (
          <span key={type} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', background: meta.stroke }} />{meta.label}
          </span>
        ))}
      </div>

      {loading ? (
        <div className="empty-state" style={{ minHeight: 280 }}><div className="spinner" /><div className="empty-state-title">Building relationship graph...</div></div>
      ) : error ? (
        <div className="alert alert-danger">{error}</div>
      ) : graph.nodes.length === 0 ? (
        <div className="empty-state" style={{ minHeight: 280 }}><Network size={30} style={{ opacity: 0.3 }} /><div className="empty-state-title">No accessible relationships found</div></div>
      ) : (
        <div style={{ borderRadius: 14, overflow: 'hidden', background: '#F5F5F7' }}>
          <svg
            viewBox={`0 0 ${width} ${height}`}
            width="100%"
            height={height}
            onWheel={handleWheel}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerLeave={handlePointerUp}
            style={{ cursor: dragging ? 'grabbing' : 'grab', touchAction: 'none' }}
          >
            <g transform={`translate(${pan.x + width / 2 * (1 - zoom)}, ${pan.y + height / 2 * (1 - zoom)}) scale(${zoom})`}>
              {graph.edges.map(edge => {
                const a = positions[edge.source]; const b = positions[edge.target];
                if (!a || !b) return null;
                return <line key={edge.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="rgba(0,0,0,.12)" strokeWidth="1" />;
              })}
              {graph.nodes.map(node => {
                const p = positions[node.id]; const meta = TYPE_META[node.type] || TYPE_META.case;
                const isSelected = node.id === selected;
                return (
                  <g key={node.id} transform={`translate(${p.x},${p.y})`} onClick={(e) => { e.stopPropagation(); setSelected(node.id); }} style={{ cursor: 'pointer' }}>
                    <circle r={isSelected ? 18 : 14} fill="#FFFFFF" stroke={meta.stroke} strokeWidth={isSelected ? 3 : 2} />
                    <text textAnchor="middle" dy="4" fontSize="9" fill={meta.stroke} fontWeight="700">{node.type === 'criminal' ? 'C' : node.type === 'case' ? 'K' : node.type === 'gang' ? 'G' : 'O'}</text>
                    <text textAnchor="middle" dy="31" fontSize="10" fill="#424245" style={{ paintOrder: 'stroke', stroke: '#F5F5F7', strokeWidth: 4 }}>{node.label.length > 18 ? `${node.label.slice(0, 17)}…` : node.label}</text>
                  </g>
                );
              })}
            </g>
          </svg>
        </div>
      )}

      {selectedNode && (
        <div className="alert alert-info" style={{ marginTop: 12 }}>
          <div style={{ flex: 1 }}>
            <strong>{selectedNode.label}</strong> <span style={{ opacity: .7 }}>· {TYPE_META[selectedNode.type]?.label}</span>
            {selectedNode.crime_type && <div style={{ fontSize: '.75rem', marginTop: 3 }}>Crime type: {selectedNode.crime_type}</div>}
            {selectedNode.title && <div style={{ fontSize: '.75rem', marginTop: 3 }}>{selectedNode.title}</div>}
          </div>
          {selectedNode.route && (
            <button className="btn btn-secondary btn-sm" onClick={() => { window.location.href = selectedNode.route; }}>
              Open record <ExternalLink size={12} />
            </button>
          )}
        </div>
      )}

      {graph.metadata && (
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginTop: 10, fontSize: '.72rem', color: 'var(--text-muted)' }}>
          <span>{graph.metadata.node_count} nodes · {graph.metadata.edge_count} relationships</span>
          <span>Depth {graph.metadata.depth} · {graph.metadata.source}</span>
        </div>
      )}
    </div>
  );
}
