"""One-shot end-to-end smoke test against the real app + real Groq (reads .env).

Run from backend/:  .venv\\Scripts\\python.exe smoke.py

Exercises the full grader flow: signup -> morning check-in (real LLM classify)
-> task board -> evening check-in (real LLM summary + plan) -> weekly review.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app


def show(title, r):
    print(f"\n--- {title}  ->  HTTP {r.status_code} ---")
    try:
        body = r.json()
        if isinstance(body, dict) and "message" in body:
            print("message:", body.get("message"))
        else:
            print(body)
    except Exception:
        print(r.text)
    return r


def main() -> None:
    email = f"founder_{uuid.uuid4().hex[:8]}@example.com"
    pw = "capstone123"

    # Context manager fires FastAPI startup -> init_db() creates the tables.
    with TestClient(app) as c:
        assert c.get("/").json()["status"] == "ok", "health failed"

        r = show("signup", c.post("/auth/signup", json={"email": email, "password": pw, "name": "Founder"}))
        assert r.status_code in (200, 201), r.text
        token = r.json()["access_token"]
        H = {"Authorization": f"Bearer {token}"}

        show("GET /auth/me", c.get("/auth/me", headers=H))

        morning = (
            "Finish the capstone slide deck, call the dentist to reschedule, "
            "gym at 6pm, and read 20 pages of the SQLAlchemy docs."
        )
        r = show("morning check-in (real Groq classify)", c.post("/checkin/morning", json={"raw_text": morning}, headers=H))
        assert r.status_code == 200, r.text
        planned = r.json().get("planned_tasks", [])
        print(f"\n[classified {len(planned)} tasks]")
        for t in planned:
            print(f"  - {t['title']}   [{t['category']}/{t['priority']}]")

        r = c.get("/tasks", headers=H)
        pending = [t["id"] for t in r.json() if t["status"] == "pending"]
        print(f"\n[/tasks returned {len(r.json())} tasks, {len(pending)} pending]")

        evening = (
            "Knocked out the deck and the dentist call. Skipped the gym and "
            "ran out of time on the reading."
        )
        r = show(
            "evening check-in (real Groq summary + plan)",
            c.post("/checkin/evening", json={"raw_text": evening, "completed_task_ids": pending[:2]}, headers=H),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        print("\n[EOD SUMMARY]\n ", body.get("eod_summary"))
        print("\n[TOMORROW PLAN]\n ", body.get("tomorrow_plan"))
        print("\n[TOMORROW TASKS]")
        for t in body.get("tomorrow_tasks", []):
            print(f"  - {t['title']}   [{t['category']}/{t['priority']}]")

        show("weekly review (real Groq)", c.post("/review/weekly", headers=H))
        rs = c.get("/summaries", headers=H)
        rv = c.get("/reviews", headers=H)
        print(f"\n[/summaries -> {len(rs.json())}]  [/reviews -> {len(rv.json())}]")

    print("\n\n==== SMOKE PASSED ====")


if __name__ == "__main__":
    main()
