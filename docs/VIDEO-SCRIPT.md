# Video Script — AltSpace (under 5 minutes)

> Screen recording (Loom / OBS). Target **~4:20** to stay safely under the 5-min cap.
> Record the demo in **one clean take** against the **live deployed app** (incognito window).
> Hit the Render URL ~1 min before recording so the free-tier backend is warm (no cold-start lag).
>
> **Demo data to use** (gives varied categories — looks great on screen):
> - Email at signup: `sunny@marakana.in` (avoid `.test` / `.local` / `.example` — the validator rejects reserved TLDs)
> - Morning brain-dump: *"Finish the capstone deck, push the backend to Render, call mom, gym at 6, read 20 pages of the LangGraph docs, reply to the TA's email."*
> - Evening recap: *"Shipped the deck and pushed to Render. Skipped the gym again and didn't get to the reading."*

| Time | On screen | What you say (voiceover) |
|---|---|---|
| **0:00–0:25** | Title slide or the app's landing page. | "Most productivity apps are glorified to-do lists — you still have to remember what's due, decide what matters, and write your own recap. The real problem isn't tasks. It's memory and prioritization. So I built **AltSpace** — not a to-do list, an AI *chief of staff* you check in with twice a day." |
| **0:25–0:50** | The landing page → click **Sign up**, fill name/email/password, **Create account**. | "It's a stateful agent that holds your context across days. Let me show you. I sign up — JWT auth, real backend — and I'm dropped straight into my workspace." |
| **0:50–1:45** | **Morning** tab. Paste the brain-dump. Click **Run morning check-in**. Wait for the result. Point at the classified task cards + the AltSpace message. | "Morning check-in: I just brain-dump everything on my plate in plain English. AltSpace reads it, and — this is a real LangGraph agent calling a Groq model — it classifies each item: *work, personal, health, learning*, with a priority, and flags anything that slipped from before. No forms. I talk; it organizes." |
| **1:45–2:10** | **Tasks** tab. Show the board grouped Pending / Slipped / Done. Click **Done** on one task. | "Everything lands on a board, grouped by status, colored by category. I can complete, reopen, or add tasks directly. This is the persistent state — it's in Postgres, it survives across days." |
| **2:10–3:05** | **Evening** tab. Multiselect the 2–3 tasks you finished. Type the recap. Click **Run evening check-in**. Point at the **EOD summary**, **tomorrow's plan**, and **queued tasks**. | "Evening check-in: I tick off what I actually finished and recap the day. AltSpace writes my end-of-day summary — what got done, what slipped — *and* plans tomorrow, carrying the unfinished work forward as new tasks. That's the part I'd normally never do myself." |
| **3:05–3:25** | **This Week** tab. Show the daily summaries side by side. | "Every evening adds a card here, so I get my whole week at a glance." |
| **3:25–3:55** | **Weekly Review** tab. Click **Run weekly review now**. Read the patterns paragraph aloud (or point). | "And weekly, it steps back and tells me the *patterns* — what I keep pushing, where my time actually goes. Here it caught that I keep skipping the gym and that my learning tasks are slipping. That's the memory paying off." |
| **3:55–4:15** | Open the **backend `/docs`** Swagger in a new tab (show the real API routes). Then flash the **GitHub repo** (show /frontend, /backend, the LangGraph agent folder). | "Quick proof it's real: this is the live FastAPI backend — auth, tasks, check-in, review, all documented. And the full source is public — FastAPI, SQLAlchemy, Alembic migrations, and the LangGraph state machine that drives the whole thing." |
| **4:15–4:25** | Back to the app / title. | "That's AltSpace v0 — an AI you *work with*, not a search box. The vision from here: a whole team of these agents, a chief that delegates. But even one, today, remembers your week so you don't have to. Thanks for watching." |

## Recording tips
- **One take, no dead air.** Pre-type the brain-dump into a notes file so you can paste instantly.
- **Warm the backend** first (open `/docs` once) so the morning check-in returns in ~2s on camera.
- If a Groq call is slow on camera, the spinner says *"AltSpace is reading your day…"* — that reads as intentional, not broken.
- Keep the cursor moving and narrate every click. Graders watch for *"can the core flow be completed live"* — show it unbroken, start to finish.
- End under 5:00. If you run long, trim the Tasks-tab beat (2:10) — it's the most cuttable.
