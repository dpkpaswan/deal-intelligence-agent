import { useState } from 'react';

export default function SessionSummary({ prospect, summary, isLoading, onGenerate }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className={`session-summary ${collapsed ? 'session-summary--collapsed' : ''}`}>
      {/* Header — click to collapse/expand */}
      <div
        className="session-summary__header"
        onClick={() => setCollapsed(!collapsed)}
      >
        <div className="session-summary__header-left">
          <span style={{ fontSize: '0.85rem' }}>📋</span>
          <span className="session-summary__title">Session Summary</span>
          {summary && (
            <span style={{
              fontSize: '0.6rem',
              padding: '0.08rem 0.35rem',
              borderRadius: 'var(--radius-full)',
              background: 'rgba(16, 185, 129, 0.12)',
              color: 'var(--success-light)',
              border: '1px solid rgba(16, 185, 129, 0.2)',
            }}>
              Generated
            </span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {!collapsed && (
            <button
              className="session-summary__generate-btn"
              onClick={(e) => { e.stopPropagation(); onGenerate(); }}
              disabled={isLoading}
            >
              {isLoading ? (
                <>
                  <span className="spinner" style={{ width: 10, height: 10 }} /> Analyzing...
                </>
              ) : (
                summary ? '🔄 Regenerate' : '✨ Generate Summary'
              )}
            </button>
          )}
          <span className="session-summary__toggle">▼</span>
        </div>
      </div>

      {/* Content */}
      {!collapsed && (
        <div className="session-summary__content">
          {isLoading ? (
            <div className="session-summary__empty">
              <div style={{ marginBottom: '0.5rem' }}>
                <span className="spinner" style={{ width: 18, height: 18 }} />
              </div>
              Analyzing conversation with {prospect.name}...
              <div style={{ fontSize: '0.72rem', marginTop: '0.3rem', color: 'var(--text-muted)' }}>
                Using Hindsight reflect() + CascadeFlow routing
              </div>
            </div>
          ) : summary ? (
            <>
              <div className="session-summary__text">{summary.summary}</div>

              <div className="session-summary__meta">
                {summary.source && (
                  <span className="session-summary__meta-item">
                    📡 {summary.source}
                  </span>
                )}
                {summary.model_used && summary.model_used !== 'none' && (
                  <span className="session-summary__meta-item">
                    🤖 {summary.model_used.includes('70b') ? '70B Pro' : summary.model_used.includes('8b') ? '8B Fast' : summary.model_used}
                  </span>
                )}
                {summary.total_turns > 0 && (
                  <span className="session-summary__meta-item">
                    💬 {summary.total_turns} turns
                  </span>
                )}
                {summary.cost > 0 && (
                  <span className="session-summary__meta-item">
                    💰 ${summary.cost.toFixed(6)}
                  </span>
                )}
                {summary.generated_at && (
                  <span className="session-summary__meta-item">
                    🕐 {new Date(summary.generated_at).toLocaleTimeString()}
                  </span>
                )}
              </div>
            </>
          ) : (
            <div className="session-summary__empty">
              Click <strong>"Generate Summary"</strong> or <strong>"End Session"</strong> to get
              key discussion points and recommended next actions for {prospect.name}.
              <div style={{ fontSize: '0.72rem', marginTop: '0.5rem', color: 'var(--accent-light)' }}>
                Powered by Hindsight reflect() — synthesizes insights from all past sessions
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
