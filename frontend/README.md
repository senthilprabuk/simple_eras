# ERAS clinical dashboard

Next.js front end for the post-operative remote monitoring service.

| Route | Who | What |
|---|---|---|
| `/login` | Clinicians | Sign in. The session lives in `sessionStorage` and ends when the tab closes. |
| `/` | Clinicians | Risk queue: unresolved alerts by severity, KPIs, acknowledge and resolve. |
| `/checkin` | Patients (prototype) | Daily check-in built from the approved ruleset. Unauthenticated until patient sign-in exists. |

## Running

The backend must be running first; see `docs/4-BACKEND-IMPLEMENTATION-GUIDE.md`.

```bash
cp .env.example .env.local   # only if the API is not at http://localhost:8000
npm install
npm run dev
```

## Checks

```bash
npm test            # unit tests (vitest)
npm run lint
npx tsc --noEmit
npm run build
```

Fonts are self-hosted: Inter through `next/font` and icons from the `material-symbols`
package, so clinical workstations make no requests to Google.
