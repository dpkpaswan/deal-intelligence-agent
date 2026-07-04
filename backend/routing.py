"""
CascadeFlow Routing for Sales Deal Intelligence Agent.

Uses CascadeAgent to implement speculative model routing:
  - Simple queries (greetings, lookups) → fast/cheap model (llama-3.1-8b-instant)
  - Complex queries (strategy, analysis) → powerful model (llama-3.3-70b-versatile)

CascadeFlow handles the routing decision automatically via quality validation.
Every routing decision is logged to an audit trail for transparency.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("routing")


class RoutingAuditEntry:
    """Single audit log entry for a routing decision."""

    def __init__(
        self,
        query_preview: str,
        model_used: str,
        cascaded: bool,
        draft_accepted: bool,
        total_cost: float,
        latency_ms: float,
        quality_score: Optional[float],
        reason: str,
        complexity: str,
        routing_strategy: str,
        timestamp: str,
    ):
        self.query_preview = query_preview
        self.model_used = model_used
        self.cascaded = cascaded
        self.draft_accepted = draft_accepted
        self.total_cost = total_cost
        self.latency_ms = latency_ms
        self.quality_score = quality_score
        self.reason = reason
        self.complexity = complexity
        self.routing_strategy = routing_strategy
        self.timestamp = timestamp

    def to_dict(self) -> dict:
        return {
            "query_preview": self.query_preview,
            "model_used": self.model_used,
            "cascaded": self.cascaded,
            "draft_accepted": self.draft_accepted,
            "total_cost": self.total_cost,
            "latency_ms": self.latency_ms,
            "quality_score": self.quality_score,
            "reason": self.reason,
            "complexity": self.complexity,
            "routing_strategy": self.routing_strategy,
            "timestamp": self.timestamp,
        }


class CascadeRouter:
    """
    Model routing layer powered by CascadeFlow.

    Two-model cascade using Groq's free tier:
      1. Draft model:    llama-3.1-8b-instant   (fast, cheap)
      2. Verifier model: llama-3.3-70b-versatile (powerful, higher cost)

    CascadeFlow's speculative execution:
      - Draft model handles the query first
      - Quality validation checks the response
      - If quality passes → draft response returned (saves cost)
      - If quality fails → verifier model handles it (better result)

    Every decision is logged with full metadata.
    """

    # Groq model pricing (approximate per-1K-token costs for cascade weighting)
    DRAFT_MODEL = "llama-3.1-8b-instant"
    DRAFT_COST = 0.00005       # Very cheap — fast inference
    VERIFIER_MODEL = "llama-3.3-70b-versatile"
    VERIFIER_COST = 0.00059    # ~12x more expensive but much more capable

    def __init__(self):
        self._agent = None
        self._audit_log: list[RoutingAuditEntry] = []
        self._total_cost: float = 0.0
        self._total_queries: int = 0

    def _get_agent(self):
        """Lazy-init the CascadeAgent."""
        if self._agent is None:
            try:
                from cascadeflow import CascadeAgent, ModelConfig, QualityConfig

                # CascadeFlow reads GROQ_API_KEY from os.environ directly,
                # not from python-dotenv. Ensure it's propagated.
                groq_key = os.getenv("GROQ_API_KEY", "")
                if groq_key:
                    os.environ["GROQ_API_KEY"] = groq_key
                else:
                    logger.warning("GROQ_API_KEY not set — CascadeAgent will fail to init providers")

                self._agent = CascadeAgent(
                    models=[
                        ModelConfig(
                            name=self.DRAFT_MODEL,
                            provider="groq",
                            cost=self.DRAFT_COST,
                        ),
                        ModelConfig(
                            name=self.VERIFIER_MODEL,
                            provider="groq",
                            cost=self.VERIFIER_COST,
                        ),
                    ],
                    quality_config=QualityConfig(
                        confidence_thresholds={
                            "simple": 0.6,
                            "moderate": 0.7,
                            "complex": 0.8,
                        }
                    ),
                    enable_cascade=True,
                    verbose=True,
                )
                logger.info(
                    "CascadeAgent initialized: %s (draft) → %s (verifier)",
                    self.DRAFT_MODEL, self.VERIFIER_MODEL,
                )
            except ImportError:
                logger.warning(
                    "cascadeflow not installed. Running in direct-Groq mode. "
                    "Install with: pip install 'cascadeflow[groq]'"
                )
            except Exception as exc:
                logger.error("Failed to initialize CascadeAgent: %s", exc)
        return self._agent

    async def route_query(
        self,
        messages: list[dict],
        complexity_hint: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> dict:
        """
        Route a query through the cascade and return response + routing metadata.

        Args:
            messages: OpenAI-format message list [{"role": ..., "content": ...}].
            complexity_hint: Optional override ("simple", "moderate", "complex").
            max_tokens: Max tokens to generate.
            temperature: Sampling temperature.

        Returns:
            Dict with keys: content, model_used, routing_info, cost.
        """
        agent = self._get_agent()
        timestamp = datetime.now(timezone.utc).isoformat()

        # Extract the latest user message for logging
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = m["content"]
                break
        query_preview = user_msg[:80] + "..." if len(user_msg) > 80 else user_msg

        # ── CascadeFlow routing ──────────────────────────────────────
        if agent is not None:
            try:
                result = await agent.run(
                    query=user_msg,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

                # Build routing info from CascadeResult — use getattr for safety
                model_used = getattr(result, "model_used", "unknown")
                cascaded = getattr(result, "cascaded", False)
                draft_accepted = getattr(result, "draft_accepted", False)
                total_cost = getattr(result, "total_cost", 0)
                latency_ms = getattr(result, "latency_ms", 0)
                quality_score = getattr(result, "quality_score", None)
                complexity = getattr(result, "complexity", "unknown")
                routing_strategy = getattr(result, "routing_strategy", "cascade")
                reason = getattr(result, "reason", "")
                content = getattr(result, "content", "")

                # Cost breakdown is in a nested dict
                cost_breakdown = getattr(result, "cost_breakdown", {}) or {}
                draft_cost = cost_breakdown.get("draft_cost", 0) if isinstance(cost_breakdown, dict) else 0
                verifier_cost = cost_breakdown.get("verifier_cost", 0) if isinstance(cost_breakdown, dict) else 0
                cost_saved = cost_breakdown.get("cost_saved", 0) if isinstance(cost_breakdown, dict) else 0

                routing_info = {
                    "model_used": model_used,
                    "cascaded": cascaded,
                    "draft_accepted": draft_accepted,
                    "total_cost": total_cost,
                    "latency_ms": latency_ms,
                    "quality_score": quality_score,
                    "complexity": complexity,
                    "routing_strategy": routing_strategy,
                    "reason": reason,
                    "draft_model": self.DRAFT_MODEL,
                    "verifier_model": self.VERIFIER_MODEL,
                    "draft_cost": draft_cost,
                    "verifier_cost": verifier_cost,
                    "cost_saved": cost_saved,
                    "quality_check_passed": getattr(result, "quality_check_passed", None),
                    "rejection_reason": getattr(result, "rejection_reason", None),
                }

                # Log the routing decision
                self._log_decision(
                    query_preview=query_preview,
                    model_used=model_used,
                    cascaded=cascaded,
                    draft_accepted=draft_accepted,
                    total_cost=total_cost,
                    latency_ms=latency_ms,
                    quality_score=quality_score,
                    reason=reason,
                    complexity=complexity,
                    routing_strategy=routing_strategy,
                    timestamp=timestamp,
                )

                return {
                    "content": content,
                    "model_used": model_used,
                    "routing_info": routing_info,
                    "cost": total_cost,
                }

            except Exception as exc:
                logger.error("CascadeAgent.run() failed: %s", exc, exc_info=True)

        # ── Fallback: direct Groq call without cascade ───────────────
        return await self._direct_groq_call(
            messages=messages,
            query_preview=query_preview,
            max_tokens=max_tokens,
            temperature=temperature,
            timestamp=timestamp,
        )

    async def _direct_groq_call(
        self,
        messages: list[dict],
        query_preview: str,
        max_tokens: int,
        temperature: float,
        timestamp: str,
    ) -> dict:
        """
        Fallback: call Groq directly without CascadeFlow.

        Uses simple heuristic routing:
          - Short queries (< 50 chars, no question words) → fast model
          - Everything else → powerful model
        """
        try:
            from groq import AsyncGroq

            client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

            # Simple heuristic: short + simple → fast model, else → powerful
            user_msg = ""
            for m in reversed(messages):
                if m.get("role") == "user":
                    user_msg = m["content"]
                    break

            is_simple = (
                len(user_msg) < 50
                and not any(w in user_msg.lower() for w in [
                    "analyze", "compare", "strategy", "explain",
                    "recommend", "evaluate", "complex", "detailed",
                ])
            )
            model = self.DRAFT_MODEL if is_simple else self.VERIFIER_MODEL
            complexity = "simple" if is_simple else "complex"

            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            content = response.choices[0].message.content
            total_cost = (
                self.DRAFT_COST if model == self.DRAFT_MODEL else self.VERIFIER_COST
            )

            # Log even the fallback decision
            self._log_decision(
                query_preview=query_preview,
                model_used=model,
                cascaded=False,
                draft_accepted=(model == self.DRAFT_MODEL),
                total_cost=total_cost,
                latency_ms=0,  # Not tracked in fallback
                quality_score=None,
                reason=f"Direct Groq fallback — heuristic: {complexity}",
                complexity=complexity,
                routing_strategy="direct_fallback",
                timestamp=timestamp,
            )

            return {
                "content": content,
                "model_used": model,
                "routing_info": {
                    "model_used": model,
                    "cascaded": False,
                    "draft_accepted": model == self.DRAFT_MODEL,
                    "total_cost": total_cost,
                    "latency_ms": 0,
                    "quality_score": None,
                    "complexity": complexity,
                    "routing_strategy": "direct_fallback",
                    "reason": f"Direct Groq fallback — heuristic: {complexity}",
                    "draft_model": self.DRAFT_MODEL,
                    "verifier_model": self.VERIFIER_MODEL,
                    "savings_percentage": None,
                },
                "cost": total_cost,
            }

        except ImportError:
            logger.error(
                "Neither cascadeflow nor groq SDK is installed. "
                "Install with: pip install 'cascadeflow[groq]' or pip install groq"
            )
            return self._mock_response(query_preview, timestamp)

        except Exception as exc:
            logger.error("Direct Groq call failed: %s", exc)
            return self._mock_response(query_preview, timestamp)

    def _mock_response(self, query_preview: str, timestamp: str) -> dict:
        """Last-resort mock response when no LLM is available."""
        self._log_decision(
            query_preview=query_preview,
            model_used="mock",
            cascaded=False,
            draft_accepted=False,
            total_cost=0,
            latency_ms=0,
            quality_score=None,
            reason="No LLM available — returning mock response",
            complexity="unknown",
            routing_strategy="mock",
            timestamp=timestamp,
        )

        return {
            "content": (
                "I'm currently running without an LLM connection. "
                "Please check your GROQ_API_KEY in .env and ensure "
                "cascadeflow or groq is installed."
            ),
            "model_used": "mock",
            "routing_info": {
                "model_used": "mock",
                "cascaded": False,
                "draft_accepted": False,
                "total_cost": 0,
                "latency_ms": 0,
                "quality_score": None,
                "complexity": "unknown",
                "routing_strategy": "mock",
                "reason": "No LLM available",
                "draft_model": self.DRAFT_MODEL,
                "verifier_model": self.VERIFIER_MODEL,
                "savings_percentage": None,
            },
            "cost": 0,
        }

    # ── Audit Logging ────────────────────────────────────────────────
    def _log_decision(self, **kwargs) -> None:
        """
        Log every routing decision. This is mandatory per project rules:
        "Every cascadeflow routing decision must be logged."
        """
        entry = RoutingAuditEntry(**kwargs)
        self._audit_log.append(entry)
        self._total_queries += 1
        self._total_cost += kwargs.get("total_cost", 0)

        # Console log for visibility
        logger.info(
            "ROUTING DECISION | model=%s | cascaded=%s | draft_accepted=%s | "
            "cost=$%.6f | complexity=%s | reason=%s | query=%s",
            kwargs["model_used"],
            kwargs["cascaded"],
            kwargs["draft_accepted"],
            kwargs.get("total_cost", 0),
            kwargs["complexity"],
            kwargs["reason"],
            kwargs["query_preview"],
        )

    def get_audit_log(self, limit: int = 50) -> list[dict]:
        """Return the audit log as a list of dicts (most recent first)."""
        entries = self._audit_log[-limit:] if len(self._audit_log) > limit else self._audit_log
        return [e.to_dict() for e in reversed(entries)]

    def get_routing_stats(self) -> dict:
        """Aggregate routing statistics."""
        if not self._audit_log:
            return {
                "total_queries": 0,
                "total_cost": 0,
                "draft_acceptance_rate": 0,
                "cascade_rate": 0,
                "models_used": {},
            }

        cascaded_count = sum(1 for e in self._audit_log if e.cascaded)
        draft_accepted_count = sum(1 for e in self._audit_log if e.draft_accepted)
        model_counts: dict[str, int] = {}
        for entry in self._audit_log:
            model_counts[entry.model_used] = model_counts.get(entry.model_used, 0) + 1

        return {
            "total_queries": self._total_queries,
            "total_cost": round(self._total_cost, 6),
            "avg_cost_per_query": round(self._total_cost / self._total_queries, 6),
            "draft_acceptance_rate": round(
                draft_accepted_count / self._total_queries * 100, 1
            ),
            "cascade_rate": round(
                cascaded_count / self._total_queries * 100, 1
            ),
            "models_used": model_counts,
        }
