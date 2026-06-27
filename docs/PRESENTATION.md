# Presentation — AltSpace: your AI Chief of Staff

> Drop this into **Gamma / Canva / Google Slides**. One block = one slide. Set sharing to
> **"anyone with the link can view"** before submitting. Speaker notes are in _italics_.
> Grab a screenshot or two from your live app for slides 5, 9. The architecture diagram (slide 6)
> can be screenshotted from `docs/architecture.md` or redrawn in the deck.

---

## Slide 1 — Title
**AltSpace**
*Your AI chief of staff.*

Sunny · IITR-SE-2509 Module 6 Capstone · Project 03 (Personal Productivity Agent)

_Live app: <Streamlit URL> · API: <Render URL>/docs · Code: github.com/5unn7/altspace-productivity-agent_

---

## Slide 2 — The Problem
**You don't have a to-do problem. You have a memory and prioritization problem.**

- You forget what was due.
- You forget how long things actually take.
- You end every day unsure if you did the things that mattered.

*To-do apps make you do all the thinking. The list just sits there. The hard part — remembering, prioritizing, recapping — is still on you.*

---

## Slide 3 — Who it's for
**Anyone running too many threads at once.**

- Solo operators / founders juggling multiple projects
- Students balancing coursework, deadlines, and life
- Knowledge workers who end the day without knowing if it counted

*The wedge: people who'd benefit from a chief of staff but can't afford one.*

---

## Slide 4 — The Insight
**Treat AI as a teammate, not a search box.**

Most AI apps answer questions. AltSpace **holds your context across days and acts on it** — it classifies, remembers, summarizes, and plans. You check in twice a day; it does the boring, high-value work in between.

*This is the AltSpace thesis: humans define intent, the AI executes. This capstone is the smallest honest slice of that — one agent you actually work with.*

---

## Slide 5 — What it does
**A twice-a-day check-in loop.**

- **Morning** — brain-dump in plain English → it classifies tasks (work / personal / health / learning), tags priority, flags what slipped.
- **Evening** — tick off what you finished → it writes your EOD summary and plans tomorrow, carrying unfinished work forward.
- **Weekly** — it surfaces patterns: what you keep pushing, where your time goes.

_[screenshot: the morning check-in result with classified task cards]_

---

## Slide 6 — Architecture
**Streamlit → FastAPI → LangGraph agent → SQLAlchemy / Postgres**

```
┌── Streamlit frontend ──┐    HTTP + JWT    ┌── FastAPI backend ──────────────┐
│  morning / evening     │ ───────────────▶ │  /auth  /tasks  /checkin /review │
│  task board · week     │                  │            │                     │
└────────────────────────┘                  │            ▼                     │
                                            │   LangGraph StateGraph           │
                                            │   classify → overdue →           │
                                            │   EOD summary → plan tomorrow    │
                                            │   (Groq llama-3.1-8b / 3.3-70b)  │
                                            │   checkpointer: 1 thread/user    │
                                            │            │                     │
                                            │            ▼                     │
                                            │   SQLAlchemy 2.0 + Alembic       │
                                            │   SQLite (dev) / Postgres (prod) │
                                            └──────────────────────────────────┘
```

*Stateless API, stateful agent. The LangGraph checkpointer gives each user one rolling thread, so context carries forward across days — that's the "memory."*

---

## Slide 7 — The Agent (the technical heart)
**A LangGraph `StateGraph` with conditional entry + a durable checkpointer.**

- **Morning path:** `classify` → `surface_overdue`
- **Evening path:** `ingest_completions` → `eod_summary` → `plan_tomorrow`
- **Weekly path:** `weekly_patterns`
- Two model tiers: **llama-3.1-8b-instant** for fast classification, **llama-3.3-70b** for summaries & planning.
- Robust by design: every node degrades gracefully — a blank check-in or a slow model never crashes the flow.

*This is the M6 learning outcome: real LLMs wired into LangGraph nodes with a SQLite/Postgres checkpointer, not hardcoded responses.*

---

## Slide 8 — Tech stack
| Layer | Tech |
|---|---|
| Frontend | Streamlit |
| Backend | FastAPI + Uvicorn, JWT auth |
| Agent | LangGraph + Groq (langchain-groq) |
| Data | SQLAlchemy 2.0 + Alembic · SQLite (dev) / Postgres (prod) |
| Deploy | Render (API + Postgres) + Streamlit Community Cloud |

*All free-tier. Pinned, reproducible `requirements.txt`. Cross-tenant safe — every query scoped to the authenticated user.*

---

## Slide 9 — What works (it's live)
- ✅ Sign up / log in (JWT)
- ✅ Morning check-in → real LLM task classification + overdue surfacing
- ✅ Task board (complete / reopen / delete / add)
- ✅ Evening check-in → real EOD summary + tomorrow's plan
- ✅ "This week" daily summaries
- ✅ Weekly pattern review
- ✅ Deployed: live frontend + live API with Swagger docs

_[screenshot: the evening EOD summary + tomorrow's plan]_

---

## Slide 10 — What I'd build in two more weeks
**Near-term:**
- Voice morning check-in (browser speech-to-text)
- Email reminders for what slipped (APScheduler + SMTP)
- Calendar import for real context
- Reranked retrieval / better grounding so summaries cite the exact task they mean

**The vision (where AltSpace goes):**
- Not one agent — a **team** of AI personas: a **Chief** that delegates, specialists that execute, every handoff a typed contract. An AI organization you run by setting intent.

*AltSpace v0 proves the core loop: an AI that holds context and acts on it. The rest is scaling that from one teammate to a whole team.*

---

## Slide 11 — Close
**AltSpace — an AI you work with, not a search box.**

- 🔗 Live app: `<Streamlit URL>`
- 🔗 API + Swagger: `<Render URL>/docs`
- 🔗 Code: `github.com/5unn7/altspace-productivity-agent`

*Thank you.*
