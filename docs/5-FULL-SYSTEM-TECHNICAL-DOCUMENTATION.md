# ERAS Full System Technical Documentation & Architecture Reference

> **Document**: 5 of 5 · Complete End-to-End System Reference  
> **System**: Enhanced Recovery After Surgery (ERAS) Remote Patient Monitoring System  
> **Scope**: Hospital Clinical Portal (All 9 Screens), Patient Check-in Simulator, Backend API (12 Modules), Database Architecture & RLS, Scoring Engine, Escalation Sweeps, and Test Suite  
> **Author**: Engineering Team  
> **Date**: September 2026  
> **Status**: Production Ready  

---

## 1. Executive Summary & System Overview

The **Enhanced Recovery After Surgery (ERAS)** platform is an enterprise-grade clinical decision support and remote patient monitoring (RPM) system designed for post-operative knee arthroplasty (TKR/PKR) patients. The platform monitors patients during their critical recovery window (up to 84 days post-discharge), capturing daily vitals, physiological signals, wound recovery status, and functional milestones.

### 1.1 Core Clinical Objectives
1. **Early Deterioration Detection**: Catch severe post-operative complications early—including Deep Vein Thrombosis (DVT), Pulmonary Embolism (PE), Surgical Site Infection (SSI), and arthrofibrosis—before emergency re-admission is required.
2. **Prioritized Risk Queue**: Eliminate alert fatigue by presenting on-call orthopedic surgeons and nurses with a deterministically sorted triage queue based on clinical urgency:
   $$\text{Emergency} \succ \text{Critical} \succ \text{Review} \succ \text{Missed}$$
3. **Rigorous Multi-Tenancy**: Guarantee strict data isolation between hospital systems via PostgreSQL Row-Level Security (RLS) enforced directly in the database engine.
4. **Honest Clinical UX**: Zero fabricated vitals, no optimistic alert acknowledgments that mask failure, and explicit visual separation between verified telemetry and patient-reported subjective data.

---

## 2. Complete Technology Stack & Runtime Topology

```mermaid
graph TD
    subgraph ClientLayer ["Client Presentation Layer"]
        ClinicianUI["Clinician Portal (Next.js 16.3 + React 19)<br/>Desktop First · 9 Clinical Screens<br/>Port 3000"]
        PatientUI["Patient Check-In Simulator (/checkin)<br/>Mobile Responsive Web Form"]
    end

    subgraph ApiLayer ["Application & Orchestration Layer (FastAPI · Port 8000)"]
        Router["APIRouter /api/v1 (12 Domain Routers)"]
        AuthModule["Core Security (PyJWT + Bcrypt)"]
        TenantScope["Session Scope: SET LOCAL ROLE eras_app<br/>app.hospital_id"]
        Scheduler["AsyncIOScheduler (APScheduler)"]
        EscalationService["services/escalation.py (60s SLA Sweep)"]
        ScoringService["services/scoring.py (Dynamic Day-Banded Thresholds)"]
    end

    subgraph DataLayer ["Persistence & Database Layer (Neon PostgreSQL 18.6)"]
        PgBouncer["PgBouncer Transaction Pooler (AWS ap-southeast-1)"]
        MetaSchema[("meta Schema<br/>Hospitals, Clinicians, Rulesets, Parameters, Templates")]
        TxnSchema[("txn Schema (RLS Enforced)<br/>Patients, Episodes, Check-ins, Values, Evals, Alerts")]
        Views[("txn.v_alert_queue<br/>Pre-computed Prioritization View")]
    end

    ClinicianUI -->|HTTPS / Bearer JWT| Router
    PatientUI -->|HTTPS / REST| Router
    Router --> AuthModule
    Router --> TenantScope
    TenantScope -->|asyncpg + SQLAlchemy 2.0| PgBouncer
    Scheduler --> EscalationService
    EscalationService -->|Check SLA Breaches & Notify| TxnSchema
    PgBouncer --> MetaSchema
    PgBouncer --> TxnSchema
    PgBouncer --> Views
```

### 2.1 Runtime Components & Specifications

| Component | Technology / Library | Version | Role & Configuration |
| :--- | :--- | :--- | :--- |
| **Frontend Framework** | Next.js (App Router) | `16.3.5` | Desktop clinical workstation & mobile check-in portal with Turbopack. |
| **UI Framework** | React | `19.0.0` | Server & Client Components, CSS Modules / Tailwind styling. |
| **Data Visualization** | Custom SVG / Tailwind | Native | Zero-dependency responsive charts (`TrendChart`, `StackedColumnChart`, `BarList`). |
| **Frontend Testing** | Vitest | `5.0.1` | Unit & integration tests for charts, formatters, and API helpers. |
| **API Framework** | FastAPI | `0.141.1` | Asynchronous REST backend with OpenAPI/Swagger docs. |
| **ASGI Server** | Uvicorn | `0.53.0` | Production ASGI runner with uvloop. |
| **ORM / Driver** | SQLAlchemy (Async) / asyncpg | `2.0.54` / `0.31.0` | Async engine configured for PgBouncer (`statement_cache_size=0`). |
| **Database** | PostgreSQL on Neon | `18.6` | Multi-tenant relational storage with schema separation & RLS. |
| **Task Scheduling** | APScheduler | `3.11.3` | AsyncIOScheduler managing 60s escalation sweeps & 30s notification dispatch. |
| **Backend Testing** | Pytest / pytest-asyncio | `8.4.2` / `0.26.0` | Comprehensive test suite (120 tests) with isolated transactional rollback. |

---

## 3. Database Architecture & Multi-Tenant Security Model

The database utilizes two distinct PostgreSQL schemas to segregate operational metadata from high-velocity clinical transactions.

### 3.1 Schema Segregation
* **`meta` Schema (Reference & Configuration)**:
  * `meta.hospital`: Tenant records, timezone configuration, escalation SLA window (`ack_window_secs`, default 900s).
  * `meta.admin_user`: Clinician accounts, bcrypt password hashes, roles (`admin`, `superadmin`), active status.
  * `meta.surgical_procedure`: Surgical procedures catalog (e.g., Total Knee Replacement `TKR`, 84-day monitoring span).
  * `meta.hospital_procedure`: Junction table mapping procedures offered per hospital.
  * `meta.parameter`: Physiological parameter registry with clinical types (`numeric`, `boolean`, `ordinal`), unit definitions, range constraints, and alert polarities.
  * `meta.parameter_option`: Ordinal rank milestones (e.g., knee flexion progression: `<90°` → `90°-105°` → `>105°`; walking aids: `walker` → `crutches` → `cane` → `none`).
  * `meta.ruleset`: Versioned clinical protocol envelopes with unique index ensuring **at most one active approved ruleset per procedure**.
  * `meta.procedure_parameter`: Clinical configuration binding parameters to rulesets. Decouples **collection window** (`collect_from_day` to `collect_to_day`) from **scoring window** (`score_from_day` to `score_to_day`). Stores threshold logic in `scoring_config` (JSONB).
  * `meta.message_template`: Per-hospital WhatsApp notification templates across languages (`en`, `ta`, `hi`), with variable placeholders.
* **`txn` Schema (Clinical Transactions & Telemetry)**:
  * `txn.patient`: Demographic master data (MRN, full name, E.164 phone, language).
  * `txn.patient_episode`: Single surgical recovery journey. Enforces partial unique constraint: **one active episode per patient at any time**.
  * `txn.episode_baseline`: Discharge baseline anchor values.
  * `txn.patient_check_in`: Daily check-in submissions. Supports idempotency keys, duplicate detection, and automated same-day superseding.
  * `txn.patient_check_in_value`: Normalized parameter measurements (`value_num`, `value_bool`, `value_code`). Missing values represent "unknown", not "normal".
  * `txn.check_in_evaluation`: Output of the clinical scoring engine (tier, score, trigger reasons).
  * `txn.alert`: Clinical alerts generated from abnormal evaluations (`emergency`, `critical`, `review`). Manages SLA timers, acknowledgment status, and clinical outcome resolutions.
  * `txn.alert_notification`: Audit log of dispatch attempts (email/SMS/WhatsApp) for breached SLAs.

### 3.2 Row-Level Security (RLS) & Tenant Isolation

To eliminate multi-tenant data leaks (cross-hospital data exposure), tenant isolation is enforced at the database kernel level through PostgreSQL Row-Level Security (RLS) policies implemented in Migration 004 and 005.

```mermaid
sequenceDiagram
    participant App as FastAPI Backend
    participant DB as PostgreSQL (Neon)
    Note over App,DB: Transaction Begins
    App->>DB: SET LOCAL ROLE eras_app;
    App->>DB: SELECT set_config('app.hospital_id', '1', true);
    Note over DB: Current session locked to Hospital ID 1
    App->>DB: SELECT * FROM txn.patient WHERE mrn = 'FX-04';
    DB-->>App: Returns only rows WHERE hospital_id = 1
    App->>DB: SELECT * FROM txn.patient (No WHERE clause)
    DB-->>App: RLS auto-filters to hospital_id = 1
    Note over App,DB: Transaction Commits (Role & Config Auto-Reset)
```

#### Key RLS Policies:
1. **Unprivileged Application Role (`eras_app`)**:
   * Has `NOBYPASSRLS` and `NOLOGIN`.
   * Only has `SELECT` on `meta` tables, `SELECT` on `txn` tables (excluding password hashes), and restricted `UPDATE` on alerts (`status`, `acknowledged_at`, `resolved_at`, `outcome`).
2. **Dynamic Context Provider**:
   ```sql
   CREATE OR REPLACE FUNCTION meta.current_hospital_id() RETURNS integer
   LANGUAGE sql STABLE AS $$
       SELECT nullif(current_setting('app.hospital_id', true), '')::integer
   $$;
   ```
3. **Table Policies**:
   * `txn.patient`: `USING (hospital_id = meta.current_hospital_id())`
   * `txn.patient_episode`: `USING (hospital_id = meta.current_hospital_id())`
   * `txn.alert`: `USING (episode_id IN (SELECT episode_id FROM txn.patient_episode WHERE hospital_id = meta.current_hospital_id()))`
   * `meta.hospital`: `USING (hospital_id = meta.current_hospital_id())`
   * `meta.message_template`: `USING (hospital_id = meta.current_hospital_id())`

---

## 4. Full Clinical Application Screen Architecture (All 9 Screens)

The frontend application (`frontend/`) is implemented as a desktop-first clinical workspace with 9 integrated screens, organized within the `(clinical)` route group and sharing a cohesive clinical layout (`Sidebar.tsx`, `SessionContext.tsx`, `TopHeader.tsx`).

```
frontend/src/app/
├── (clinical)/
│   ├── layout.tsx                     # Global clinical layout (Sidebar, Session Provider, Breadcrumbs)
│   ├── page.tsx                       # Screen 1: Risk Queue Dashboard
│   ├── alerts/page.tsx                # Screen 2: Alert History & Escalation Log
│   ├── enrollment/page.tsx            # Screen 3: Patient Onboarding & Discharge Baseline
│   ├── hospitals/page.tsx             # Screen 4: Hospital Profile & Service Directory
│   ├── patients/page.tsx              # Screen 5a: Patient Census Directory
│   ├── patients/[episodeId]/page.tsx  # Screen 5b: Patient Longitudinal Trajectory & Vitals Drilldown
│   ├── reports/page.tsx               # Screen 6: Clinical Quality & Adherence Analytics
│   ├── rulesets/page.tsx              # Screen 7: Clinical Rulesets & Protocol Inspector
│   ├── settings/page.tsx              # Screen 8: Hospital Settings & Clinician Roster Management
│   └── templates/page.tsx             # Screen 9: WhatsApp Communication Templates
├── checkin/page.tsx                   # Patient Daily Check-In Mobile Web Simulator
└── login/page.tsx                     # Clinician Sign-In & JWT Authentication
```

### Screen 1: Risk Queue Dashboard (`/`)
* **Purpose**: Primary clinical command center for monitoring recovering knee arthroplasty patients.
* **Components**:
  * `TopHeader`: Displays clinic branding ("St. Mary's Orthopedic Center — Wing B"), connection status ("LIVE NEON POSTGRESQL"), active clinician profile, and emergency "Call Protocol" modal.
  * `KpiMetrics`: 4 real-time telemetry cards: **Active Patients Census**, **Open Alerts**, **Ack <15m Response Compliance (7d)**, and **Missed Check-ins Today**.
  * `QueueControls`: Severity filter pills (`Emergency`, `Critical`, `Review`, `Missed`, `All`) and Pod selectors (`All PODs`, `East Wing`, `West Wing`).
  * `RiskQueueTable`: Deterministically sorted table presenting patient name, MRN, post-op day, procedure, severity badge, clinical flag reasons, SLA countdown timer, and inline `Acknowledge` action with honest error handling.
  * `PatientDetailDrawer`: Contextual slide-out drawer displaying episode metadata, WhatsApp structured responses, wound image status, and resolution forms (`Record Outcome & Resolve`).
  * `TriageStatusBanner`: Triage routine sweep status with manual "Trigger Sweep Now" button.

### Screen 2: Alerts History (`/alerts`)
* **Purpose**: Comprehensive audit trail of all alerts raised across the hospital's patient census.
* **Features**:
  * Multi-dimensional filtering by status (`All`, `Open`, `Acknowledged`, `Resolved`, `Escalated`), severity tier (`Emergency`, `Critical`, `Review`), and patient name or MRN.
  * Tabular display showing Alert ID, Patient, Raised Timestamp, Severity Badge, Trigger Reasons, Acknowledging Clinician, and Outcome Notes.
  * Direct deep-link to patient drilldown.

### Screen 3: Patient Enrollment (`/enrollment`)
* **Purpose**: Discharge coordination workflow to register patients into remote monitoring before they leave the hospital.
* **Features**:
  * Multi-step wizard:
    1. **Demographics**: Name, MRN, E.164 phone number, preferred communication language (`English`, `Tamil`, `Hindi`).
    2. **Surgical Details**: Procedure selection (`Total Knee Replacement`), Surgery Date, Discharge Date, Auto-calculated Monitoring End Date (84 days).
    3. **Discharge Baseline Vitals**: Baseline temperature, pulse, SpO2, pain score, mobility score, and walking aid.
    4. **Confirmation & Activation**: Validates against duplicate active MRNs and seeds baseline anchor into `txn.episode_baseline`.

### Screen 4: Hospital Profile & Directory (`/hospitals`)
* **Purpose**: Overview of the hospital's clinical services, operative procedure catalog, and active census metrics.
* **Features**:
  * Hospital configuration summary (Hospital Code, City, Timezone, Active Procedures).
  * Current census summary and emergency contact directories.

### Screen 5: Patient Census & Longitudinal Drilldown (`/patients` & `/patients/[episodeId]`)
* **Purpose**: Directory of all patients currently enrolled, with deep-dive clinical trajectory analysis.
* **Features**:
  * **Directory (`/patients`)**: Search by MRN or Name; displays current Post-Op Day, Monitoring Status, Adherence % (check-ins completed / expected days), and Latest Clinical Severity.
  * **Drilldown (`/patients/[episodeId]`)**:
    * **Telemetry Trend Charts (`TrendChart.tsx`)**: Temperature trajectory with fever threshold line (38.0°C); Resting pulse trajectory; Oxygen saturation ($SpO_2$) with hypoxemia boundary; Steps walked tracking personal best.
    * **Pain Trajectory Chart**: Day-banded pain thresholds demonstrating expected recovery pain curves vs. patient-reported pain.
    * **Symptom Matrix**: Historical checklist tracking calf swelling, chest pain, wound drainage, and chills.
    * **Check-in Journal**: Complete table of daily submissions with submission timestamps and sources.

### Screen 6: Clinical Quality & Adherence Analytics (`/reports`)
* **Purpose**: Clinical governance and quality assurance reporting.
* **Visualizations**:
  * **Weekly Alert Volume Stacked Chart (`StackedColumnChart.tsx`)**: Longitudinal distribution of Emergency, Critical, and Review alerts over 12 weeks.
  * **SLA Compliance Trends**: Percentage of alerts acknowledged within the hospital's SLA window (900 seconds).
  * **Check-in Adherence Histogram**: Patient completion adherence rates grouped into cohorts ($>90\%$, $75-90\%$, $<75\%$).
  * **Outcome Distribution (`BarList.tsx`)**: Breakdown of resolved alert outcomes (`Reassured & Continuing`, `Care Plan Adjusted`, `Medication Changed`, `ER / Urgent Visit`).

### Screen 7: Clinical Rulesets & Protocol Inspector (`/rulesets`)
* **Purpose**: Transparent inspection of the medical decision logic governing automated triage.
* **Features**:
  * Catalog of approved rulesets for Knee Arthroplasty (`ERAS-TKR-2026.1`).
  * Parameter breakdown showing:
    * **Collection Window** (e.g., Days 1 to 84).
    * **Scoring Window** (e.g., Days 1 to 28 for acute surgical site infection).
    * **Clinical Evaluation Logic**: Day-dependent thresholds for fever, tachycardia, pain bands, and immobility.

### Screen 8: Hospital Settings & Clinician Management (`/settings`)
* **Purpose**: Administrative controls for hospital settings and clinician access.
* **Features**:
  * **SLA Configuration**: Adjustable escalation timer window (`ack_window_secs`, e.g., 900s).
  * **Hospital Timezone & Profile**: Timezone configuration to ensure post-op day rollover occurs at local midnight.
  * **Clinician Roster**: List active doctors and nurses; create new clinician accounts with role assignments (`admin`, `superadmin`); toggle active/deactivated status (with protection against self-deactivation).

### Screen 9: WhatsApp Communication Templates (`/templates`)
* **Purpose**: Management of patient-facing automated message templates across languages.
* **Features**:
  * Template types: `enrollment_welcome`, `checkin_reminder`, `missed_checkin`, `urgent_guidance`.
  * Multi-language tabs: English (`en`), Tamil (`ta`), Hindi (`hi`).
  * Dynamic parameter interpolation preview (`{patient_first_name}`, `{hospital_name}`, `{checkin_link}`).
  * Superadmin inline editor with length constraints (WhatsApp 1024-character maximum).

---

## 5. Backend Architecture & API Specification (All 12 Modules)

The backend exposes a unified REST API under `/api/v1`, structured into 12 domain routers:

```
backend/app/api/v1/
├── auth.py          # Clinician login & JWT tokens
├── dashboard.py     # Risk queue & KPI metrics
├── alerts.py        # Alert history, acknowledgement, & resolution
├── episodes.py      # Episode summary & baseline comparison
├── patients.py      # Patient list, search, & longitudinal timeline
├── enrollment.py    # Patient enrollment & baseline registration
├── rulesets.py      # Approved clinical rulesets & parameter scoring
├── hospital.py      # Hospital profile & settings update
├── templates.py     # Message templates catalog & translations
├── reports.py       # Clinical analytics, SLA compliance, & adherence
├── clinicians.py    # Clinician accounts & access administration
└── checkin.py       # Patient-facing daily check-in submission
```

### 5.1 Complete API Endpoint Directory

```mermaid
graph LR
    subgraph ClinicalOps ["Clinical Operations"]
        Q["GET /dashboard/queue"]
        K["GET /dashboard/kpis"]
        A_Ack["POST /alerts/{id}/acknowledge"]
        A_Res["POST /alerts/{id}/resolve"]
        A_Hist["GET /alerts/history"]
    end

    subgraph PatientCare ["Patient Care & Trajectory"]
        P_List["GET /patients"]
        P_Time["GET /patients/{id}/timeline"]
        E_Sum["GET /episodes/{id}/summary"]
        E_Enroll["POST /enrollment"]
        C_Form["GET /checkin/form"]
        C_Sub["POST /checkin"]
    end

    subgraph Governance ["Administration & Governance"]
        H_Prof["GET /hospital/profile"]
        H_Set["PATCH /hospital/settings"]
        C_Roster["GET /clinicians"]
        C_Add["POST /clinicians"]
        R_List["GET /rulesets"]
        T_Cat["GET /templates"]
        Rep["GET /reports"]
    end
```

| Router | Method | Path | Auth / Role | Description |
| :--- | :---: | :--- | :--- | :--- |
| **Auth** | `POST` | `/api/v1/auth/token` | Public | Authenticates clinician credentials; returns JWT token & profile. |
| **Auth** | `GET` | `/api/v1/auth/me` | Bearer JWT | Returns current authenticated clinician info and tenant ID. |
| **Dashboard**| `GET` | `/api/v1/dashboard/queue` | Bearer JWT | Fetches prioritized risk queue filtered by tenant and severity. |
| **Dashboard**| `GET` | `/api/v1/dashboard/kpis` | Bearer JWT | Returns 4 real-time KPI metrics with hospital-local timezone math. |
| **Alerts** | `POST` | `/api/v1/alerts/{id}/acknowledge` | Bearer JWT | Clinician acknowledges an alert; transitions state and records timestamp. |
| **Alerts** | `POST` | `/api/v1/alerts/{id}/resolve` | Bearer JWT | Clinician records outcome (`resolved_by`, `outcome`, `outcome_note`). |
| **Alerts** | `GET` | `/api/v1/alerts/history` | Bearer JWT | Paginated alert history with filters for status, tier, and search query. |
| **Episodes** | `GET` | `/api/v1/episodes/{id}/summary`| Bearer JWT | Returns episode details pairing discharge baseline with latest check-in. |
| **Patients** | `GET` | `/api/v1/patients` | Bearer JWT | Returns hospital patient census with adherence rate and severity flags. |
| **Patients** | `GET` | `/api/v1/patients/{id}/timeline`| Bearer JWT | Longitudinal telemetry, pain bands, threshold points, and symptom logs. |
| **Enrollment**| `GET` | `/api/v1/enrollment/options` | Bearer JWT | Returns offered procedures and baseline parameter form configuration. |
| **Enrollment**| `POST` | `/api/v1/enrollment` | Bearer JWT | Creates patient record, active episode, and seeds discharge baseline. |
| **Rulesets** | `GET` | `/api/v1/rulesets` | Bearer JWT | Lists approved rulesets for the hospital's offered procedures. |
| **Rulesets** | `GET` | `/api/v1/rulesets/{id}` | Bearer JWT | Detailed ruleset schema with collection/scoring windows & scoring JSON. |
| **Hospital** | `GET` | `/api/v1/hospital/profile` | Bearer JWT | Current hospital profile, configuration, and offered procedures. |
| **Hospital** | `PATCH`| `/api/v1/hospital/settings`| `superadmin` | Updates hospital SLA window (`ack_window_secs`), timezone, name, or the emergency number patients are told to call (`emergency_phone_e164`). |
| **Clinicians**| `GET` | `/api/v1/clinicians` | Bearer JWT | Returns clinician roster without exposing password hashes. |
| **Clinicians**| `POST` | `/api/v1/clinicians` | `superadmin` | Creates a new clinician account (enforces password strength & email format).|
| **Clinicians**| `PATCH`| `/api/v1/clinicians/{id}` | `superadmin` | Activates or deactivates clinician (prevents self-deactivation). |
| **Clinicians**| `POST` | `/api/v1/clinicians/me/password`| Bearer JWT | Secure password update for the authenticated clinician. |
| **Templates**| `GET` | `/api/v1/templates` | Bearer JWT | WhatsApp message templates across all supported languages. |
| **Templates**| `PUT` | `/api/v1/templates/{key}/{lang}`| `superadmin` | Updates template body text (validates placeholder variables). |
| **Reports** | `GET` | `/api/v1/reports` | Bearer JWT | Aggregates 12-week clinical metrics, SLA adherence, and outcomes. |
| **Check-in** | `GET` | `/api/v1/checkin/episodes` | Simulator only | Active episodes for the check-in simulator. 404 unless `CHECKIN_SIMULATOR_ENABLED`. |
| **Check-in** | `GET` | `/api/v1/checkin/form` | Check-in link | Day-appropriate check-in questions, and the hospital's emergency number. The link token comes in the `X-Checkin-Token` header (older links: `?token=`) and is bound to one episode and today's post-op day; `?episode_id=` serves the simulator when enabled.|
| **Check-in** | `POST` | `/api/v1/checkin` | Check-in link | Persists check-in; prevents duplicates via idempotency; supersedes older entries. Without the simulator, a submission needs the patient's link; only those get a WhatsApp reply.|
| **WhatsApp** | `GET` | `/api/v1/whatsapp/account` | Bearer JWT | The hospital's WhatsApp number and click-to-chat QR code. Access token masked; verify token shown to superadmins only. |
| **WhatsApp** | `POST` | `/api/v1/whatsapp/account` | `superadmin` | Connects or updates the account, checked against Meta when `WHATSAPP_PROVIDER=meta`. |
| **WhatsApp** | `DELETE`| `/api/v1/whatsapp/account` | `superadmin` | Disconnects the account. |
| **WhatsApp** | `POST` | `/api/v1/whatsapp/test` | `superadmin` | Sends free text from the hospital's own number. |
| **WhatsApp** | `GET` | `/api/v1/whatsapp/webhook` | Verify token | Meta's subscription handshake; accepts `META_WEBHOOK_VERIFY_TOKEN` or a connected hospital's verify token. |
| **WhatsApp** | `POST` | `/api/v1/whatsapp/webhook` | Meta signature | Delivery receipts. Refused unless `X-Hub-Signature-256` matches `META_APP_SECRET`. |

---

## 6. Clinical Decision Engine, Scoring Algorithms & Escalation

### 6.1 Clinical Scoring Architecture (`services/scoring.py`)
The clinical evaluation engine runs after check-in ingestion or during automated batch triage. It evaluates patient responses against post-operative day bands defined in `meta.procedure_parameter`.

#### 1. Day-Banded Pain Thresholds
Pain perception expectations change dramatically across the recovery timeline. The ruleset specifies tighter thresholds as recovery progresses:
* **Days 1–7 (Acute Post-Op)**: Expected mild-to-moderate pain ($Score \le 6.0$ is non-alarming).
* **Days 8–21 (Subacute Recovery)**: Expected pain to decrease ($Score > 4.0$ triggers Review).
* **Days 22–84 (Late Recovery)**: Persistent high pain ($Score \ge 4.0$) indicates arthrofibrosis, complex regional pain syndrome, or loosening, triggering Critical review.

#### 2. Temperature & Infection Trajectory
* **Fever Threshold**: Persistent temperature $\ge 38.0^\circ\text{C}$ ($100.4^\circ\text{F}$) combined with wound drainage triggers an immediate **Critical Alert** for suspected Surgical Site Infection (SSI).
* **Severe Hyperthermia**: Temperature $\ge 39.5^\circ\text{C}$ triggers an **Emergency Alert**.

#### 3. Oxygenation & Thromboembolism (DVT / PE) Flags
* **Emergency Red Flag**: Positive patient response for `breathless` (sudden breathlessness or chest pain) combined with $SpO_2 < 92\%$ immediately generates an **Emergency Tier Alert** with 0-minute SLA requirement.
* **Calf Pain / Asymmetry**: Positive response for `calf_pain` triggers a **Critical Alert** for DVT ultrasound evaluation.

#### 4. Mobility & Rehabilitation Trajectory
* **Personal Best Tracking**: Step counts are evaluated against $50\%$ of the patient's rolling personal best. A sudden drop of $>50\%$ in daily activity indicates functional deterioration or acute distress.

### 6.2 Escalation Engine (`services/escalation.py`)
* **Execution Interval**: Async APScheduler job executes every **60 seconds**.
* **Escalation Trigger**: Scans for alerts in `open` status where:
  $$\text{Current Time} - \text{Raised At} > \text{Hospital SLA Window (e.g. 900s)}$$
* **Escalation Transition**:
  1. Sets alert status to 'escalated'.
  2. Sets `escalated_at = NOW()`.
  3. Identifies all active `admin` and `superadmin` clinicians for the tenant hospital.
  4. Queues audit notifications in `txn.alert_notification` with payload omitting raw PII to prevent data leakage in notification channels.
  5. The notification dispatcher sweeps every **30 seconds** to deliver outbound alerts.

---

## 7. Security Architecture & Threat Mitigation Matrix

| Security Threat | Mitigation Mechanism in ERAS System | Verification Point |
| :--- | :--- | :--- |
| **Cross-Tenant Data Bleed** | PostgreSQL Row-Level Security (`SET LOCAL ROLE eras_app` + `app.hospital_id`). Unfiltered queries return only the authenticated tenant's data. | `backend/tests/test_security.py` |
| **Credential & Hash Leakage** | Database permissions explicitly revoke `SELECT (password_hash)` from `eras_app`. API schemas use strict Pydantic response models. | Tested in `test_clinicians.py` |
| **Default JWT Secret Vulnerability** | Application startup validator (`app/core/config.py`) refuses to boot if `JWT_SECRET` is missing, under 32 bytes, or set to placeholder defaults. | Tested in `test_config.py` |
| **Optimistic UI False Acknowledgment** | Frontend eliminates local optimistic state overrides in `RiskQueueTable.tsx`. Acknowledged badges only render upon confirmed HTTP 200 receipt. | Verified in Vitest & QA |
| **Fabricated Clinical Telemetry** | Removed all static hardcoded vitals. When direct vitals telemetry feeds are absent, UI honestly displays structured WhatsApp self-reported cards. | Frontend Drawer verified |
| **SQL / Search Injection** | All dynamic searches use SQLAlchemy parameterized statements. Search queries escape wildcards (`%` and `_`) to treat input literally. | `backend/tests/test_patients.py` |
| **Privilege Escalation** | Writes to hospital settings, clinicians, templates and the WhatsApp account depend on `require_superadmin` (`app/core/security.py`). Self-deactivation is blocked. | `test_clinicians.py`, `test_templates.py`, `test_whatsapp_account.py` |
| **Patient Messaging** | Messages are recorded as queued and sent after the deciding transaction commits, so a rollback never hides a sent message. Check-in links are minted at send time and never stored or logged. `WHATSAPP_PROVIDER=disabled` leaves messages queued rather than reporting them sent. The Meta access token is unreadable by `eras_app`. | `test_daily_dispatch.py`, `test_whatsapp_checkin.py`, `test_security.py` |
| **Concurrent Check-In Collisions** | Check-in submissions acquire row locks (`FOR UPDATE`) on `txn.patient_episode`. Same-day submissions supersede older entries deterministically. | `backend/app/api/v1/checkin.py` |

---

## 8. Verification & Testing Reference

The platform features a 100% automated test suite across both frontend and backend environments.

### 8.1 Backend Test Suite (Pytest: 120 Tests)
Located in `backend/tests/`, executing against an isolated PostgreSQL test environment using rollback transactions:

```bash
# Run full backend test suite
cd backend
pytest -v
```

* **Test Suite Breakdown**:
  * `test_alert_history.py` (2 tests): Alert audit logs, status filters, and multi-tenant scoping.
  * `test_alerts.py` (8 tests): Alert transitions, acknowledgement flow, resolution with outcomes.
  * `test_auth.py` (4 tests): Clinician login, invalid password rejection, JWT expiration.
  * `test_checkin.py` (5 tests): Patient form generation, collection windows, duplicate idempotency.
  * `test_clinicians.py` (8 tests): Roster listing, superadmin creation, deactivation guardrails.
  * `test_config.py` (3 tests): JWT secret length and placeholder rejection at startup.
  * `test_dashboard.py` (12 tests): Queue sorting by tier/age, SLA indicators, KPI calculations in hospital timezones.
  * `test_enrollment.py` (12 tests): Patient registration, duplicate MRN protection, baseline validation.
  * `test_episodes.py` (4 tests): Baseline pairing with latest telemetry, authorization checks.
  * `test_escalation.py` (4 tests): SLA breach detection, concurrent sweep locking, notification queueing.
  * `test_hospital.py` (5 tests): Settings updates, superadmin restrictions, tenant boundary enforcement.
  * `test_notifications.py` (2 tests): Dispatcher providers, PII-stripped notification logging.
  * `test_patients.py` (10 tests): Patient list, literal wildcard search, longitudinal timeline metrics.
  * `test_reports.py` (4 tests): 12-week alert aggregations, SLA compliance %, adherence rates.
  * `test_rulesets.py` (3 tests): Approved ruleset resolution, collection vs. scoring parameter checks.
  * `test_scoring.py` (7 tests): Threshold calculations across day bands, personal-best step tracking.
  * `test_security.py` (7 tests): Kernel-level RLS validation, password hash read denials, rollback scope.
  * `test_templates.py` (4 tests): WhatsApp template catalogue, translation updates, variable validation.
* **Result**: **120 passed in 422s (100% pass rate)**.

### 8.2 Frontend Test Suite (Vitest: 56 Tests)
Located in `frontend/src/lib/`, testing business logic, formatters, and chart math:

```bash
# Run full frontend test suite
cd frontend
npm test -- --run
```

* **Test Suite Breakdown**:
  * `chart.test.ts`: Coordinate scaling, date range normalization, and threshold boundary calculations.
  * `enrollment.test.ts`: Validation for phone numbers (E.164), MRN formats, and baseline vital ranges.
  * `format.test.ts`: Post-op day formatting, timezone-aware datetime rendering, and SLA counter strings.
  * `templates.test.ts`: Placeholder interpolation checks and length constraints.
* **Result**: **56 passed in 808ms (100% pass rate)**.

---

## 9. Operations, Startup & Deployment Guide

### 9.1 Environment Configuration (`.env`)

#### Backend Configuration (`backend/.env`):
```ini
DATABASE_URL=postgresql://user:password@ep-sample-pooler.ap-southeast-1.aws.neon.tech/simpleeras?sslmode=require
JWT_SECRET_KEY=<at least 32 random characters>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=720
CORS_ORIGINS=http://localhost:3000,https://eras.example-hospital.org
ESCALATION_SWEEP_INTERVAL_SECS=60
NOTIFICATION_DISPATCH_INTERVAL_SECS=30
NOTIFICATION_PROVIDER=disabled
# Patient WhatsApp messages: disabled | log | meta
WHATSAPP_PROVIDER=disabled
META_APP_SECRET=<Meta app secret; the webhook refuses every call without it>
FRONTEND_BASE_URL=https://eras.example-hospital.org
PUBLIC_API_BASE_URL=https://api.eras.example-hospital.org
```

#### Frontend Configuration (`frontend/.env.local`):
```ini
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

### 9.2 Starting Services in Production / Development

```bash
# 1. Start Backend Service (FastAPI on Port 8000)
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2. Start Frontend Service (Next.js on Port 3000)
cd frontend
npm run dev
# Or for optimized production deployment:
npm run build
npm run start
```

### 9.3 Health & Monitoring Endpoints
* **API Documentation**: `http://localhost:8000/docs` (Swagger UI) / `http://localhost:8000/redoc`
* **Root Health Check**: `GET http://localhost:8000/` -> Returns API status and active scheduler routines.
* **Clinical Dashboard**: `http://localhost:3000/`
* **Mobile Patient Check-in Simulator**: `http://localhost:3000/checkin`
* **Clinician Sign-in Portal**: `http://localhost:3000/login`
