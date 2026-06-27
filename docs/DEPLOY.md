# Deploy AltSpace (free tier, two public URLs)

This guide takes you from a clean repo to two live, incognito-verifiable URLs:

- **Backend** — FastAPI on Render (+ free Postgres). Swagger at `<render-url>/docs`.
- **Frontend** — Streamlit on Streamlit Community Cloud.

Everything here is **free tier**. Total time: ~20 minutes (most of it Render's
first build).

---

## Prerequisites

- A [GitHub](https://github.com) account.
- A [Render](https://render.com) account (sign in with GitHub).
- A [Streamlit Community Cloud](https://share.streamlit.io) account (sign in with GitHub).
- A free [Groq API key](https://console.groq.com) — `GROQ_API_KEY`.
- A long random `JWT_SECRET` (≥32 chars). Generate one:
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```

---

## Step 1 — Push a public GitHub repo

The pre-flight checklist requires `/frontend`, `/backend`, and a root
`README.md` in a **public** repo.

```bash
cd "altspace-productivity-agent"
git init
git add .
git commit -m "AltSpace v0 — AI chief of staff"
# create an EMPTY public repo on github.com first, then:
git remote add origin https://github.com/<you>/altspace-productivity-agent.git
git branch -M main
git push -u origin main
```

Confirm `render.yaml` is at the repo root and `backend/alembic/versions/0001_initial.py`
is committed (it builds the schema on first deploy).

> **Never commit secrets.** `backend/.gitignore` excludes `.env` and the local
> SQLite file. Only `.env.example` (no real keys) is committed.

---

## Step 2 — Deploy the backend on Render (Blueprint)

The repo's `render.yaml` provisions a web service **and** a free Postgres in one
shot.

1. Render dashboard → **New +** → **Blueprint**.
2. Connect your GitHub and pick the `altspace-productivity-agent` repo.
3. Render reads `render.yaml` and shows two resources to create:
   - `altspace-api` — the FastAPI web service (rootDir `backend`).
   - `altspace-db` — the free Postgres database.
4. It prompts for the `sync: false` env vars. Set:
   - **`GROQ_API_KEY`** → your Groq key.
   - **`JWT_SECRET`** → the random string from Prerequisites.
   - **`FRONTEND_ORIGIN`** → put `http://localhost:8501` for now; you'll
     replace it with the real Streamlit URL in Step 4.
5. Click **Apply**. Render builds:
   - `pip install -r requirements.txt`
   - then the start command runs `alembic upgrade head` (creates all 5 tables
     from `0001_initial.py`) and boots Uvicorn on `$PORT`.
6. `DATABASE_URL` is injected automatically from `altspace-db` — do not set it
   by hand.

When the deploy goes green, open **`https://altspace-api.onrender.com/docs`**
(your URL will differ). The Swagger UI should list `/auth`, `/tasks`,
`/checkin`, `/review`. **That is the graded backend URL.**

> **Postgres URL normalization.** Render's managed Postgres connection string
> begins with `postgres://`, but SQLAlchemy + psycopg2 expect `postgresql://`.
> `app/database.py` normalizes this prefix at startup, so no manual edit is
> needed. (If you ever see `Can't load plugin: sqlalchemy.dialects:postgres`,
> that normalization is missing — see the seam note at the bottom.)

> **Free-tier cold start.** The free web service spins down after inactivity and
> takes ~30–60s to wake. Hit the URL ~1 minute before recording your demo.

---

## Step 3 — Deploy the frontend on Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**.
2. Pick the same GitHub repo and branch `main`.
3. **Main file path:** `frontend/streamlit_app.py`.
4. **Advanced settings → Secrets** — add the backend URL:
   ```toml
   API_BASE_URL = "https://altspace-api.onrender.com"
   ```
   (Use *your* Render URL, no trailing slash.)
5. **Deploy.** Streamlit gives you a public URL like
   `https://<you>-altspace.streamlit.app`. **That is the graded frontend URL.**

---

## Step 4 — Close the CORS loop

Now that the Streamlit URL exists, point the backend's CORS at it:

1. Render → `altspace-api` → **Environment** → edit **`FRONTEND_ORIGIN`** to
   your Streamlit URL (e.g. `https://<you>-altspace.streamlit.app`, no trailing
   slash).
2. Save. Render redeploys automatically.

Without this, the browser blocks the frontend's requests with a CORS error.

---

## Step 5 — Incognito verification (the grader's path)

Open a **fresh incognito window** (no cached login) and confirm:

- [ ] `<render-url>/docs` — Swagger loads and lists all four routers.
- [ ] `<streamlit-url>` — the app loads (no blank screen / connection error).
- [ ] **Sign up** with a new email → you land logged in.
- [ ] **Morning check-in** — type a free-text brain-dump → tasks appear,
      classified by category/priority.
- [ ] **Task board** — the classified tasks render; you can mark them.
- [ ] **Evening check-in** — mark some done → you get an EOD summary +
      tomorrow's plan.
- [ ] **This week** — daily summaries show.
- [ ] **Run weekly review** — produces a real patterns paragraph.
- [ ] **Refresh / re-login** — your data is still there (Postgres durability).

If all boxes check in incognito, the deploy is grader-ready.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Render build fails on `pip install` | Confirm `backend/requirements.txt` is committed and `rootDir: backend` is set (it is, in `render.yaml`). |
| Backend boots but `/docs` 500s | Check the start command ran `alembic upgrade head`. View Render logs for the migration line. |
| `sqlalchemy.dialects:postgres` plugin error | The `postgres://` → `postgresql://` normalization in `app/database.py` is missing (see seam note). |
| Frontend shows CORS / network error | `FRONTEND_ORIGIN` on Render must equal the Streamlit URL exactly (no trailing slash). Redeploy after editing. |
| Streamlit "connection refused" | `API_BASE_URL` secret is wrong or has a trailing slash. |
| Login works, then 401 on every call | The frontend isn't sending `Authorization: Bearer <token>`. Check `frontend/lib/api.py`. |
| First request after idle is slow | Free-tier cold start (~30–60s). Wake the backend before demoing. |

---

## Seam note for the backend authors

`render.yaml` and this guide assume **`app/database.py` normalizes the DB URL
prefix** so Render's `postgres://...` works with SQLAlchemy:

```python
url = settings.DATABASE_URL
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)
engine = create_engine(url, ...)
```

If the foundation seam didn't include this, add it — it's the single most
common Render + SQLAlchemy deploy break. The same `url` should feed the
LangGraph `PostgresSaver` so the agent checkpointer points at the same DB.
