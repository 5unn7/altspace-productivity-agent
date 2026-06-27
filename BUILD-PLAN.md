# AltSpace — AI Chief of Staff · Capstone Build Plan

> **Course:** IITR-SE-2509 Cohort B · Module 6 Capstone · **Project 03 — Personal Productivity Agent**
> **Build:** solo · **Deadline:** plan to **Sun 28 Jun 2026 EOD** (brief says 28; instructions text says 30 — build to 28).
> **Authored:** 2026-06-26 · **Status:** active execution plan, built for parallel-agent fan-out.

## 0. The product (and the framing that wins the deck)

**AltSpace** is your AI **chief of staff**. You check in twice a day; it remembers everything, tells you what slipped, writes your end-of-day summary, and plans tomorrow. The capstone narrative: *"Most apps treat AI as a search box. AltSpace treats it as someone you work with — an agent that holds your context across days and acts on it."* This single-module build is **AltSpace v0**; the "what's next / two more weeks" slide is the full multi-persona AltSpace platform.

This satisfies Project 03's core outcomes exactly: daily check-in, task classification + urgency, overdue surfacing, auto-drafted EOD summary, tomorrow's plan, weekly pattern review.

## 1. Locked stack (the taught, free, low-risk path)

| Layer | Choice | Why |
|---|---|---|
| Frontend | **Streamlit** | Brief's recommended fit for a data-light, chat-like UI. One-line forms/chat. Deploys free on Streamlit Community Cloud. |
| Backend | **FastAPI + Uvicorn** | Graded deliverable wants FastAPI + `/docs` Swagger. JWT auth. |
| Agent core | **LangGraph `StateGraph` + checkpointer** (`SqliteSaver` dev / `PostgresSaver` prod), `thread_id = user-{id}` | M6 learning outcome. Nodes: classifier → overdue-surfacer → EOD-summarizer → next-day-planner. |
| LLM | **Groq free tier** — `llama-3.1-8b-instant` (classify/parse) + `llama-3.3-70b-versatile` (summaries/plan/patterns) | Free, fast, brief-recommended. Single `GROQ_API_KEY`. |
| DB | **SQLAlchemy 2.0 + Alembic** · SQLite (dev) / **Postgres** (prod, Render free) | Alembic folder is a graded deliverable. Postgres survives restarts (demo durability). |
| Auth | **JWT** (`python-jose` + `passlib[bcrypt]`) | Reuse M3 CRUD+JWT patterns. |
| Scheduler | **APScheduler** | Weekly review job + (stretch) reminders. Also exposed as a manual "Run weekly review" button so it's demo-able without waiting for Sunday. |
| Deploy | **Render** (backend + free Postgres) + **Streamlit Community Cloud** (frontend) | Two public URLs: frontend + backend `/docs`. Both free. |

**Hard rule:** stay inside this stack. No tool the course didn't teach.

## 2. Repo layout (matches the pre-flight checklist exactly)

```
altspace-productivity-agent/
├── README.md                  # root README (REQUIRED by checklist)
├── BUILD-PLAN.md              # this file
├── render.yaml                # Render blueprint (backend + Postgres)
├── docs/
│   ├── architecture.md        # architecture diagram (for the deck)
│   └── schema.dbml            # DB schema diagram (graded deliverable)
├── backend/                   # REQUIRED folder
│   ├── requirements.txt       # graded deliverable
│   ├── .env.example           # graded deliverable
│   ├── alembic.ini
│   ├── alembic/               # migrations folder (graded deliverable)
│   │   ├── env.py
│   │   └── versions/
│   └── app/
│       ├── main.py            # FastAPI app + CORS + router includes
│       ├── config.py          # pydantic-settings
│       ├── database.py        # engine, SessionLocal, get_db
│       ├── models.py          # SQLAlchemy models  ← CONTRACT (scaffolded)
│       ├── schemas.py         # Pydantic v2 schemas ← CONTRACT (scaffolded)
│       ├── security.py        # JWT + password hashing + get_current_user
│       ├── llm.py             # Groq client factory (two model tiers)
│       ├── routes/
│       │   ├── auth.py        # POST /auth/signup, /auth/login, GET /auth/me
│       │   ├── tasks.py       # CRUD /tasks
│       │   ├── checkin.py     # POST /checkin/morning, /checkin/evening
│       │   └── review.py      # POST /review/weekly, GET /summaries, GET /reviews
│       └── agent/
│           ├── state.py       # CheckinState TypedDict ← CONTRACT
│           ├── nodes.py       # classify / surface_overdue / eod_summary / plan_tomorrow / weekly_patterns
│           └── graph.py       # StateGraph build + checkpointer + run helpers
└── frontend/                  # REQUIRED folder
    ├── requirements.txt
    ├── streamlit_app.py       # entry: login → check-ins → task board → week view
    └── lib/
        ├── api.py             # httpx client to the FastAPI backend (JWT in header)
        └── ui.py              # shared components (task card, summary panel)
```

## 3. Data model (the contract — see `backend/app/models.py`)

- **users**: id, email (unique), hashed_password, name, streak_count, last_checkin_date, created_at.
- **tasks**: id, user_id→users, title, category (`work|personal|health|learning|other`), priority (`low|medium|high`), status (`pending|completed|slipped`), due_date, source (`morning|agent_planned|emerged`), created_at, completed_at.
- **daily_logs**: id, user_id, log_date, kind (`morning|evening`), raw_text, created_at. (Raw check-in text the agent parsed.)
- **eod_summaries**: id, user_id, summary_date, summary_text, tomorrow_plan (text), stats_json, created_at.
- **weekly_reviews**: id, user_id, week_start, patterns_text, stats_json, created_at.

## 4. API contract (so routes / frontend / agent build in parallel)

| Method | Path | Auth | Body → Returns |
|---|---|---|---|
| POST | `/auth/signup` | – | `UserCreate` → `Token` |
| POST | `/auth/login` | – | `UserLogin` (OAuth2 form) → `Token` |
| GET | `/auth/me` | JWT | → `UserOut` |
| GET | `/tasks` | JWT | query: `?status&date` → `TaskOut[]` |
| POST | `/tasks` | JWT | `TaskCreate` → `TaskOut` |
| PATCH | `/tasks/{id}` | JWT | `TaskUpdate` (e.g. mark complete) → `TaskOut` |
| DELETE | `/tasks/{id}` | JWT | → 204 |
| POST | `/checkin/morning` | JWT | `MorningCheckinIn{raw_text}` → `CheckinResult{greeting, planned_tasks[], overdue[]}` |
| POST | `/checkin/evening` | JWT | `EveningCheckinIn{raw_text, completed_task_ids[]}` → `CheckinResult{eod_summary, tomorrow_plan, tomorrow_tasks[]}` |
| POST | `/review/weekly` | JWT | → `WeeklyReviewOut` (manual trigger; same code APScheduler calls) |
| GET | `/summaries` | JWT | `?from&to` → `EodSummaryOut[]` (for the "This week" view) |
| GET | `/reviews` | JWT | → `WeeklyReviewOut[]` |

CORS allows the Streamlit origin (`FRONTEND_ORIGIN`).

## 5. The LangGraph agent (M6 learning outcome — the core)

**State** (`agent/state.py`): `user_id, kind, raw_text, completed_task_ids, parsed_tasks, overdue, eod_summary, tomorrow_plan, tomorrow_tasks, result_message`.

**Graph**: a single `StateGraph` with a `SqliteSaver`/`PostgresSaver` checkpointer, `thread_id = f"user-{user_id}"` so each user has one rolling thread (state carries forward across days — the "memory" the brief wants). Conditional entry on `kind`:

- **morning path:** `classify` (8b parses free text → structured tasks + category + urgency, persists `tasks` + `daily_log`) → `surface_overdue` (DB query: pending tasks with `due_date < today` → mark `slipped`, return list) → emit greeting + today's plan + overdue.
- **evening path:** `ingest_completions` (mark `completed_task_ids` done, parse any emerged tasks) → `eod_summary` (70b drafts the 1-paragraph "done vs slipped") → `plan_tomorrow` (70b proposes tomorrow's tasks from slipped + priorities + patterns, inserts them as `tasks` with `source=agent_planned`) → persist `eod_summaries`.
- **weekly:** `weekly_patterns` (70b over the 7-day window → "you pushed gym 4 weeks running", category mix) → persist `weekly_reviews`.

**Voice:** all LLM output speaks as **AltSpace**, a candid, concise chief of staff (consistent system prompt). This is the "someone you work with" identity — cheap, high-impact for the "quality of execution" mark.

LLM wiring per `ref-langgraph-llm-wiring.pdf` (real Groq in nodes + checkpointer, not hardcoded).

## 6. Scope triage — graded on "can a grader complete the core flow LIVE"

**MUST (the demo-able core flow — build first):**
1. JWT signup/login. 2. Morning check-in (free-text → classified tasks). 3. Task board (by category/urgency). 4. Evening check-in (mark complete → EOD summary + tomorrow plan). 5. "This week" view. 6. Persistence across restarts (Postgres prod). 7. Deployed: frontend URL + backend `/docs`. 8. Repo hygiene: `/frontend` `/backend`, README, `requirements.txt`, `.env.example`, Alembic folder, schema diagram.

**SHOULD (core outcome, keep — de-risked as a manual button):**
9. Weekly pattern review via a **"Run weekly review now"** button (same function APScheduler schedules) — demo-able without waiting for Sunday.

**STRETCH (only if time, in priority order):**
10. Streak gamification (trivial; high charm). 11. "Show retrieved/agent-reasoning" debug toggle (transparency, easy). 12. Email reminder via APScheduler + SMTP. 13. Voice morning check-in (browser STT). 14. Calendar import (mock JSON).

**CUT unless everything else is done:** anything not above.

## 7. Parallel-agent wave plan ("lots of agents")

Fresh repo → clean module boundaries → safe parallelism once the contract (models + schemas + state) is locked.

**Wave 0 — Foundation (serial, ~done in scaffold):** repo layout, `models.py`, `schemas.py`, `state.py`, `config.py`, `database.py`, `requirements.txt`, `.env.example`, Alembic init. **This locks the contract.** (Most of it is scaffolded with this plan.)

**Wave 1 — Parallel build (fan out, each owns its own files):**
- **Agent A — Auth:** `security.py` + `routes/auth.py` (JWT, hashing, `get_current_user`).
- **Agent B — Tasks CRUD:** `routes/tasks.py`.
- **Agent C — LangGraph core:** `llm.py` + `agent/nodes.py` + `agent/graph.py` (the AI heart).
- **Agent D — Check-in + review routes:** `routes/checkin.py` + `routes/review.py` (calls Agent C's graph).
- **Agent E — Streamlit frontend:** `frontend/streamlit_app.py` + `frontend/lib/*` (against the API contract in §4).
- **Agent F — Deploy + docs:** `render.yaml`, Alembic migration, `docs/architecture.md`, `docs/schema.dbml`, root `README.md`, `.streamlit` config.

Agents B/D depend on A's `get_current_user` signature (fixed in the contract). D depends on C's `run_checkin(state)` helper signature (fixed in §5). E depends only on the §4 API contract (HTTP — no code coupling). So all six can start; B/D/E stub against the locked signatures and integrate.

**Wave 2 — Integrate + migrate + smoke (serial):** wire `main.py` includes, run Alembic, end-to-end local smoke (signup → morning → evening → week view), fix breaks.

**Wave 3 — Deploy + record:** push public GitHub repo, deploy backend to Render + Postgres, deploy frontend to Streamlit Cloud, verify both URLs in **incognito**, then record the <5-min video + build the deck.

## 8. Deploy plan (free tier, two URLs)

1. **GitHub** — public repo, `/frontend` + `/backend` + README at root.
2. **Backend → Render:** `render.yaml` provisions a free web service (Uvicorn) + free Postgres. Env: `DATABASE_URL` (Render injects), `GROQ_API_KEY`, `JWT_SECRET`. Alembic runs on deploy (`alembic upgrade head` in the start command). Verify `/<url>/docs` Swagger loads.
3. **Frontend → Streamlit Community Cloud:** point at `frontend/streamlit_app.py`; secret `API_BASE_URL` = the Render backend URL. Verify the public URL.
4. **Incognito test** every URL (pre-flight checklist: links must open without login prompts the grader can't pass).

> ⚠️ Free Postgres on Render is the durable store. Do **not** rely on a local SQLite file in prod (Render's web FS is ephemeral). SQLite is dev-only; `DATABASE_URL` switches prod to Postgres. LangGraph checkpointer follows the same split.

## 9. Submission deliverables → checklist

- [ ] **Video < 5 min** — screen-record the core flow live (signup → morning check-in → task board → evening check-in → EOD summary + tomorrow plan → "this week" → weekly review). Loom/OBS.
- [ ] **Presentation** (Gamma/Slides, "anyone with link can view") — problem · who it's for (the AltSpace teammate vision) · architecture diagram · what works (demo) · what's next / 2 more weeks (full AltSpace platform).
- [ ] **Frontend** — public Streamlit URL **and** in the repo `/frontend`.
- [ ] **Backend** — public Render URL + working `/docs` Swagger; repo `/backend` with `requirements.txt`, `.env.example`, `alembic/`.
- [ ] **DB** — `docs/schema.dbml` diagram + `models.py` linked from README.
- [ ] Repo **public**, `/frontend` + `/backend` + root `README.md`. Test every link in incognito.

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Groq free-tier rate limits during demo | Cache the last summary; keep prompts short; 8b for classify. Record the video when limits are fresh. |
| Render free service cold-start (spins down) | Hit the URL ~1 min before recording; mention it's free-tier in the deck. |
| LangGraph checkpointer dev/prod split bugs | Abstract behind one `get_checkpointer()`; test prod Postgres path before recording. |
| Weekly review needs Sunday | Manual "Run weekly review now" button (same code) — never block the demo on a cron. |
| Scope creep eating the deadline | §6 triage is law: MUST first, deploy, then SHOULD, then stretch. Deck + video are deliverables too — budget half a day. |
| Data lost on restart kills the "memory" story | Postgres in prod; never SQLite file in prod. |

## 11. Definition of done

- [ ] A grader, in a fresh incognito window, completes: sign up → morning check-in → see classified tasks → evening check-in → get an EOD summary + tomorrow's plan → view the week. **Live.**
- [ ] Backend `/docs` Swagger works; repo matches the live app (honest build).
- [ ] Weekly review produces a real pattern paragraph.
- [ ] Video, deck, both URLs, repo hygiene all submitted; every link incognito-verified.
