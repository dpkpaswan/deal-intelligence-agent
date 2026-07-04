# Sales Deal Intelligence Agent

AI-powered sales assistant with **persistent memory across sessions** and **intelligent model routing**.

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend** | FastAPI + Python | API server |
| **Frontend** | React + Vite | Chat UI |
| **Memory** | [Hindsight](https://hindsight.vectorize.io) | Cross-session conversation memory |
| **Routing** | [CascadeFlow](https://docs.cascadeflow.ai) | Smart model routing + cost control |
| **LLM** | Groq (free tier) | LLama 3.1 8B + LLama 3.3 70B |
| **Data** | Supabase (optional) | Prospect storage |

## Features

- **Hindsight Memory** — Session 1 is generic. By session 3, the agent recalls past objections, preferences, and deal context
- **CascadeFlow Routing** — Simple queries use fast/cheap 8B model. Complex analysis auto-escalates to 70B. Every decision is audit-logged
- **Session Summaries** — AI-generated key points + next actions after each conversation
- **Prospect Management** — Sidebar with search, CRUD, and deal stage tracking

## Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/dpkpaswan/deal-intelligence-agent.git
cd deal-intelligence-agent
```

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env — add your GROQ_API_KEY (required) and HINDSIGHT_API_KEY (optional)
```

Get free API keys:
- **Groq**: https://console.groq.com
- **Hindsight**: https://ui.hindsight.vectorize.io/signup

Start the backend:
```bash
uvicorn main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chat` | POST | Chat with a prospect (memory + routing) |
| `/prospects` | GET/POST | List or create prospects |
| `/history/{id}` | GET | Conversation history |
| `/summary/{id}` | POST | Generate session summary |
| `/audit-log` | GET | CascadeFlow routing decisions |
| `/stats` | GET | Routing + memory statistics |
| `/health-check` | GET | Hindsight retain→recall test |

## Architecture

```
React Frontend (5173) → FastAPI Backend (8000)
                            ├── Hindsight (retain/recall/reflect)
                            ├── CascadeFlow (8B draft → 70B verifier)
                            └── Supabase (optional prospect storage)
```

## License

MIT
