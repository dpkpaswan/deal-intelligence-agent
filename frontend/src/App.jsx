import { useState, useCallback } from 'react';
import ProspectSidebar from './components/ProspectSidebar';
import ChatWindow from './components/ChatWindow';
import SessionSummary from './components/SessionSummary';

const API_BASE = 'http://localhost:8000';

export default function App() {
  const [activeProspect, setActiveProspect] = useState(null);
  const [messages, setMessages] = useState({});       // prospect_id -> message[]
  const [summary, setSummary] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSummarizing, setIsSummarizing] = useState(false);

  // Get messages for active prospect
  const currentMessages = activeProspect ? (messages[activeProspect.id] || []) : [];

  // ── Send message ──────────────────────────────────────────────────
  const handleSendMessage = useCallback(async (text) => {
    if (!activeProspect || !text.trim()) return;

    const prospectId = activeProspect.id;
    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: text.trim(),
      timestamp: new Date().toISOString(),
    };

    // Optimistic update: add user message immediately
    setMessages(prev => ({
      ...prev,
      [prospectId]: [...(prev[prospectId] || []), userMessage],
    }));
    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prospect_id: prospectId,
          message: text.trim(),
        }),
      });

      if (!res.ok) throw new Error(`Chat failed: ${res.status}`);
      const data = await res.json();

      const assistantMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: data.response,
        timestamp: data.timestamp,
        routing: data.routing,
        memory: data.memory,
      };

      setMessages(prev => ({
        ...prev,
        [prospectId]: [...(prev[prospectId] || []), assistantMessage],
      }));
    } catch (err) {
      console.error('Chat error:', err);
      const errorMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: `⚠️ Connection error: ${err.message}. Make sure the backend is running on port 8000.`,
        timestamp: new Date().toISOString(),
        routing: { model_used: 'error', complexity: 'error' },
      };
      setMessages(prev => ({
        ...prev,
        [prospectId]: [...(prev[prospectId] || []), errorMessage],
      }));
    } finally {
      setIsLoading(false);
    }
  }, [activeProspect]);

  // ── Generate summary ──────────────────────────────────────────────
  const handleGenerateSummary = useCallback(async () => {
    if (!activeProspect) return;
    setIsSummarizing(true);
    setSummary(null);

    try {
      const res = await fetch(`${API_BASE}/summary/${activeProspect.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });

      if (!res.ok) throw new Error(`Summary failed: ${res.status}`);
      const data = await res.json();
      setSummary(data);
    } catch (err) {
      console.error('Summary error:', err);
      setSummary({
        summary: `⚠️ Failed to generate summary: ${err.message}`,
        source: 'error',
        generated_at: new Date().toISOString(),
      });
    } finally {
      setIsSummarizing(false);
    }
  }, [activeProspect]);

  // ── Select prospect ───────────────────────────────────────────────
  const handleSelectProspect = useCallback((prospect) => {
    setActiveProspect(prospect);
    setSummary(null);
  }, []);

  return (
    <div className="app-layout">
      <ProspectSidebar
        activeProspect={activeProspect}
        onSelectProspect={handleSelectProspect}
        apiBase={API_BASE}
      />

      <div className="main-content">
        {activeProspect ? (
          <>
            <ChatWindow
              prospect={activeProspect}
              messages={currentMessages}
              isLoading={isLoading}
              onSendMessage={handleSendMessage}
              onGenerateSummary={handleGenerateSummary}
            />
            <SessionSummary
              prospect={activeProspect}
              summary={summary}
              isLoading={isSummarizing}
              onGenerate={handleGenerateSummary}
            />
          </>
        ) : (
          <div className="no-prospect">
            <div className="no-prospect__icon">💼</div>
            <div className="no-prospect__title">Select a Prospect</div>
            <div className="no-prospect__subtitle">
              Choose a prospect from the sidebar to start a conversation. Your chat history persists across sessions via Hindsight.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
