# ERAS clinical dashboard

Next.js front end for the post-operative remote monitoring service.

| Route | Who | What |
|---|---|---|
| `/login` | Clinicians | Sign in. The session lives in `sessionStorage` and ends when the tab closes. |
| `/` | Clinicians | Risk queue: unresolved alerts by severity, KPIs, acknowledge and resolve. |
| `/patients` | Clinicians | Monitored patients with adherence and their most urgent open alert. |
| `/patients/[episodeId]` | Clinicians | Drilldown: temperature, pain and step trends against the ruleset's scoring thresholds, and red-flag symptoms by day. |
| `/alerts` | Clinicians | Alert history in every state, with who acknowledged and resolved each and how quickly. |
| `/enrollment` | Clinicians | Enroll a patient with discharge baseline and consent. |
| `/rulesets` | Clinicians | The approved scoring rules, read-only: when each question is asked and scored. |
| `/hospitals` | Clinicians | Your hospital's profile and activity; superadmins edit the SLA and timezone. |
| `/templates` | Clinicians | WhatsApp wording per language, with preview; superadmins edit. Not sent anywhere yet. |
| `/reports` | Clinicians | Alerts per week by tier, SLA compliance, check-in adherence, outcomes. |
| `/settings` | Clinicians | Change your password; superadmins manage clinician accounts. |
| `/checkin` | Patients (prototype) | Daily check-in built from the approved ruleset. Unauthenticated until patient sign-in exists. |

Every clinician route lives in the `src/app/(clinical)` route group, whose layout holds the session check and sidebar.

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
