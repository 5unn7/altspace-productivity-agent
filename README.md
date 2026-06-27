# AltSpace — your AI Chief of Staff

> IITR-SE-2509 · Module 6 Capstone · **Project 03 — Personal Productivity Agent**

Most apps treat AI as a search box. **AltSpace treats it as someone you work with** — a chief of staff you check in with twice a day. It remembers your history, tells you what slipped, drafts your end-of-day summary, and plans tomorrow. This is the smallest honest slice of a bigger vision: AI that holds your context across days and acts on it.

## What it does

- **Morning check-in** — brain-dump your day in free text; the agent parses it into structured tasks, classifies them (work / personal / health / learning), and tags urgency.
- **Surfaces what's overdue** — anything due that you didn't close.
- **Evening check-in** — mark what you finished; the agent drafts a candid **EOD summary** ("here's what you got done, here's what slipped") and **plans tomorrow**.
- **This week** — your daily summaries side by side.
- **Weekly review** — patterns it noticed ("you've pushed *gym* four weeks running").

## Architecture

```
Streamlit (frontend)  ──HTTP+JWT──▶  FastAPI (backend)  ──▶  LangGraph agent
   check-in forms                      /auth /tasks            classify → surface-overdue
   task board                          /checkin /review        → EOD-summary → plan-tomorrow
   week view                                │                   (Groq llama-3.1-8b / 3.3-70b)
                                            ▼                   checkpointer: thread per user
                                   SQLAlchemy + Alembic
                                   SQLite (dev) / Postgres (prod)
                                   users · tasks · daily_logs · eod_summaries · weekly_reviews
```

The agent is a LangGraph `StateGraph` with a per-user checkpointer thread, so state carries forward across days — that's the "memory." Full design in [BUILD-PLAN.md](BUILD-PLAN.md). Schema in [docs/schema.dbml](docs/schema.dbml); models in [backend/app/models.py](backend/app/models.py).

## Run locally

**Backend**
```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # set GROQ_API_KEY + JWT_SECRET
alembic upgrade head
uvicorn app.main:app --reload                         # http://localhost:8000  · /docs for Swagger
```

**Frontend**
```bash
cd frontend
pip install -r requirements.txt
# set API_BASE_URL (defaults to http://localhost:8000)
streamlit run streamlit_app.py                        # http://localhost:8501
```

## Live demo

- Frontend: _<Streamlit Community Cloud URL>_
- Backend API + Swagger: _<Render URL>/docs_

## Tech

FastAPI · SQLAlchemy 2.0 + Alembic · SQLite/Postgres · LangGraph (+ Groq via `langchain-groq`) · JWT · APScheduler · Streamlit. Free-tier only.

## What's next (the vision)

AltSpace v0 is one agent you check in with. The full platform is a **team** of AI personas — a Chief that delegates, specialists that execute, every handoff a typed contract — that runs your work alongside you. This capstone proves the core loop: an AI that holds context and acts on it.
