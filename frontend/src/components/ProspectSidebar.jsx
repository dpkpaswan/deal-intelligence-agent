import { useState, useEffect } from 'react';

export default function ProspectSidebar({ activeProspect, onSelectProspect, apiBase }) {
  const [prospects, setProspects] = useState([]);
  const [search, setSearch] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);
  const [newProspect, setNewProspect] = useState({
    id: '', name: '', company: '', deal_stage: 'Discovery', deal_value: 0, contact_email: '',
  });

  // ── Fetch prospects on mount ──────────────────────────────────────
  useEffect(() => {
    fetchProspects();
  }, []);

  const fetchProspects = async () => {
    try {
      const res = await fetch(`${apiBase}/prospects`);
      if (res.ok) {
        const data = await res.json();
        setProspects(data.prospects || []);
      }
    } catch (err) {
      console.error('Failed to fetch prospects:', err);
      // Seed data fallback
      setProspects([
        { id: 'acme-corp', name: 'Acme Corporation', company: 'Acme Corp', deal_stage: 'Discovery', deal_value: 50000 },
        { id: 'globex-inc', name: 'Globex Industries', company: 'Globex Inc', deal_stage: 'Proposal', deal_value: 120000 },
        { id: 'initech-llc', name: 'Initech Solutions', company: 'Initech LLC', deal_stage: 'Negotiation', deal_value: 85000 },
      ]);
    }
  };

  // ── Add new prospect ──────────────────────────────────────────────
  const handleAddProspect = async (e) => {
    e.preventDefault();
    if (!newProspect.id || !newProspect.name) return;

    try {
      const res = await fetch(`${apiBase}/prospects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newProspect),
      });
      if (res.ok) {
        const data = await res.json();
        setProspects(prev => [...prev, data.prospect]);
      }
    } catch (err) {
      // Add locally on error
      setProspects(prev => [...prev, { ...newProspect }]);
    }

    setNewProspect({ id: '', name: '', company: '', deal_stage: 'Discovery', deal_value: 0, contact_email: '' });
    setShowAddForm(false);
  };

  // ── Filter prospects ──────────────────────────────────────────────
  const filtered = prospects.filter(p =>
    p.name.toLowerCase().includes(search.toLowerCase()) ||
    p.company?.toLowerCase().includes(search.toLowerCase())
  );

  const formatValue = (val) => {
    if (!val) return '';
    if (val >= 1000) return `$${(val / 1000).toFixed(0)}K`;
    return `$${val}`;
  };

  const getInitials = (name) =>
    name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();

  return (
    <aside className="sidebar">
      {/* Header */}
      <div className="sidebar__header">
        <div className="app-header__logo">
          <div className="app-header__icon">🎯</div>
          <div>
            <div className="app-header__title">Deal Intelligence</div>
            <span className="app-header__badge">AI Agent</span>
          </div>
        </div>
        <div style={{ marginTop: '0.75rem' }}>
          <div className="sidebar__title">Prospects</div>
          <input
            className="sidebar__search"
            type="text"
            placeholder="Search prospects..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Prospect List */}
      <div className="sidebar__list">
        {filtered.map(prospect => (
          <div
            key={prospect.id}
            className={`prospect-card ${activeProspect?.id === prospect.id ? 'prospect-card--active' : ''}`}
            onClick={() => onSelectProspect(prospect)}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <div className="chat-window__avatar" style={{ width: 30, height: 30, fontSize: '0.7rem' }}>
                {getInitials(prospect.name)}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="prospect-card__name">{prospect.name}</div>
                <div className="prospect-card__company">{prospect.company}</div>
              </div>
            </div>
            <div className="prospect-card__meta" style={{ marginTop: '0.35rem', paddingLeft: '2.4rem' }}>
              <span className="prospect-card__stage">{prospect.deal_stage}</span>
              {prospect.deal_value > 0 && (
                <span className="prospect-card__value">{formatValue(prospect.deal_value)}</span>
              )}
            </div>
          </div>
        ))}

        {filtered.length === 0 && (
          <div style={{ padding: '2rem 1rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
            {search ? 'No prospects match your search' : 'No prospects yet'}
          </div>
        )}
      </div>

      {/* Add Form */}
      {showAddForm && (
        <div style={{ padding: '0.75rem', borderTop: '1px solid var(--border)' }}>
          <form onSubmit={handleAddProspect} style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            <input className="sidebar__search" placeholder="ID (e.g. acme-corp)" value={newProspect.id}
              onChange={e => setNewProspect(p => ({ ...p, id: e.target.value }))} required />
            <input className="sidebar__search" placeholder="Name" value={newProspect.name}
              onChange={e => setNewProspect(p => ({ ...p, name: e.target.value }))} required />
            <input className="sidebar__search" placeholder="Company" value={newProspect.company}
              onChange={e => setNewProspect(p => ({ ...p, company: e.target.value }))} />
            <div style={{ display: 'flex', gap: '0.4rem' }}>
              <button type="submit" className="sidebar__add-btn" style={{ fontSize: '0.72rem' }}>Save</button>
              <button type="button" className="sidebar__add-btn" onClick={() => setShowAddForm(false)}
                style={{ fontSize: '0.72rem', background: 'var(--bg-elevated)' }}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {/* Footer */}
      <div className="sidebar__footer">
        <button className="sidebar__add-btn" onClick={() => setShowAddForm(!showAddForm)}>
          <span>{showAddForm ? '✕' : '+'}</span>
          <span>{showAddForm ? 'Cancel' : 'New Prospect'}</span>
        </button>
      </div>
    </aside>
  );
}
