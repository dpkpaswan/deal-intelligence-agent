"""
Sales Deal Intelligence Agent — FastAPI Backend.

Endpoints:
  POST /chat              — Chat with a prospect (memory + routing)
  GET  /prospects          — List prospects (Supabase)
  POST /prospects          — Create a prospect (Supabase)
  GET  /history/{id}       — Conversation history from Hindsight
  POST /summary/{id}       — Generate session summary via reflect()
  GET  /audit-log          — CascadeFlow routing audit trail
  GET  /stats              — Aggregated routing + memory stats
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("main")

# ── Supabase Client ──────────────────────────────────────────────────────
supabase_client = None


def get_supabase():
    """Lazy-init Supabase client."""
    global supabase_client
    if supabase_client is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")
        if url and key:
            try:
                from supabase import create_client

                supabase_client = create_client(url, key)
                logger.info("Supabase client initialized")
            except ImportError:
                logger.warning(
                    "supabase not installed. Prospect storage will use in-memory fallback. "
                    "Install with: pip install supabase"
                )
            except Exception as exc:
                logger.error("Supabase init failed: %s", exc)
        else:
            logger.warning("SUPABASE_URL or SUPABASE_KEY not set — using in-memory prospect store")
    return supabase_client


# ── In-memory prospect fallback ──────────────────────────────────────────
_local_prospects: list[dict] = [
    {
        "id": "acme-corp",
        "name": "Acme Corporation",
        "company": "Acme Corp",
        "deal_stage": "Discovery",
        "deal_value": 50000,
        "contact_email": "jane@acme.com",
    },
    {
        "id": "globex-inc",
        "name": "Globex Industries",
        "company": "Globex Inc",
        "deal_stage": "Proposal",
        "deal_value": 120000,
        "contact_email": "bob@globex.com",
    },
    {
        "id": "initech-llc",
        "name": "Initech Solutions",
        "company": "Initech LLC",
        "deal_stage": "Negotiation",
        "deal_value": 85000,
        "contact_email": "peter@initech.com",
    },
]


# ── App lifecycle ────────────────────────────────────────────────────────
try:
    from .agent import SalesDealAgent  # when run as package: uvicorn backend.main:app
except ImportError:
    from agent import SalesDealAgent   # when run standalone: uvicorn main:app

agent = SalesDealAgent()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    logger.info("Starting Sales Deal Intelligence Agent")
    logger.info("Hindsight base URL: %s", os.getenv("HINDSIGHT_BASE_URL", "not set"))
    logger.info("Groq API key: %s", "set" if os.getenv("GROQ_API_KEY") else "NOT SET")
    logger.info("Supabase URL: %s", "set" if os.getenv("SUPABASE_URL") else "NOT SET (using local)")
    yield
    logger.info("Shutting down Sales Deal Intelligence Agent")


# ── FastAPI App ──────────────────────────────────────────────────────────
app = FastAPI(
    title="Sales Deal Intelligence Agent",
    description="AI-powered sales assistant with persistent memory and intelligent model routing",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ────────────────────────────────────────────
class ChatRequest(BaseModel):
    prospect_id: str
    message: str
    session_id: Optional[str] = None


class ProspectCreate(BaseModel):
    id: str
    name: str
    company: str
    deal_stage: str = "Discovery"
    deal_value: float = 0
    contact_email: str = ""


class SummaryRequest(BaseModel):
    custom_query: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────────


@app.get("/")
async def root():
    """Health check."""
    return {
        "status": "running",
        "service": "Sales Deal Intelligence Agent",
        "version": "1.0.0",
        "integrations": {
            "hindsight": "configured" if os.getenv("HINDSIGHT_API_KEY") else "not configured",
            "cascadeflow": "configured" if os.getenv("GROQ_API_KEY") else "not configured",
            "supabase": "configured" if os.getenv("SUPABASE_URL") else "local fallback",
        },
    }


# ── Chat ─────────────────────────────────────────────────────────────────
@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Chat with the agent about a specific prospect.

    The agent:
      1. Recalls past context from Hindsight
      2. Routes query through CascadeFlow (fast or powerful model)
      3. Retains the exchange for future sessions
      4. Returns response + routing info + memory context indicator
    """
    try:
        result = await agent.chat(
            prospect_id=request.prospect_id,
            message=request.message,
            session_id=request.session_id,
        )
        return result
    except Exception as exc:
        logger.error("Chat error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(exc)}")


# ── Prospects ────────────────────────────────────────────────────────────
@app.get("/prospects")
async def list_prospects():
    """List all prospects from Supabase or local fallback."""
    sb = get_supabase()
    if sb is not None:
        try:
            response = sb.table("prospects").select("*").execute()
            return {"prospects": response.data, "source": "supabase"}
        except Exception as exc:
            logger.error("Supabase query failed: %s — falling back to local", exc)

    return {"prospects": _local_prospects, "source": "local"}


@app.post("/prospects")
async def create_prospect(prospect: ProspectCreate):
    """Create a new prospect in Supabase or local fallback."""
    prospect_dict = prospect.model_dump()

    sb = get_supabase()
    if sb is not None:
        try:
            response = sb.table("prospects").insert(prospect_dict).execute()
            return {"prospect": response.data[0] if response.data else prospect_dict, "source": "supabase"}
        except Exception as exc:
            logger.error("Supabase insert failed: %s — falling back to local", exc)

    _local_prospects.append(prospect_dict)
    return {"prospect": prospect_dict, "source": "local"}


# ── History ──────────────────────────────────────────────────────────────
@app.get("/history/{prospect_id}")
async def get_history(prospect_id: str, limit: int = 50):
    """
    Get conversation history for a prospect.

    Returns turns from local memory (current process) and indicates
    whether Hindsight has cross-session data.
    """
    try:
        result = await agent.memory.get_history(prospect_id, limit=limit)
        return result
    except Exception as exc:
        logger.error("History error: %s", exc)
        raise HTTPException(status_code=500, detail=f"History fetch failed: {str(exc)}")


# ── Summary ──────────────────────────────────────────────────────────────
@app.post("/summary/{prospect_id}")
async def generate_summary(prospect_id: str, request: SummaryRequest = None):
    """
    Generate a session summary for a prospect.

    Uses Hindsight reflect() for raw insights, then CascadeFlow
    to produce a structured summary with key points + next action.
    """
    try:
        custom_query = request.custom_query if request else None
        result = await agent.generate_summary(
            prospect_id=prospect_id,
            custom_query=custom_query,
        )
        return result
    except Exception as exc:
        logger.error("Summary error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Summary generation failed: {str(exc)}")


# ── Audit Log ────────────────────────────────────────────────────────────
@app.get("/audit-log")
async def get_audit_log(limit: int = 50):
    """
    Get the CascadeFlow routing audit log.

    Every routing decision is logged here — which model was chosen,
    whether the draft was accepted, cost, complexity, and reasoning.
    """
    return {
        "entries": agent.get_audit_log(limit),
        "stats": agent.get_stats(),
    }


# ── Stats ────────────────────────────────────────────────────────────────
@app.get("/stats")
async def get_stats():
    """Aggregated routing and memory statistics."""
    return agent.get_stats()


# ── Health Check ─────────────────────────────────────────────────────────
@app.get("/health-check")
async def health_check():
    """
    Test Hindsight retain→recall round-trip.

    Retains a test string, waits 3s for indexing, then tries to recall it.
    Returns detailed diagnostics including the raw response object.
    """
    result = await agent.memory.health_check()
    return result


# ── Run directly ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
