"""
Hindsight Memory Integration for Sales Deal Intelligence Agent.

Wraps the hindsight-client SDK to provide persistent memory across sessions.
Each prospect gets its own memory bank, so conversation history is isolated.

Key operations:
  - retain(): Store conversation turns after each exchange
  - recall(): Retrieve relevant past context before generating a response
  - reflect(): Synthesize session summaries with key points + next actions
  - get_history(): Return raw conversation log for UI display
"""

import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("memory")


class HindsightMemory:
    """
    Persistent memory layer backed by Hindsight.

    Each prospect gets a dedicated memory bank (bank_id = "prospect-{prospect_id}").
    This means Session 1 with Prospect A is generic (no prior context),
    but Session 3 with the same prospect recalls everything from sessions 1 & 2.
    """

    def __init__(self):
        self._base_url = os.getenv("HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io")
        self._api_key = os.getenv("HINDSIGHT_API_KEY", "")
        self._client = None

        # In-memory fallback for conversation logs (always available, even if
        # Hindsight is unreachable). Keys: prospect_id -> list of turn dicts.
        self._local_history: dict[str, list[dict]] = {}

    def _get_client(self):
        """Lazy-init the Hindsight client."""
        if self._client is None:
            try:
                from hindsight_client import Hindsight

                self._client = Hindsight(
                    base_url=self._base_url,
                    api_key=self._api_key,
                )
                logger.info("Hindsight client initialized (base_url=%s)", self._base_url)
            except ImportError:
                logger.warning(
                    "hindsight-client not installed. Running in local-only mode. "
                    "Install with: pip install hindsight-client"
                )
            except Exception as exc:
                logger.error("Failed to initialize Hindsight client: %s", exc)
        return self._client

    @staticmethod
    def _bank_id(prospect_id: str) -> str:
        """Deterministic bank ID per prospect."""
        return f"prospect-{prospect_id}"

    # ── Retain ───────────────────────────────────────────────────────────
    async def retain(
        self,
        prospect_id: str,
        content: str,
        role: str = "user",
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Store a conversation turn in Hindsight memory.

        Args:
            prospect_id: The prospect this conversation belongs to.
            content: The message text to store.
            role: "user" or "assistant".
            metadata: Optional extra metadata (e.g. deal stage, sentiment).

        Returns:
            Dict with status and stored turn info.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        turn = {
            "role": role,
            "content": content,
            "timestamp": timestamp,
            "metadata": metadata or {},
        }

        # Always store locally for fast retrieval
        if prospect_id not in self._local_history:
            self._local_history[prospect_id] = []
        self._local_history[prospect_id].append(turn)

        # Store in Hindsight for cross-session persistence
        bank_id = self._bank_id(prospect_id)
        client = self._get_client()

        if client is not None:
            try:
                formatted_content = (
                    f"[{role.upper()}] [{timestamp}] {content}"
                )
                if metadata:
                    formatted_content += f" | metadata: {metadata}"

                await client.aretain(bank_id=bank_id, content=formatted_content)
                logger.info(
                    "Retained memory for prospect %s (bank=%s, role=%s)",
                    prospect_id, bank_id, role,
                )
                # Allow Hindsight indexing time before any subsequent recall
                await asyncio.sleep(3)
                logger.info("Post-retain indexing delay complete for prospect %s", prospect_id)
                return {"status": "stored", "backend": "hindsight", "turn": turn}
            except Exception as exc:
                logger.error("Hindsight retain failed: %s — falling back to local", exc)

        return {"status": "stored", "backend": "local", "turn": turn}

    # ── Recall ───────────────────────────────────────────────────────────
    async def recall(
        self,
        prospect_id: str,
        query: str,
        max_results: int = 5,
    ) -> dict:
        """
        Retrieve relevant past context for a prospect.

        This is the core of the "memory across sessions" feature:
        - Session 1: recall returns nothing → agent gives generic response
        - Session 3: recall returns rich context → agent references past deals,
          preferences, objections, etc.

        Args:
            prospect_id: Which prospect's memory to search.
            query: The current user query (used for semantic search).
            max_results: Max number of memories to return.

        Returns:
            Dict with memories list and metadata.
        """
        bank_id = self._bank_id(prospect_id)
        client = self._get_client()

        memories = []
        source = "none"

        # Try Hindsight first (cross-session persistence)
        if client is not None:
            try:
                results_raw = await client.arecall(bank_id=bank_id, query=query)

                # Debug: log the full raw response
                logger.info(
                    "RAW HINDSIGHT RECALL RESPONSE for prospect %s:\n"
                    "  type=%s\n  value=%r",
                    prospect_id, type(results_raw).__name__, results_raw,
                )

                # Hindsight returns a response object with .results field
                # containing a list of RecallResult objects, each with .text
                if hasattr(results_raw, 'results') and results_raw.results:
                    memories = [
                        r.text for r in results_raw.results[:max_results]
                        if hasattr(r, 'text') and r.text
                    ]
                    source = "hindsight"

                logger.info(
                    "Recalled %d memories for prospect %s (source=%s)",
                    len(memories), prospect_id, source,
                )
            except Exception as exc:
                logger.error("Hindsight recall failed: %s", exc, exc_info=True)

        # Fallback: search local history with simple keyword matching
        if not memories and prospect_id in self._local_history:
            query_lower = query.lower()
            for turn in reversed(self._local_history[prospect_id]):
                if query_lower in turn["content"].lower() or len(memories) < max_results:
                    memories.append(
                        f"[{turn['role'].upper()}] {turn['content']}"
                    )
                if len(memories) >= max_results:
                    break
            source = "local"

        return {
            "prospect_id": prospect_id,
            "query": query,
            "memories": memories,
            "count": len(memories),
            "source": source,
            "has_context": len(memories) > 0,
        }

    # ── Reflect ──────────────────────────────────────────────────────────
    async def reflect(
        self,
        prospect_id: str,
        query: Optional[str] = None,
    ) -> dict:
        """
        Synthesize a session summary using Hindsight's reflect capability.

        Analyzes all stored memories for a prospect and produces:
        - Key discussion points
        - Prospect sentiment / objections
        - Recommended next action

        Args:
            prospect_id: Which prospect to reflect on.
            query: Optional focus query. Defaults to a sales-oriented prompt.

        Returns:
            Dict with the reflection text and metadata.
        """
        if query is None:
            query = (
                "Summarize the key points from our conversations with this prospect. "
                "Include: 1) Main topics discussed, 2) Any objections or concerns raised, "
                "3) Current deal stage assessment, 4) Recommended next action for the sales rep."
            )

        bank_id = self._bank_id(prospect_id)
        client = self._get_client()

        # Try Hindsight reflect
        if client is not None:
            try:
                result = await client.areflect(bank_id=bank_id, query=query)
                reflection = result if isinstance(result, str) else str(result)
                logger.info("Generated reflection for prospect %s", prospect_id)
                return {
                    "prospect_id": prospect_id,
                    "summary": reflection,
                    "source": "hindsight",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
            except Exception as exc:
                logger.error("Hindsight reflect failed: %s — generating local summary", exc)

        # Fallback: build a simple summary from local history
        return self._local_reflect(prospect_id)

    def _local_reflect(self, prospect_id: str) -> dict:
        """Generate a basic summary from local conversation history."""
        history = self._local_history.get(prospect_id, [])
        if not history:
            return {
                "prospect_id": prospect_id,
                "summary": "No conversation history found for this prospect.",
                "source": "local",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        user_messages = [t["content"] for t in history if t["role"] == "user"]
        assistant_messages = [t["content"] for t in history if t["role"] == "assistant"]

        summary_parts = [
            f"**Session Summary for Prospect {prospect_id}**\n",
            f"Total exchanges: {len(history)} ({len(user_messages)} from user, "
            f"{len(assistant_messages)} from assistant)\n",
            "**Key Topics Discussed:**",
        ]

        # Extract first few user messages as topic indicators
        for i, msg in enumerate(user_messages[:5], 1):
            preview = msg[:100] + "..." if len(msg) > 100 else msg
            summary_parts.append(f"  {i}. {preview}")

        summary_parts.append("\n**Recommended Next Action:** Follow up on the latest discussion points.")

        return {
            "prospect_id": prospect_id,
            "summary": "\n".join(summary_parts),
            "source": "local",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── History ──────────────────────────────────────────────────────────
    async def get_history(
        self,
        prospect_id: str,
        limit: int = 50,
    ) -> dict:
        """
        Return raw conversation history for UI display.

        Args:
            prospect_id: Which prospect's history to fetch.
            limit: Max number of turns to return.

        Returns:
            Dict with turns list and metadata.
        """
        history = self._local_history.get(prospect_id, [])
        turns = history[-limit:] if len(history) > limit else history

        return {
            "prospect_id": prospect_id,
            "turns": turns,
            "total_turns": len(history),
            "returned_turns": len(turns),
        }

    # ── Utilities ────────────────────────────────────────────────────────
    def get_prospect_ids(self) -> list[str]:
        """Return all prospect IDs that have local history."""
        return list(self._local_history.keys())

    async def clear_history(self, prospect_id: str) -> dict:
        """Clear local history for a prospect (does not affect Hindsight)."""
        removed = len(self._local_history.pop(prospect_id, []))
        return {
            "prospect_id": prospect_id,
            "turns_removed": removed,
            "note": "Hindsight memory bank is not cleared. Use Hindsight dashboard to manage.",
        }

    async def health_check(self) -> dict:
        """
        Verify Hindsight retain→recall round-trip works.

        Retains a test string, waits 3 seconds for indexing,
        then recalls it and checks if the content was found.
        """
        test_bank = "health-check-test"
        test_content = f"health_check_marker_{datetime.now(timezone.utc).isoformat()}"
        client = self._get_client()

        if client is None:
            return {"healthy": False, "reason": "Hindsight client not available"}

        try:
            # Retain
            await client.aretain(bank_id=test_bank, content=test_content)
            logger.info("Health check: retained test content")

            # Wait for indexing
            await asyncio.sleep(3)

            # Recall
            results = await client.arecall(bank_id=test_bank, query="health_check_marker")
            logger.info("Health check: raw recall response: %r", results)

            # Check if anything came back
            result_str = str(results)
            found = "health_check_marker" in result_str

            return {
                "healthy": found,
                "retain": "ok",
                "recall": "ok" if found else "empty",
                "raw_response_type": type(results).__name__,
                "raw_response_preview": result_str[:500],
            }
        except Exception as exc:
            logger.error("Health check failed: %s", exc, exc_info=True)
            return {"healthy": False, "reason": str(exc)}
