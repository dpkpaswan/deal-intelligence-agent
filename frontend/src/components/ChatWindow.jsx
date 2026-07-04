import { useState, useRef, useEffect } from 'react';

export default function ChatWindow({ prospect, messages, isLoading, onSendMessage, onGenerateSummary }) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  // Focus input when prospect changes
  useEffect(() => {
    inputRef.current?.focus();
  }, [prospect?.id]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    onSendMessage(input);
    setInput('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const formatTime = (ts) => {
    if (!ts) return '';
    try {
      return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  const getModelBadge = (routing) => {
    if (!routing) return null;
    const model = routing.model_used || '';

    if (model === 'mock' || model === 'error') {
      return { label: model, className: 'message__routing-badge--mock' };
    }

    // CascadeFlow returns "8b+70b" when both models ran (cascade)
    const cascaded = routing.cascaded;
    const draftAccepted = routing.draft_accepted;

    if (cascaded && !draftAccepted) {
      // Draft failed quality check → verifier produced the response
      return { label: '🧠 70B (cascaded)', className: 'message__routing-badge--powerful' };
    }
    if (cascaded && draftAccepted) {
      // Draft passed quality check → fast model saved cost
      return { label: '⚡ 8B (cascade saved)', className: 'message__routing-badge--fast' };
    }
    if (model.includes('70b') || model.includes('versatile')) {
      return { label: '🧠 70B Pro', className: 'message__routing-badge--powerful' };
    }
    if (model.includes('8b') || model.includes('instant')) {
      return { label: '⚡ 8B Fast', className: 'message__routing-badge--fast' };
    }
    return { label: model.split('/').pop(), className: 'message__routing-badge--fast' };
  };

  const getInitials = (name) =>
    name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();

  return (
    <div className="chat-window">
      {/* Header */}
      <div className="chat-window__header">
        <div className="chat-window__prospect-info">
          <div className="chat-window__avatar">
            {getInitials(prospect.name)}
          </div>
          <div>
            <div className="chat-window__name">{prospect.name}</div>
            <div className="chat-window__status">
              <span className="chat-window__status-dot" />
              {prospect.deal_stage} · {prospect.company}
            </div>
          </div>
        </div>
        <div className="chat-window__actions">
          <button
            className="chat-window__action-btn chat-window__action-btn--primary"
            onClick={onGenerateSummary}
          >
            📋 End Session
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="chat-window__messages">
        {messages.length === 0 ? (
          <div className="chat-window__empty">
            <div className="chat-window__empty-icon">💬</div>
            <div className="chat-window__empty-text">
              Start a conversation about <strong>{prospect.name}</strong>. Ask about their needs, objections, or deal strategy.
              {messages.length === 0 && (
                <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--accent-light)' }}>
                  ✨ Session 1 is generic. By session 3, the agent will recall past context via Hindsight.
                </div>
              )}
            </div>
          </div>
        ) : (
          messages.map(msg => (
            <div key={msg.id} className={`message message--${msg.role}`}>
              <div className="message__bubble">
                {msg.content}
              </div>
              <div className="message__meta">
                <span className="message__time">{formatTime(msg.timestamp)}</span>

                {msg.role === 'assistant' && msg.routing && (
                  <>
                    {(() => {
                      const badge = getModelBadge(msg.routing);
                      return badge ? (
                        <span className={`message__routing-badge ${badge.className}`}>
                          {badge.label}
                        </span>
                      ) : null;
                    })()}

                    {msg.routing.cost > 0 && (
                      <span className="message__cost">
                        ${msg.routing.cost.toFixed(6)}
                      </span>
                    )}
                  </>
                )}

                {msg.role === 'assistant' && msg.memory?.has_prior_context && (
                  <span className="message__memory-indicator">
                    🧠 {msg.memory.memories_recalled} memories recalled
                  </span>
                )}
              </div>
            </div>
          ))
        )}

        {/* Typing indicator */}
        {isLoading && (
          <div className="typing-indicator">
            <div className="typing-indicator__dot" />
            <div className="typing-indicator__dot" />
            <div className="typing-indicator__dot" />
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="chat-window__input-area">
        <form className="chat-window__input-wrapper" onSubmit={handleSubmit}>
          <textarea
            ref={inputRef}
            className="chat-window__input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Ask about ${prospect.name}...`}
            rows={1}
            disabled={isLoading}
          />
          <button
            type="submit"
            className="chat-window__send-btn"
            disabled={!input.trim() || isLoading}
            title="Send message"
          >
            {isLoading ? <span className="spinner" /> : '➤'}
          </button>
        </form>
      </div>
    </div>
  );
}
