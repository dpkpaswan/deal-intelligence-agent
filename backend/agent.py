"""
Sales Deal Intelligence Agent — Orchestrator.

Ties together Hindsight memory + CascadeFlow routing into a single agent
that can chat with sales reps about their prospects with full context.

Flow per user message:
  1. Recall past context from Hindsight for this prospect
  2. Build system prompt with sales context + recalled memories
  3. Route the query through CascadeFlow (cheap model or powerful model)
  4. Retain the exchange (user msg + agent reply) in Hindsight
  5. Return response + routing metadata + memory context indicator

Session summary:
  - Triggered explicitly via reflect()
  - Uses Hindsight's reflect() to synthesize key points + next action
"""

import logging
from datetime import datetime, timezone
from typing import Optional

try:
    from .memory import HindsightMemory
    from .routing import CascadeRouter
except ImportError:
    from memory import HindsightMemory
    from routing import CascadeRouter

logger = logging.getLogger("agent")

# ── System Prompt ────────────────────────────────────────────────────────
SYSTEM_PROMPT_BASE = """You are a Sales Deal Intelligence Agent — an AI assistant that helps sales representatives manage their prospect relationships and close deals.

Your capabilities:
- Track conversation history across multiple sessions with each prospect
- Recall past discussions, objections, preferences, and deal stages
- Provide strategic advice on next steps, objection handling, and deal progression
- Analyze prospect sentiment and buying signals

Guidelines:
- Be concise and actionable — sales reps are busy
- Reference past context when available (e.g., "Last time we discussed...")
- Flag objections and suggest rebuttals
- Recommend specific next actions at the end of each response
- If this is a new prospect with no history, acknowledge it and ask discovery questions
"""

CONTEXT_INJECTION_TEMPLATE = """
--- RECALLED CONTEXT FROM PAST SESSIONS ---
The following memories are from previous conversations with this prospect.
Use them to provide personalized, context-aware responses.

{memories}

--- END OF RECALLED CONTEXT ---
"""

SUMMARY_SYSTEM_PROMPT = """You are a Sales Deal Intelligence Agent generating a session summary.
Analyze the conversation history and produce a structured summary with:
1. **Key Discussion Points** — What was talked about
2. **Prospect Sentiment** — Positive, neutral, negative, and why
3. **Objections Raised** — Any concerns or pushback
4. **Deal Stage Assessment** — Where this prospect is in the pipeline
5. **Recommended Next Action** — Specific, actionable next step for the rep

Be concise. Use bullet points. Focus on what's actionable.
"""


class SalesDealAgent:
    """
    The main orchestrator that combines memory + routing.

    Usage:
        agent = SalesDealAgent()
        response = await agent.chat("prospect-123", "What's their budget?")
        summary = await agent.generate_summary("prospect-123")
    """

    def __init__(self):
        self.memory = HindsightMemory()
        self.router = CascadeRouter()

        # Track active sessions: prospect_id -> session metadata
        self._active_sessions: dict[str, dict] = {}

    async def chat(
        self,
        prospect_id: str,
        message: str,
        session_id: Optional[str] = None,
    ) -> dict:
        """
        Handle a single chat turn with a prospect.

        This is the main entry point. It:
          1. Recalls past context from Hindsight
          2. Builds the message list with context-enriched system prompt
          3. Routes through CascadeFlow
          4. Retains both the user message and agent reply
          5. Returns everything the frontend needs

        Args:
            prospect_id: Which prospect this conversation is about.
            message: The sales rep's message/question.
            session_id: Optional session identifier for grouping.

        Returns:
            Dict with response, routing info, memory context, and metadata.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        # Track session
        if prospect_id not in self._active_sessions:
            self._active_sessions[prospect_id] = {
                "session_id": session_id or f"session-{timestamp}",
                "started_at": timestamp,
                "turn_count": 0,
            }
        session = self._active_sessions[prospect_id]
        session["turn_count"] += 1

        # ── Step 1: Recall past context ──────────────────────────────
        recall_result = await self.memory.recall(
            prospect_id=prospect_id,
            query=message,
        )
        memories = recall_result.get("memories", [])
        has_prior_context = recall_result.get("has_context", False)

        logger.info(
            "Recalled %d memories for prospect %s (has_context=%s, source=%s)",
            len(memories),
            prospect_id,
            has_prior_context,
            recall_result.get("source", "unknown"),
        )

        # ── Step 2: Build system prompt ──────────────────────────────
        system_prompt = SYSTEM_PROMPT_BASE
        if memories:
            memory_text = "\n".join(f"  • {m}" for m in memories)
            system_prompt += CONTEXT_INJECTION_TEMPLATE.format(memories=memory_text)

        # Build message list with conversation history from current session
        history_result = await self.memory.get_history(prospect_id, limit=20)
        past_turns = history_result.get("turns", [])

        messages = [{"role": "system", "content": system_prompt}]

        # Add recent conversation turns (current session context)
        for turn in past_turns[-10:]:  # Last 10 turns for immediate context
            messages.append({
                "role": turn["role"],
                "content": turn["content"],
            })

        # Add the current user message
        messages.append({"role": "user", "content": message})

        # ── Step 3: Route through CascadeFlow ────────────────────────
        # Provide a complexity hint based on message characteristics
        complexity_hint = self._estimate_complexity(message)

        route_result = await self.router.route_query(
            messages=messages,
            complexity_hint=complexity_hint,
        )

        agent_response = route_result["content"]
        routing_info = route_result["routing_info"]

        logger.info(
            "Routed query for prospect %s: model=%s, cost=$%.6f",
            prospect_id,
            route_result["model_used"],
            route_result["cost"],
        )

        # ── Step 4: Retain the exchange ──────────────────────────────
        # Store user message
        await self.memory.retain(
            prospect_id=prospect_id,
            content=message,
            role="user",
            metadata={
                "session_id": session["session_id"],
                "turn": session["turn_count"],
            },
        )

        # Store agent response
        await self.memory.retain(
            prospect_id=prospect_id,
            content=agent_response,
            role="assistant",
            metadata={
                "session_id": session["session_id"],
                "turn": session["turn_count"],
                "model_used": route_result["model_used"],
                "cost": route_result["cost"],
            },
        )

        # ── Step 5: Build response ───────────────────────────────────
        return {
            "response": agent_response,
            "prospect_id": prospect_id,
            "session_id": session["session_id"],
            "turn_number": session["turn_count"],
            "routing": {
                "model_used": routing_info.get("model_used", "unknown"),
                "cascaded": routing_info.get("cascaded", False),
                "draft_accepted": routing_info.get("draft_accepted", False),
                "cost": routing_info.get("total_cost", 0),
                "complexity": routing_info.get("complexity", "unknown"),
                "reason": routing_info.get("reason", ""),
                "savings_percentage": routing_info.get("savings_percentage"),
            },
            "memory": {
                "has_prior_context": has_prior_context,
                "memories_recalled": len(memories),
                "memory_source": recall_result.get("source", "none"),
            },
            "timestamp": timestamp,
        }

    async def generate_summary(
        self,
        prospect_id: str,
        custom_query: Optional[str] = None,
    ) -> dict:
        """
        Generate a session summary for a prospect.

        Uses Hindsight's reflect() to synthesize insights, then optionally
        routes through CascadeFlow for a polished summary.

        Args:
            prospect_id: Which prospect to summarize.
            custom_query: Optional custom focus for the summary.

        Returns:
            Dict with the summary text, key points, and next action.
        """
        # First try Hindsight reflect for the raw summary
        reflect_result = await self.memory.reflect(
            prospect_id=prospect_id,
            query=custom_query,
        )

        raw_summary = reflect_result.get("summary", "")

        # If we have conversation history, also generate a structured summary
        # via the LLM for better formatting
        history_result = await self.memory.get_history(prospect_id)
        turns = history_result.get("turns", [])

        if turns:
            # Build a conversation transcript for the LLM
            transcript_lines = []
            for turn in turns:
                role_label = "Sales Rep" if turn["role"] == "user" else "AI Agent"
                transcript_lines.append(f"{role_label}: {turn['content']}")
            transcript = "\n".join(transcript_lines)

            summary_messages = [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Here is the conversation transcript with prospect {prospect_id}:\n\n"
                        f"{transcript}\n\n"
                        f"Hindsight memory reflection:\n{raw_summary}\n\n"
                        "Generate a structured session summary."
                    ),
                },
            ]

            # Route through cascade — summaries are complex, hint accordingly
            route_result = await self.router.route_query(
                messages=summary_messages,
                complexity_hint="complex",
                max_tokens=1500,
            )

            structured_summary = route_result["content"]

            return {
                "prospect_id": prospect_id,
                "summary": structured_summary,
                "hindsight_reflection": raw_summary,
                "source": reflect_result.get("source", "unknown"),
                "total_turns": len(turns),
                "model_used": route_result["model_used"],
                "cost": route_result["cost"],
                "generated_at": reflect_result.get("generated_at", ""),
            }

        # No conversation history — return what Hindsight gave us
        return {
            "prospect_id": prospect_id,
            "summary": raw_summary,
            "hindsight_reflection": raw_summary,
            "source": reflect_result.get("source", "unknown"),
            "total_turns": 0,
            "model_used": "none",
            "cost": 0,
            "generated_at": reflect_result.get("generated_at", ""),
        }

    async def end_session(self, prospect_id: str) -> dict:
        """
        End the active session for a prospect.

        Generates a summary and clears the session tracker.
        The conversation history remains in both local storage and Hindsight.
        """
        summary = await self.generate_summary(prospect_id)
        session = self._active_sessions.pop(prospect_id, None)

        return {
            **summary,
            "session_ended": True,
            "session_info": session,
        }

    def _estimate_complexity(self, message: str) -> Optional[str]:
        """
        Heuristic complexity estimation to hint CascadeFlow routing.

        This is a lightweight pre-filter — CascadeFlow does its own
        quality-based routing, but hints can speed up the decision.
        """
        msg_lower = message.lower()
        word_count = len(message.split())

        # Simple: greetings, short factual questions, yes/no
        if word_count < 8 or any(w in msg_lower for w in [
            "hello", "hi", "thanks", "bye", "yes", "no", "ok",
        ]):
            return "simple"

        # Complex: analysis, strategy, multi-part questions
        if word_count > 30 or any(w in msg_lower for w in [
            "analyze", "strategy", "compare", "evaluate", "recommend",
            "detailed", "comprehensive", "explain why", "pros and cons",
            "what should", "how should", "objection", "negotiate",
        ]):
            return "complex"

        # Let CascadeFlow decide
        return None

    def get_audit_log(self, limit: int = 50) -> list[dict]:
        """Proxy to router's audit log."""
        return self.router.get_audit_log(limit)

    def get_stats(self) -> dict:
        """Combined stats from routing + memory."""
        routing_stats = self.router.get_routing_stats()
        return {
            "routing": routing_stats,
            "prospects_with_history": self.memory.get_prospect_ids(),
            "active_sessions": {
                pid: {
                    "session_id": s["session_id"],
                    "turn_count": s["turn_count"],
                    "started_at": s["started_at"],
                }
                for pid, s in self._active_sessions.items()
            },
        }
