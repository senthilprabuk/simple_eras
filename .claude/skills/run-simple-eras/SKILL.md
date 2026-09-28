---
name: run-simple-eras
description: Start, stop, build, test and drive the ERAS remote-monitoring app on Windows (FastAPI backend, Next.js clinician dashboard, patient check-in page). Use when asked to run or start simple_eras, sign in to the dashboard, open or submit a patient check-in link, take a screenshot of a page, smoke-test the API, build or reset the demo database, or run its tests.
---

ERAS is a FastAPI backend (`:8000`) and a Next.js frontend (`:3000`) on a Neon Postgres
database. Start and stop both with `.claude/skills/run-simple-eras/app.sh`, check the API
with `app.sh smoke`, and drive the UI with `.claude/skills/run-simple-eras/driver.mjs`, a
dependency-free headless-Edge driver fed a script on stdin.

Windows only: run everything from Git Bash. Verified on Windows 11 with Python 3.13, Node 24
and the Edge that ships with Windows. All paths are relative to the repository root.

## Prerequisites

- `backend/.venv`, a Python 3.10+ virtualenv (the scripts use `backend/.venv/Scripts/python.exe`).
- Node 20+ (Node 22+ for the driver's built-in WebSocket).
- Microsoft Edge or Chrome. The driver finds Edge in `C:/Program Files (x86)/Microsoft/Edge/`; set `BROWSER=<path>` otherwise.
- `backend/.env` with at least `DATABASE_URL` (Neon pooler URL) and `JWT_SECRET_KEY` (32+ characters); see `backend/.env.example`.
  Add `CHECKIN_SIMULATOR_ENABLED=true` to use the `/checkin` episode picker on demo data; the flows
  below use check-in links and work without it.

## Setup

```bash
cd backend && .venv/Scripts/python.exe -m pip install -q -r requirements.txt && cd ..
cd frontend && npm ci && cd ..
```

A brand-new, empty database: build the schema, reference data, FX-* demo patients and demo
logins (refuses a database that already has the schema; upgrade those with `db/migrate.py`):

```bash
.claude/skills/run-simple-eras/app.sh db-build
.claude/skills/run-simple-eras/app.sh db-status     # every migration through 013 "applied"
```

## Run (agent path)

```bash
.claude/skills/run-simple-eras/app.sh start    # ~10s; both servers keep running after the shell exits
.claude/skills/run-simple-eras/app.sh smoke    # /health, then 200s for alerts, patients, templates, whatsapp/account
```

Drive the dashboard: sign in, wait for real data, open a page, screenshot.

```bash
node .claude/skills/run-simple-eras/driver.mjs <<'EOF'
nav http://localhost:3000/login
wait-for input[autocomplete=username]
fill input[autocomplete=username] admin@stmarys.org
fill input[autocomplete=current-password] password123
click button[type=submit]
wait-for text=Prioritized clinical queue
wait-gone text=Loading
screenshot dashboard
nav http://localhost:3000/settings
wait-for text=WhatsApp Business Number
wait-gone text=Loading
scroll-to text=WhatsApp Business Number
screenshot whatsapp-settings
console
EOF
```

Drive the patient check-in through a WhatsApp link (no sign-in; `app.sh link <MRN>` mints
today's link). FX-06 is the only seeded patient who has not checked in today:

```bash
LINK=$(.claude/skills/run-simple-eras/app.sh link FX-06)
node .claude/skills/run-simple-eras/driver.mjs <<EOF
viewport 430x900
nav $LINK
wait-for text=Today's check-in is ready
click text=Start today's check-in
wait-for text=Step 1 of 5
click text=2
click text=Continue
wait-for text=Step 2 of 5
eval [...document.querySelectorAll('button')].filter(b => b.innerText.trim() === 'No').map(b => b.click()).length
click text=Continue
wait-for text=Step 3 of 5
click text=Continue
wait-for text=Step 4 of 5
click text=Continue
wait-for text=Step 5 of 5
click text=Send to my care team
wait-for text=Reference
screenshot checkin-done
console
EOF
.claude/skills/run-simple-eras/app.sh reset-demo   # undo the submission: FX-* patients back to day 21
```

Screenshots land in `%TEMP%\run-simple-eras\shots\` (`01-dashboard.png`, ...; the driver
prints each path). A failing command saves `NN-failure.png` there and exits 1. Server logs:
`app.sh logs [lines]`, files in `%TEMP%\run-simple-eras\`.

| driver command | what it does |
|---|---|
| `nav <url>` | open a page, wait for the load event |
| `wait-for text=<t>` / `wait-for <css>` | wait up to 30s for visible text or an element |
| `wait-gone text=<t>` / `wait-gone <css>` | wait up to 30s until it disappears |
| `fill <css> <text>` | focus and type; React sees the change |
| `click text=<t>` / `click <css>` | click; `text=` prefers an exact match |
| `scroll-to text=<t>` / `scroll-to <css>` | bring it into view before a screenshot |
| `viewport <w>x<h>` | resize, e.g. `430x900` for the phone layout |
| `text [n]` / `eval <js>` | print visible text / a JS value |
| `screenshot [name]` | PNG of the view, after animations settle |
| `console` | console errors, exceptions and failed loads so far |

| app.sh command | what it does |
|---|---|
| `start` / `stop` / `status` | launch both servers / kill the :8000 and :3000 listeners / show them |
| `smoke` | API sign-in as the demo superadmin and four authenticated reads |
| `link [MRN]` | today's check-in link for a patient (default FX-01) |
| `logs [n]` | tail both server logs |
| `db-build` / `db-status` / `reset-demo` | build an empty DB / list migrations / rebuild the demo patients |

Demo logins, password `password123`: `admin@stmarys.org` (superadmin: WhatsApp settings,
templates, clinicians), `nurse.sarah@stmarys.org` and `dr.mehta@stmarys.org` (clinicians),
`appadmin@eras.local` (platform admin, opens `/app_admin`).

```bash
.claude/skills/run-simple-eras/app.sh stop
```

## Run (human path)

Two terminals, Ctrl-C to stop; open http://localhost:3000.

```bash
cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd frontend && npm run dev -- --port 3000
```

## Test

```bash
cd backend && .venv/Scripts/python.exe -m pytest -q tests/test_whatsapp_checkin.py
cd backend && .venv/Scripts/python.exe -m pytest -q      # 289 tests; ~16 min against Neon
cd frontend && npx vitest run && npx tsc --noEmit -p .   # 95 tests
```

The backend suite builds a throwaway database next to the one in `backend/.env` (the role
needs CREATEDB, which `neondb_owner` has), runs, and drops it.

## Gotchas

- **`GET /` on the backend is a 404.** Poll `/health` for readiness; `app.sh start` does.
- **A sign-in lives in one tab's sessionStorage.** A one-shot `msedge --headless --screenshot`
  can capture only signed-out pages (`/login`, a check-in link). Anything behind sign-in needs
  `driver.mjs`, which keeps one tab for the whole script.
- **The dashboard shell renders before its data.** `wait-for text=Settings` passes while every
  panel still says "Loading…"; add `wait-gone text=Loading` before a screenshot.
- **Wait text is visible text and case-sensitive.** The check-in overview lists "Temperature",
  but the step says "What is your temperature?", so `wait-for text=Temperature` times out after
  the click. Wait on `Step N of 5` instead.
- **Substring clicks hit the wrong button** on the 0-10 pain scale ("1" is inside "10"), so
  `click text=` tries an exact match first. Step 2's five Yes/No pairs share labels; the `eval`
  above answers all of them.
- **A screenshot taken during the check-in's slide between screens shows both screens stacked.**
  `screenshot` now waits for finite animations to finish; spinners are ignored.
- **Screenshots show the view only.** The WhatsApp section of `/settings` is below the fold:
  `scroll-to` it first.
- **After seeding, every active FX patient but FX-06 has already checked in today.** Their link
  opens "You've already checked in today" with "Check in again", which supersedes the fixture's
  check-in. Any submission changes the demo data; `app.sh reset-demo` rebuilds it. FX-10 has no
  active episode.
- **`WHATSAPP_PROVIDER` unset means `disabled`.** A check-in reply stays queued, the done screen
  says the WhatsApp message "will follow shortly", and the backend logs a waiting-messages
  warning every minute. Put `WHATSAPP_PROVIDER=log` in `backend/.env` and restart to see them
  "sent" in the log.
- **Check-in links carry the token after `#`** (`/checkin#token=...`), which the browser never sends
  to a server, and the page sends it to the API in an `X-Checkin-Token` header. Only older
  `?token=` links reach a request log, where the backend redacts them. The driver prints `token=…`.
- **With `CHECKIN_SIMULATOR_ENABLED` unset, `/checkin` without a link shows "Open your check-in from
  WhatsApp"**, and `/api/v1/checkin/episodes` answers 404. That is the safe default, not a fault.
- **Labels styled in capitals are capitals to `wait-for`.** The driver matches `innerText`, which
  applies CSS `text-transform`: the hospital page's "Emergency number" label reads "EMERGENCY
  NUMBER". Wait on the value underneath instead.
- **`npm ci` warns `unrs-resolver@... (postinstall ...)` is "not yet covered by allowScripts"**
  (npm 11 skips unapproved install scripts). Harmless here: the dev server, vitest, tsc and
  eslint all work without it.
- **Git Bash has no `lsof`.** `app.sh stop` reads `netstat -ano` and runs `taskkill //F //T //PID`
  (doubled slashes, or Git Bash rewrites them into paths).

## Troubleshooting

- **`psycopg.OperationalError: ... password authentication failed for user 'neondb_owner'`**
  (every test errors in setup): the Neon password or endpoint in `backend/.env` changed. Copy the
  current connection string from the Neon console into `DATABASE_URL`.
- **`ModuleNotFoundError: No module named 'qrcode'`**: the venv predates the WhatsApp QR code;
  run the Setup `pip install -r requirements.txt`.
- **`This database has no schema. Build it from db/schema/ first`** from `app.sh db-status`: an
  empty database; run `app.sh db-build`.
- **`No active episode for MRN FX-10`** from `app.sh link`: pick another MRN (FX-01 to FX-15,
  except FX-10).
- **Driver `FAILED: timed out after 30s waiting for ...`**: open the `NN-failure.png` it names;
  usually the wait text differs in case or wording from what is on screen.
