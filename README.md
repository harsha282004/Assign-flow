# AssignFlow

**Trustworthy assignment submission, deadline tracking and late-work management for faculty and students.**

AssignFlow is a *Student Assignment Submission & Late Work Manager*. Faculty publish assignments (file-based or quiz) for the
classes they teach; students submit work as immutable versions; the **server** decides whether each submission is on time,
late or missing, and every important event is kept as a persistent, auditable record and delivered as an in-app notification.

> Built by **Team CODE24** for the **CBC 2.0 Hackathon** (Domain: Software & Web Development, Problem Statement 73), as stated in
> [`architecture.md`](architecture.md).

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-6-646CFF?logo=vite&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

![AssignFlow landing page](docs/images/landing-page.png)

---

## Table of contents

1. [Project overview](#1-project-overview)
2. [Features](#2-features)
3. [Technology stack](#3-technology-stack)
4. [System architecture](#4-system-architecture)
5. [Core workflows](#5-core-workflows)
6. [Business rules and status semantics](#6-business-rules-and-status-semantics)
7. [Repository structure](#7-repository-structure)
8. [Database and data model](#8-database-and-data-model)
9. [API overview](#9-api-overview)
10. [Prerequisites and environment configuration](#10-prerequisites-and-environment-configuration)
11. [Installation and local execution](#11-installation-and-local-execution)
12. [Seeded accounts and data](#12-seeded-accounts-and-data)
13. [Testing and quality assurance](#13-testing-and-quality-assurance)
14. [Security and privacy](#14-security-and-privacy)
15. [Troubleshooting](#15-troubleshooting)
16. [Roadmap](#16-roadmap)
17. [Screenshots and demo](#17-screenshots-and-demo)
18. [License and contributions](#18-license-and-contributions)
19. [Further documentation](#19-further-documentation)

---

## 1. Project overview

### The problem

In a typical course, assignments are announced in chat groups, collected through e-mail or shared drives, and judged
"on time" by whoever happens to look at a timestamp. That breaks down quickly:

- Deadlines change and nobody can say which deadline applied to which upload.
- A resubmission silently overwrites the earlier file, so history is lost.
- A student who misses a deadline has no formal way to ask for extra time, and the teacher has no record of the decision.
- Students find out about new work, changes and reviews only if they happen to check.

### The solution

AssignFlow keeps one authoritative record per assignment and per student:

- **Versioned submissions.** Every upload becomes a new immutable version stored with the deadline that applied at that moment.
- **Server-side time.** The status (pending, on time, late, missing) is computed by the server from its own clock. The browser clock is never used.
- **Late-work requests.** A student who missed a deadline can ask for a limited window; faculty approve or reject; the window is enforced on every upload.
- **Persistent notifications.** Events (submissions, late requests, reviews, deadline changes, new quizzes, reminders) are stored per recipient with an unread badge.
- **Deadline reminders.** A backend scheduler reminds students about 24 hours before the current deadline.

### Target users

| Role | What they do |
|---|---|
| **Faculty** | Create and publish assignments for the subject/section combinations they teach, review submissions, decide late requests, follow class progress. |
| **Student** | See the assignments of their own section, submit work, request late submission, read feedback, receive reminders. |

Accounts are **seeded**: there is no self-registration.

> **Existing vs planned.** This README describes only functionality present in the source code. Ideas that are not implemented are listed under [Roadmap](#16-roadmap) and clearly labelled as planned.

---

## 2. Features

### Faculty

- Create assignments for a class they teach (subject × section); save as **draft** or publish immediately. Drafts can be edited and published.
- Set the deadline in IST (stored in UTC). After publishing, only the deadline can change, with an optional reason; every change is kept in the deadline history.
- Attach **reference materials** (PDF, PPT or PPTX, up to 5 files) to a draft; they are locked after publishing. Students can view or download them.
- Build a **quiz** inside AssignFlow (single choice, multiple select, true/false; marks per question; optional time limit). Quizzes are graded by the server. *(Quizzes are built in the app; there is no Google Forms integration.)*
- **Archive** a published assignment (and restore it later) instead of deleting it; **delete** a draft only when nothing refers to it.
- See the **roster** of the section, each student's versions and a chronological **Deadline Integrity Timeline** with a "why this status" explanation.
- **Review** a submission: *Under review*, *Accepted* or *Revision requested*, with feedback (required for a revision request).
- Decide **late-work requests** (approve with a 1–72 hour window, default 24, or reject).
- **Health board** with counts per student (on time, late, pending, missing), filterable by assignment, subject, section and review status.
- Receive notifications for new submissions and new versions, and for new late requests, with an unread bell badge.

> Not implemented: numeric marks or grades for file submissions (reviews carry a status and feedback text), and supporting-document uploads on late requests (a late request carries a written reason only).

### Students

- See the published assignments of **their own section**, ordered by deadline, with status badges and a live countdown.
- Open reference materials (View for PDF/PNG/JPEG, Download for the original).
- Upload a submission (PDF, DOCX, PPTX, ZIP, PNG or JPG, as allowed by the assignment) and upload **new versions**; see the version history with the deadline that applied to each.
- Take quizzes (one attempt, server-enforced deadline and time limit) and see the score immediately; the answer key is released after the deadline.
- Request **late submission** after missing a deadline; see the decision and the approved window.
- Read the **review status and feedback** and the personal timeline.
- Receive persistent notifications (new quiz, deadline change, review, late-request decision) and the **24-hour deadline reminder**, with an unread badge.

### System capabilities

- Seeded-account-only authentication with JWT, Argon2 password hashing, Redis rate limiting and token revocation.
- Role-based **and** ownership-based authorization enforced in the backend.
- Server-generated submission timestamps; UTC storage, IST display.
- Persistent unread counts computed from the database; the bell polls a lightweight count endpoint.
- Background deadline-reminder scheduler with database advisory locking and deduplication.
- Private object storage; files are only served by authenticated endpoints.
- Docker Compose setup with health checks; Alembic migrations applied automatically on backend start.

---

## 3. Technology stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend framework | React 18, TypeScript 5.9 | Single-page application UI |
| Build tool | Vite 6 | Dev server and production bundle |
| Routing | React Router 7 | Public, student and faculty routes |
| Server state | TanStack Query 5 | Fetching, caching, polling (notification count) |
| Forms / validation | react-hook-form, zod | Client-side form handling (the server validates again) |
| HTTP client | Axios | API calls with the bearer token |
| Motion / icons | Framer Motion, lucide-react | Landing-page scroll animation, icons |
| Styling | Plain CSS | Light theme, no CSS framework |
| Backend framework | FastAPI 0.115 on Uvicorn, Python 3.12 | REST API (`/api/v1`) |
| Validation | Pydantic v2, pydantic-settings | Request/response schemas, configuration |
| ORM / migrations | SQLAlchemy 2.0, Alembic | Data access and schema versioning |
| Database | PostgreSQL 16 (psycopg 3) | System of record |
| Cache / security store | Redis 7 | Rate limiting, JWT revocation list |
| Object storage | MinIO (S3 API, via boto3) | Private storage of submissions and reference files |
| Authentication | PyJWT, pwdlib (Argon2), slowapi | Tokens, password hashing, rate limits |
| File validation | filetype, python-multipart | Content-type checks, multipart uploads |
| Containers | Docker, Docker Compose | Five services, health checks |
| Backend tests | pytest, ruff | Tests and linting |
| Frontend quality | ESLint 9, typescript-eslint, Prettier 3 | Linting, type checking (`tsc`), formatting |

The MinIO image is a community build (`pgsty/minio`), pinned in `docker-compose.yml`; see the note in
[`docs/IMPLEMENTATION_LOG.md`](docs/IMPLEMENTATION_LOG.md).

---

## 4. System architecture

```mermaid
flowchart LR
    FB["Faculty browser"]
    SB["Student browser"]

    subgraph FE["Frontend container :5173"]
        SPA["React + TypeScript + Vite SPA<br/>TanStack Query, Axios"]
    end

    subgraph BE["Backend container :8000 (FastAPI, /api/v1)"]
        MW["CORS, upload size limit,<br/>request logging"]
        AUTH["Authentication<br/>JWT, role guards"]
        RT["Routers<br/>auth, faculty, student, files,<br/>notifications, health"]
        SVC["Business services<br/>assignments, submissions, quiz, late requests,<br/>reviews, notifications, reminders"]
        SCH["Deadline reminder scheduler<br/>(asyncio task, every 60 s)"]
    end

    PG[("PostgreSQL 16<br/>SQLAlchemy / Alembic")]
    RD[("Redis 7<br/>rate limits, token revocation")]
    MN[("MinIO<br/>private bucket")]

    FB -->|"HTTPS/HTTP"| SPA
    SB -->|"HTTPS/HTTP"| SPA
    SPA -->|"REST JSON + Bearer token"| MW
    MW --> AUTH --> RT --> SVC
    AUTH -.->|"revocation check"| RD
    RT -.->|"login rate limit"| RD
    SVC -->|"transactions"| PG
    SVC -->|"put / get objects"| MN
    SCH -->|"advisory lock, select, insert notifications"| PG
    PG -. "notification rows read by the API" .-> SVC
```

Solid arrows are synchronous requests; the scheduler is a background task inside the backend process and never serves HTTP.

| Component | Responsibility |
|---|---|
| **Frontend SPA** | Renders the landing, login, student and faculty pages; keeps the access token in `sessionStorage`; polls the unread count; shows IST times. It never decides statuses. |
| **Routers** | Thin HTTP layer under `/api/v1`: `auth`, `faculty`, `student`, `files`, `notifications`, `health`. |
| **Authentication / authorization** | Verifies the JWT and its revocation, applies role guards, and the scope helpers enforce ownership and section isolation. |
| **Business services** | All rules: eligibility to upload, status calculation, late windows, reviews, quiz grading, notification creation. |
| **PostgreSQL** | Source of truth for users, assignments, versions, requests, reviews, quizzes and notifications. Foreign keys are `ON DELETE RESTRICT`. |
| **Redis** | Per-IP and per-account login limits; token revocation list. If Redis is down, authenticated requests fail closed (HTTP 503). |
| **MinIO** | Private bucket; objects live under server-generated keys and are only served through the backend. |
| **Reminder scheduler** | Creates 24-hour reminder notifications (see [workflow 6](#6-twenty-four-hour-deadline-reminder)). |

---

## 5. Core workflows

### Project workflow at a glance

The end-to-end life of an assignment, from login to review. Every status shown is decided by the server.

```mermaid
flowchart TD
    L["Landing page"] --> R{"Choose role"}
    R --> FL["Faculty login"]
    R --> SL["Student login"]
    FL --> FD["Faculty dashboard<br/>(health counts, recent activity)"]
    SL --> SD["Student dashboard<br/>(assignments, deadlines, activity)"]

    subgraph FAC["Faculty"]
        FD --> NA["New assignment<br/>File / Instructions or Quiz"]
        NA --> DR["Draft<br/>(edit, reference files, quiz questions)"]
        DR --> PUB["Publish"]
        PUB --> MON["Monitor: roster, health board,<br/>per-student timeline"]
        MON --> REV["Review a submission<br/>under review / accepted / revision requested"]
        MON --> LRD["Decide late-work requests<br/>approve (1-72 h window) or reject"]
        PUB --> DLC["Change deadline (history kept)<br/>or archive / restore"]
    end

    subgraph STU["Student"]
        SD --> OPEN["Open assignment<br/>(instructions, reference files, countdown)"]
        OPEN --> SUB["Upload a file (new version)<br/>or take the quiz (one attempt)"]
        SUB --> ST["Server stamps the time and sets the status<br/>PENDING / ON_TIME / LATE / MISSING"]
        ST --> FB["Read review status and feedback"]
        OPEN --> MISS["Deadline missed"]
        MISS --> LRQ["Request late submission (reason)"]
    end

    PUB -- "notification: new quiz / deadline change" --> OPEN
    SCH(["Scheduler: 24 h reminder"]) -- "notification" --> SD
    ST -- "notification: new submission / version" --> MON
    LRQ -- "notification: new request" --> LRD
    LRD -- "approved window, notification" --> SUB
    REV -- "notification: review recorded" --> FB
```

### 1. Authentication

```mermaid
sequenceDiagram
    actor U as User (faculty or student)
    participant FE as Frontend
    participant API as FastAPI /auth
    participant RD as Redis
    participant DB as PostgreSQL

    Note over DB: Accounts exist only through the seed (no registration)
    U->>FE: Role form + login ID + password
    FE->>API: POST /api/v1/auth/login
    API->>RD: IP limit (10/min) and per-account lockout check
    alt locked out or rate limited
        API-->>FE: 429
    else allowed
        API->>DB: Find active user for role + login ID
        alt wrong ID, password or role
            API->>RD: Count the failure
            API-->>FE: 401 generic error
        else valid
            API-->>FE: Access token (JWT) + user
            FE->>FE: Store token in sessionStorage
        end
    end
    FE->>API: Protected request with Bearer token
    API->>RD: Is the token revoked?
    alt token invalid, expired or revoked
        API-->>FE: 401
    else wrong role for the route
        API-->>FE: 403
    else resource outside the caller's scope
        API-->>FE: 404 (never reveals other records)
    else authorized
        API-->>FE: 200 data
    end
    U->>FE: Log out
    FE->>API: POST /auth/logout (token revoked in Redis)
    FE->>FE: Clear token and cached data
```

### 2. Assignment lifecycle

```mermaid
stateDiagram-v2
    [*] --> DRAFT: Faculty creates (subject x section they teach)
    DRAFT --> DRAFT: Edit, attach reference files
    DRAFT --> PUBLISHED: Publish (deadline at least 1 minute ahead)
    DRAFT --> [*]: Delete (only if nothing refers to it)
    PUBLISHED --> PUBLISHED: Change deadline (history kept)
    PUBLISHED --> ARCHIVED: Archive (all records kept)
    ARCHIVED --> PUBLISHED: Restore
    note right of PUBLISHED
        Visible to students of the section.
        Before the deadline: PENDING.
        After the deadline without a submission: MISSING.
    end note
```

### 3. Submission lifecycle

```mermaid
flowchart TD
    A["Student selects a file"] --> B["POST /student/assignments/{id}/submissions"]
    B --> C{"Assignment published and in the<br/>student's section?"}
    C -- no --> X1["404 not found"]
    C -- yes --> D{"Type, content, size<br/>valid for this assignment?"}
    D -- no --> X2["415 / 413 / 422, nothing stored"]
    D -- yes --> E["Server captures the time (UTC)"]
    E --> F{"Eligible at that time?<br/>on time, revision requested,<br/>or inside an approved late window"}
    F -- no --> X3["409 DEADLINE_PASSED / SUBMISSION_ACCEPTED"]
    F -- yes --> G{"Identical to the latest version?"}
    G -- yes --> X4["409 duplicate"]
    G -- no --> H["Store object in private MinIO<br/>under a server-generated key"]
    H --> I["Database transaction under a row lock"]
    I --> J["Insert new version (immutable)<br/>with deadline snapshot and context"]
    J --> K["Create notification for the owning faculty member"]
    K --> L{"Commit succeeds?"}
    L -- no --> M["Rollback and delete the stored object"]
    L -- yes --> N["201 version number, timing"]
    N --> O["Faculty reviews: under review / accepted / revision requested"]
```

### 4. Late-work request

```mermaid
sequenceDiagram
    actor S as Student
    actor F as Faculty
    participant API as Backend
    participant DB as PostgreSQL

    S->>API: POST /student/assignments/{id}/late-request (reason 20-1000 chars)
    API->>DB: Check: deadline passed, no submission yet, no earlier request
    alt not eligible
        API-->>S: 409 NOT_MISSING or REQUEST_EXISTS
    else eligible
        API->>DB: Insert PENDING request + notification for the faculty member
        API-->>S: 201
    end
    F->>API: GET /faculty/late-requests (own assignments only)
    F->>API: POST /faculty/late-requests/{id}/decision
    alt Approve (window 1-72 h, default 24)
        API->>DB: Store APPROVED, window start and end (server clock) + notification
        S->>API: Upload inside the window
        API->>DB: Version recorded as LATE_APPROVED with its real time
    else Reject
        API->>DB: Store REJECTED + notification
    end
    Note over API,DB: A decision is final (second decision returns 409 ALREADY_DECIDED).<br/>After the window closes the assignment stays missing.
```

### 5. Notification lifecycle

```mermaid
flowchart LR
    E["Event in a service<br/>(submission, late request, decision,<br/>review, deadline change, quiz, reminder)"] --> N["notify(): INSERT ... ON CONFLICT DO NOTHING<br/>unique dedup_key, same transaction as the event"]
    N --> T[("notifications table<br/>user_id, type, title, body, ref, read_at")]
    T --> U["GET /notifications/unread-count<br/>COUNT of the caller's unread rows"]
    U --> B["Bell badge (polled every 10 s,<br/>refreshed on tab focus)"]
    B --> L["Open the bell: GET /notifications"]
    L --> R["POST /notifications/{id}/read or /read-all"]
    R --> T
    T --> P["Read state persists across reload and login"]
```

### 6. Twenty-four-hour deadline reminder

```mermaid
flowchart TD
    S["Scheduler task starts with the backend<br/>one pass every 60 s"] --> LK{"pg_try_advisory_xact_lock<br/>acquired?"}
    LK -- no --> SK["Another instance is running: skip this pass"]
    LK -- yes --> Q["Select assignments: status PUBLISHED and<br/>deadline in (now + 22 h, now + 24 h]"]
    Q --> ST["Students of the assignment's section"]
    ST --> DN{"Already completed?<br/>file: has an uploaded version<br/>quiz: has a submitted attempt"}
    DN -- yes --> SKIP["No reminder"]
    DN -- no --> INS["INSERT notification DEADLINE_REMINDER_24H<br/>dedup key = assignment + deadline instant + student<br/>ON CONFLICT DO NOTHING"]
    INS --> COMMIT["Commit"]
    COMMIT --> UI["Student bell badge and list<br/>(deadline shown in IST)"]
```

Behaviour, taken from `backend/app/services/reminders.py`:

- **Window.** The reminder is created when the *current* deadline is between 22 and 24 hours away. The 2-hour margin lets a restart or missed pass still send it without sending "late" reminders. An assignment published with less than 22 hours remaining gets no 24-hour reminder; if the backend is down for the whole 2-hour window the reminder is skipped.
- **Exactly once.** The deduplication key contains the assignment, the deadline instant and the student, so repeated passes, several instances and restarts add nothing.
- **Deadline changes.** The old key becomes obsolete: no reminder is sent for a deadline that no longer applies. If the new deadline is later, the new deadline earns one reminder of its own (a student can therefore receive a second reminder after an extension).
- **Drafts and archived assignments** are never reminded. **Students who already submitted** (file) or **finished the quiz** are skipped.
- The scheduler is disabled with `REMINDER_SCHEDULER_ENABLED=false` (the test configuration does this).
- A separate, computed "Needs attention" alert (due within 24 hours / 3 hours, missing, window closing) is shown in the bell as well; it stores nothing.

### 7. Deployment and startup

```mermaid
flowchart TD
    UP["docker compose up --build -d"] --> PGS["postgres<br/>healthcheck: pg_isready"]
    UP --> RDS["redis<br/>healthcheck: redis-cli ping"]
    UP --> MNS["minio<br/>healthcheck: /minio/health/live"]
    PGS --> BES
    RDS --> BES
    MNS --> BES
    subgraph BES["backend (starts when the three above are healthy)"]
        I1["entrypoint.sh runs app.db.init_db"] --> I2["wait for services, advisory lock"]
        I2 --> I3["alembic upgrade head"]
        I3 --> I4["seed accounts (idempotent), create private bucket"]
        I4 --> I5["uvicorn serves :8000 and starts the reminder scheduler"]
    end
    I5 --> HB["backend healthcheck: GET /api/v1/health<br/>(db, redis, storage must be ok)"]
    HB --> FES["frontend (starts when the backend is healthy)<br/>vite preview on :5173, healthcheck: wget /"]
    FES --> BR["Browser: http://localhost:5173"]
```

---

## 6. Business rules and status semantics

### Completion status vs review status

These are **two independent concepts**. Uploading a file does not mean it was graded or accepted.

**Completion (timing) status** — computed by the server from its own clock against the assignment's *current* deadline `D` (`backend/app/services/status.py`):

| Status | Meaning |
|---|---|
| `PENDING` | No submission yet and `now <= D` (exactly at `D` is still pending). |
| `MISSING` | No submission and `now > D`. |
| `ON_TIME` | The **first** version was uploaded at or before `D` (exactly at `D` counts as on time). |
| `LATE` | The first version was uploaded after `D`. |
| `LATE_APPROVED` (a flag, not a separate timing) | The first version was uploaded through an approved late request and is still late; it is shown as "Late (approved)" and never as on time. |

Submission-level timing follows the **first** version; later versions never change it (a *Resubmitted* flag is shown when more than one version exists).

**Review status** — set by faculty on the latest version (`UNDER_REVIEW`, `ACCEPTED`, `REVISION_REQUESTED`; students without a review show *Not reviewed*). Reviews are an append-only log; a new version starts as *Not reviewed*. *Accepted* closes further uploads; *Revision requested* lets the student upload once after the deadline.

### Time

- **Server-generated timestamps.** Upload time, decision time and window times come from the server clock; any timestamp sent by a client is ignored.
- **UTC storage, IST display.** Deadlines must carry a UTC offset and are stored in UTC. The UI enters and shows `Asia/Kolkata` (UTC+05:30).
- **Deadline rules.** At create/publish the deadline must be at least 1 minute ahead. After publishing only the deadline can change (it must be in the future; extensions after the old deadline are allowed). `original_deadline` is never modified; each change is a row in `deadline_changes`.

### Late requests

- Allowed only after the deadline, for a student with no submission, one request per assignment, reason 20–1000 characters.
- Faculty approve (window 1–72 hours, default 24) or reject once; the window is enforced on every upload. The upload inside the window is recorded as `LATE_APPROVED`.
- Late requests do not apply to quizzes.

### File assignments vs quizzes

| | File assignment | Quiz |
|---|---|---|
| Student action | Upload one or more versions | One attempt answered in the app |
| Late work | Late request possible | Not available; no attempt can start after the deadline |
| Grading | Faculty review status and feedback | Automatic: a question earns full marks only if the selected options exactly match the correct set |
| Answer key | — | Never sent while the quiz is taken; shown after the deadline |
| Edit after publish | Only the deadline | Only the deadline |

### Visibility and isolation

- A student sees only **published** assignments of **their own section** (archived ones remain readable only if the student has a submission or late request on them).
- A faculty member manages only assignments they created **and** for which they still have a teaching assignment (subject × section). Out-of-scope resources return 404; creating for a class you do not teach returns 403.
- Notifications are scoped to the authenticated user.

### Notifications

Each event has a deterministic `dedup_key` and is inserted with `ON CONFLICT DO NOTHING` in the same transaction as the event, so a retried action never produces a second notification.

### Version history and immutability

Submission versions are never updated or deleted by the application; files are kept. A deletion of an assignment is refused while any submission, review, request, notification or attempt refers to it (publish → archive instead). All foreign keys use `ON DELETE RESTRICT`.

---

## 7. Repository structure

```text
AssignFlow/
├── README.md                    This document
├── architecture.md              Blueprint (decisions, rules, API plan)
├── docker-compose.yml           postgres, redis, minio, backend, frontend
├── .env.example                 Placeholder environment template (copy to .env)
├── .gitignore / .gitattributes
├── docs/
│   ├── IMPLEMENTATION_LOG.md        Chronological implementation and decisions
│   ├── DATABASE_SCHEMA.md           Tables, constraints, indexes
│   ├── REQUIREMENTS_TRACEABILITY.md Requirement-to-implementation map
│   ├── DEMO_DATASET_NAME_MAPPING.md Demo dataset notes
│   └── DATASET_TRANSITION_DRYRUN.md Dry-run report of the dataset transition tool
├── backend/
│   ├── Dockerfile, entrypoint.sh, pyproject.toml, alembic.ini
│   ├── alembic/versions/        0001 initial schema, 0002 attachments, 0003 archive, 0004 quizzes
│   ├── app/
│   │   ├── main.py              App factory, middleware, routers, scheduler start
│   │   ├── core/                Settings, clock, dependencies (auth guards), errors, security
│   │   ├── routers/             auth, faculty, student, files, notifications, health
│   │   ├── schemas/             Pydantic request/response models
│   │   ├── services/            Business rules (assignments, submissions, quiz, reminders, ...)
│   │   └── db/                  Models, session, init_db, seeds, transition_dataset
│   ├── scripts/find_orphans.py  Storage housekeeping report
│   └── tests/                   unit/, db/, api/ test suites
└── frontend/
    ├── Dockerfile, package.json, package-lock.json, vite.config.ts
    ├── public/                  Login background videos, landing image
    └── src/
        ├── app/                 Router
        ├── api/                 Axios client, TanStack Query hooks, types
        ├── auth/                Auth context, login hook, token storage
        ├── pages/               public (landing, logins), student, faculty
        ├── components/          Shared UI, quiz builder/taker, notification bell, landing
        └── *.css                Plain CSS (dashboard, login pages, landing, quiz, materials)
```

---

## 8. Database and data model

Schema is created and evolved only through Alembic (`backend/alembic/versions`). Full table, constraint and index
detail is in [`docs/DATABASE_SCHEMA.md`](docs/DATABASE_SCHEMA.md).

```mermaid
erDiagram
    USERS ||--o| STUDENT_PROFILES : "has (students)"
    SECTIONS ||--o{ STUDENT_PROFILES : "contains"
    USERS ||--o{ TEACHING_ASSIGNMENTS : "teaches (faculty)"
    SUBJECTS ||--o{ TEACHING_ASSIGNMENTS : ""
    SECTIONS ||--o{ TEACHING_ASSIGNMENTS : ""
    USERS ||--o{ ASSIGNMENTS : "creates"
    SUBJECTS ||--o{ ASSIGNMENTS : ""
    SECTIONS ||--o{ ASSIGNMENTS : "audience"
    ASSIGNMENTS ||--o{ DEADLINE_CHANGES : "history"
    ASSIGNMENTS ||--o{ ASSIGNMENT_STATE_CHANGES : "archive / restore"
    ASSIGNMENTS ||--o{ ASSIGNMENT_ATTACHMENTS : "reference files"
    ASSIGNMENTS ||--o{ SUBMISSIONS : ""
    USERS ||--o{ SUBMISSIONS : "student"
    SUBMISSIONS ||--o{ SUBMISSION_VERSIONS : "immutable versions"
    SUBMISSIONS ||--o{ REVIEWS : "append-only"
    SUBMISSION_VERSIONS ||--o{ REVIEWS : "reviewed version"
    ASSIGNMENTS ||--o{ LATE_REQUESTS : ""
    USERS ||--o{ LATE_REQUESTS : "student"
    LATE_REQUESTS ||--o| SUBMISSION_VERSIONS : "approved window used by"
    USERS ||--o{ NOTIFICATIONS : "recipient"
    ASSIGNMENTS ||--o{ QUIZ_QUESTIONS : "quiz only"
    QUIZ_QUESTIONS ||--o{ QUIZ_OPTIONS : ""
    ASSIGNMENTS ||--o{ QUIZ_ATTEMPTS : ""
    USERS ||--o{ QUIZ_ATTEMPTS : "student"
    QUIZ_ATTEMPTS ||--o{ QUIZ_ANSWERS : "selected options"
```

Key points:

- **Ownership.** `assignments.created_by` plus a matching `teaching_assignments` row gives a faculty member control; a student's section (`student_profiles.section_id`) defines which assignments they see.
- **Immutability.** `submission_versions` rows are inserted, never updated; each stores the deadline in force at upload (`deadline_at_upload`) and its upload context (`REGULAR`, `LATE_APPROVED`, `REVISION`).
- **Quiz integrity.** `quiz_answers` uses composite foreign keys so an answer's attempt, question and option must all belong to the same quiz. One attempt per student and quiz is a unique constraint.
- **Referential safety.** All foreign keys are `ON DELETE RESTRICT`; migrations never rewrite history (downgrades refuse to run when they would destroy data).
- **Privacy.** Passwords are stored only as Argon2 hashes; this README contains no data from a real database.

---

## 9. API overview

Base URL (local): `http://localhost:8000/api/v1`. Interactive OpenAPI documentation (FastAPI): `http://localhost:8000/docs`.
All endpoints except login and health require `Authorization: Bearer <token>`. Errors use a common envelope
(`{"error": {"code", "message", ...}}`). The tables below are generated from the routers in `backend/app/routers`.

**Auth** (`/auth`)

| Method | Route | Role | Purpose |
|---|---|---|---|
| POST | `/auth/login` | public | `{role, login_id, password}` → token and user (rate limited) |
| GET | `/auth/me` | any | Profile and academic mapping |
| POST | `/auth/logout` | any | Revoke the current token (204) |

**Faculty assignments** (`/faculty`, role FACULTY)

| Method | Route | Purpose |
|---|---|---|
| GET | `/faculty/assignments` | Own assignments; filters `subject_id`, `section_id`, `state=active\|archived\|all` |
| POST | `/faculty/assignments` | Create (draft, or published when `publish` is true) → 201 |
| GET | `/faculty/assignments/{id}` | Detail, deadline history, attachments |
| PATCH | `/faculty/assignments/{id}` | Edit a draft |
| POST | `/faculty/assignments/{id}/publish` | Publish (also validates and publishes quizzes) |
| PATCH | `/faculty/assignments/{id}/deadline` | Change a published deadline |
| POST | `/faculty/assignments/{id}/archive`, `/restore` | Archive or restore |
| GET | `/faculty/assignments/{id}/deletion-check` | Whether and why a draft can be deleted |
| DELETE | `/faculty/assignments/{id}` | Delete a draft (409 if anything refers to it) |
| POST / DELETE | `/faculty/assignments/{id}/attachments[/{attachment_id}]` | Add (201) / remove (204) a reference document on a draft |
| GET | `/faculty/assignments/{id}/roster` | One row per student, optional `status` filter |
| GET | `/faculty/assignments/{id}/students/{student_id}/timeline` | Versions, reviews, events, "why this status" |

**Quizzes**

| Method | Route | Role | Purpose |
|---|---|---|---|
| POST / GET / PUT | `/faculty/quizzes`, `/faculty/quizzes/{id}` | FACULTY | Create (201), read with answer key, replace a draft's definition |
| GET | `/faculty/quizzes/{id}/participation` | FACULTY | Started / submitted / scores |
| GET | `/student/quizzes/{id}` | STUDENT | Details; questions only after the attempt starts, never the key |
| POST | `/student/quizzes/{id}/attempts` | STUDENT | Start the single attempt (idempotent) |
| PUT | `/student/quiz-attempts/{id}/answers` | STUDENT | Save answers |
| POST | `/student/quiz-attempts/{id}/submit` | STUDENT | Submit (idempotent) |
| GET | `/student/quiz-attempts/{id}/result` | STUDENT | Score; answer key after the deadline |

**Student assignments and submissions** (`/student`, role STUDENT)

| Method | Route | Purpose |
|---|---|---|
| GET | `/student/assignments`, `/student/assignments/archived` | Own-section assignments (active / own history) |
| GET | `/student/assignments/{id}` | Detail incl. own versions, status, `can_upload`, timeline |
| POST | `/student/assignments/{id}/submissions` | Multipart `file` → 201 new version (409 `DEADLINE_PASSED`, `SUBMISSION_ACCEPTED`, duplicates; 413/415/422 validation) |
| POST | `/student/assignments/{id}/late-request` | `{reason}` → 201 (409 `NOT_MISSING`, `REQUEST_EXISTS`) |

**Late requests, reviews, overview** (role FACULTY)

| Method | Route | Purpose |
|---|---|---|
| GET | `/faculty/late-requests`, `/faculty/late-requests/{id}` | List (filters) and detail |
| POST | `/faculty/late-requests/{id}/decision` | `{decision: APPROVE\|REJECT, note?, window_hours?}` (409 `ALREADY_DECIDED`) |
| POST | `/faculty/submissions/{id}/reviews` | Record a review → 201 |
| GET | `/faculty/submissions/{id}/locator` | Resolve a notification's submission to its page (404 unless it is yours) |
| GET | `/faculty/overview`, `/faculty/overview/students` | Health-board counts and the students behind them |

**Files** (`/files`, owner student or the assignment's faculty; materials: students of the section and the owner)

| Method | Route | Purpose |
|---|---|---|
| GET | `/files/versions/{version_id}` , `/files/versions/{version_id}/preview` | Download / inline preview of a submitted version |
| GET | `/files/materials/{attachment_id}`, `/files/materials/{attachment_id}/preview` | Download / preview a reference document |

**Notifications** (`/notifications`, any role, own records only)

| Method | Route | Purpose |
|---|---|---|
| GET | `/notifications` | Computed alerts, stored items, unread count |
| GET | `/notifications/unread-count` | `{unread_count}` (single COUNT query) |
| POST | `/notifications/{id}/read` | Mark one as read (404 if not yours) → 204 |
| POST | `/notifications/read-all` | Mark all of your own as read → 204 |

**Health**: `GET /health` → `200 {"status":"ok","db":"ok","redis":"ok","storage":"ok"}`, or `503` with the failing dependency marked `"down"`.

More detail on request and response shapes is in `architecture.md` and the generated OpenAPI page.

---

## 10. Prerequisites and environment configuration

### Prerequisites

- **Docker Desktop** (Windows) running, with at least 4 GB RAM allocated; it provides Docker Compose.
- **PowerShell**.
- Node.js and Python on the host are **not** required to run the stack. They are only needed for running tooling outside containers (the images use Python 3.12 and Node 20).

### Environment variables

Copy the template and edit it. **Never commit `.env`**: it holds credentials and is excluded by `.gitignore`.

```powershell
Copy-Item .env.example .env
```

| Variable | Required | Notes |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | yes | The password must equal the one in `DATABASE_URL`. |
| `DATABASE_URL` | yes | `postgresql+psycopg://user:password@postgres:5432/db` (host is the Compose service name). |
| `REDIS_URL` | yes | `redis://redis:6379/0`. |
| `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` | yes | Password at least 8 characters. |
| `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, `S3_REGION` | yes | Access/secret keys must equal the MinIO root credentials. |
| `SEED_DEMO_PASSWORD` | yes | One demo password for all seeded accounts; startup fails when empty. Share it out of band. |
| `JWT_SECRET` | yes | At least 32 random characters; the API refuses to start with a missing, short or placeholder value. |
| `JWT_EXPIRE_MINUTES` | no | Default 120. |
| `MAX_UPLOAD_MB`, `APP_TIMEZONE_DISPLAY` | no | Defaults 10 and `Asia/Kolkata`. |
| `FRONTEND_ORIGIN` | yes | CORS origin; must exactly equal the URL in the browser (`http://localhost:5173`). |
| `VITE_API_BASE_URL` | yes | Public build-time value baked into the frontend (`http://localhost:8000/api/v1`); rebuild the frontend after changing it. |
| `REMINDER_SCHEDULER_ENABLED` | no | Optional; defaults to `true`. Set `false` to turn the reminder scheduler off. |

Generate a JWT secret:

```powershell
python -c "import secrets;print(secrets.token_urlsafe(48))"
```

**Production note.** The template and README values are for local development. Do not reuse development passwords or the demo
password in any shared or production environment; use unique strong secrets, restrict `FRONTEND_ORIGIN`, serve over HTTPS and
do not publish the PostgreSQL, Redis or MinIO ports (the Compose file already publishes only 5173 and 8000).

---

## 11. Installation and local execution

```powershell
# 1. Clone (use your repository URL) and enter the project
git clone <your-repository-url> AssignFlow
cd AssignFlow

# 2. Configure the environment (then edit .env: replace every placeholder, see section 10)
Copy-Item .env.example .env

# 3. Validate the configuration, then build and start all five services
docker compose config --quiet
docker compose up --build -d

# 4. Wait until every service is "healthy" (first start takes about 15-30 s for seeding)
docker compose ps
docker compose logs -f backend      # Ctrl+C to stop following

# 5. Verify the health check
Invoke-RestMethod http://localhost:8000/api/v1/health

# 6. Open the application
Start-Process http://localhost:5173
```

What happens on backend start (`backend/entrypoint.sh` → `python -m app.db.init_db`): wait for PostgreSQL, Redis and MinIO →
take an advisory lock → `alembic upgrade head` (migrations are applied automatically) → seed accounts (idempotent) → create the
private bucket → start Uvicorn and the reminder scheduler.

Useful commands:

```powershell
docker compose exec backend alembic current          # current migration revision
docker compose exec backend python -m app.db.init_db # re-run initialization (idempotent)
docker compose logs -f backend                       # follow logs (also: frontend, postgres, redis, minio)
docker compose down                                  # stop; data volumes are KEPT
```

### Fresh setup vs an existing database

- **Fresh development setup:** the first `up` creates empty volumes, runs all migrations and seeds the accounts.
- **Existing populated database:** keep your volumes. Restarting is safe: migrations are applied incrementally and the seed does not duplicate or re-hash existing accounts. If the stored dataset differs from the configured one, the initializer reports it and continues without changing data.
- **Never** run `docker compose down -v` on data you want to keep: it deletes the PostgreSQL, Redis and MinIO volumes. Take a backup first (for example `docker compose exec -T postgres pg_dump -U <user> <db> > backup.sql`, kept outside the repository).
- If you changed database or MinIO credentials after the first start, the existing volumes still hold the *old* credentials; either restore the old values or, for a throwaway setup only, recreate the volumes.

---

## 12. Seeded accounts and data

Authentication is **seeded-account-only**: there is no registration endpoint. Accounts are created by the initializer
(`backend/app/db/seeds`) and every account uses the password you set in `SEED_DEMO_PASSWORD` (stored as an Argon2 hash).
All names and data are fictional.

The current seed configuration (`backend/app/db/seeds/seed_config.py`) defines:

- **15 faculty** with login IDs `FAC001`–`FAC015`;
- **50 students** with login IDs `STU0101`–`STU0150`, in sections **CSE-5A (17), CSE-5B (17), CSE-5C (16)**;
- semester-5 subjects and teaching assignments (subject × section) linking each faculty member to their classes.

For example, `FAC001` teaches CS503 *Database Systems* in CSE-5A and `STU0101`–`STU0103` belong to CSE-5A. Sign in on the
matching form (faculty or student); IDs are case-insensitive.

> **Configured seed vs your local database.** The configuration above is what a fresh database receives. A database seeded by an
> earlier version of the project may still contain the older 50-faculty / 200-student dataset. The initializer does not change
> or delete existing accounts; moving an older database to the current dataset is a separate, deliberate step
> (`python -m app.db.transition_dataset` is a **dry run**; `--apply` modifies data and should be used only after reading the
> report in [`docs/DATASET_TRANSITION_DRYRUN.md`](docs/DATASET_TRANSITION_DRYRUN.md) and taking a backup).

---

## 13. Testing and quality assurance

Commands (PowerShell, project root). Run them yourself; this README does not claim any particular current result.

```powershell
# Backend: tests and lint (tests run in the backend container against isolated databases)
docker compose build backend
docker compose run --rm backend pytest
docker compose run --rm backend ruff check .

# Frontend: lint, formatting, TypeScript + production build
cd frontend
npm ci
npm run lint
npm run format:check
npm run build            # runs "tsc -b && vite build"
cd ..

# Docker Compose configuration
docker compose config --quiet
```

How tests are isolated: they use dedicated databases (`assignflow_test`, `assignflow_migtest`, `assignflow_inittest`), Redis
database 1 and the `assignflow-test` bucket, so they never touch the normal demo database. The reminder scheduler is disabled in
the test configuration; reminder tests call the service directly with a frozen clock. The backend image contains the tests,
so rebuild it (`docker compose build backend`) after editing them.

Test suites (`backend/tests`):

| Area | Files |
|---|---|
| Unit | status semantics, upload eligibility, file validation, security (JWT/passwords) |
| Database | constraints, migrations (upgrade, downgrade, data preserved), seed, initializer |
| API: access and scope | authentication and rate limiting, role guards, section/ownership isolation |
| API: workflows | assignments, deadline changes, archive/delete, attachments, submissions, late requests, reviews and timeline, health-board overview |
| API: quizzes | creation and validation, attempts, grading, answer-key release, time rules |
| API: notifications | unread counts, mark read / read-all, submission notifications, 24-hour reminders (timing, recipients, duplicates, deadline changes, IST text) |

The frontend has no unit-test framework configured; the UI was exercised manually and with scripted browser runs that are not part of this repository.

---

## 14. Security and privacy

Implemented controls:

- **Authentication.** Seeded accounts only; short-lived JWT (default 2 hours) sent as a Bearer token; the frontend keeps it in `sessionStorage`. Logout revokes the token in a Redis deny-list keyed by its `jti`.
- **Password hashing.** Argon2 (pwdlib). Passwords and hashes are never logged or returned by the API.
- **Rate limiting.** 10 login requests per minute per IP and 5 failed attempts per (role, login ID) per 10 minutes (HTTP 429). If Redis is unavailable the system fails closed (HTTP 503).
- **Authorization.** Role guards on every route and **ownership/scope checks** in the services: out-of-scope records return 404 so identifiers cannot be probed; faculty can act only on classes they teach; students only on their own section and their own submissions.
- **Server-side validation.** All input is validated by Pydantic; uploads are validated for size, extension, real content type and archive structure; unknown fields are rejected on the main write payloads.
- **Private file storage.** The MinIO bucket is private (no public policy); objects have server-generated keys; downloads and previews go through authenticated endpoints that check ownership.
- **Secrets.** Configuration is read from the environment only; `.env` is git-ignored; the API refuses to start with a weak `JWT_SECRET`.
- **Database integrity.** Foreign keys with `ON DELETE RESTRICT`, check and unique constraints (for example one quiz attempt per student), row locks for concurrent submissions, and transactional notification creation.
- **Safe errors.** A common error envelope with stable codes; internal details are not exposed; login failures are generic.
- **Student-data protection.** Seed data is fictional; database dumps are git-ignored; no real student data belongs in the repository.

AssignFlow has **not** been formally security-audited or certified, and no claim of complete security is made.

**Responsible use and reporting.** Use AssignFlow only with data you are permitted to process. If you find a vulnerability, please
report it privately to the repository owner (for example through GitHub's private vulnerability reporting, if enabled, or by
contacting the owner directly) rather than opening a public issue with exploit details.

---

## 15. Troubleshooting

| Problem | What to check / do |
|---|---|
| **A service does not start or stays unhealthy** | `docker compose ps` then `docker compose logs <service>` (`postgres`, `redis`, `minio`, `backend`, `frontend`). The backend waits up to 60 s for dependencies and has a 90 s start period. |
| **`set POSTGRES_PASSWORD in .env` style errors from Compose** | A required variable is missing. Recreate `.env` from `.env.example` and fill every value. |
| **Database connection errors / authentication failed** | `DATABASE_URL` must use host `postgres` and the same password as `POSTGRES_PASSWORD`. If you changed credentials after the first start, the existing `pgdata` volume keeps the old ones. |
| **Migration failures** | `docker compose logs backend` (the initializer stops with a non-zero exit); inspect with `docker compose exec backend alembic current`. Do not edit applied migrations. A downgrade that would destroy data (archived assignments, quizzes) is refused by design. |
| **Frontend cannot reach the backend / CORS errors** | `FRONTEND_ORIGIN` must exactly equal the browser URL; `VITE_API_BASE_URL` must be host-reachable (`http://localhost:8000/api/v1`, never `http://backend:8000`). After changing it: `docker compose up --build -d frontend`. Check `http://localhost:8000/api/v1/health`. |
| **Backend refuses to start: invalid environment** | Missing `SEED_DEMO_PASSWORD`, or a missing/short/placeholder `JWT_SECRET` (needs 32+ characters). |
| **Login fails** | Use the form that matches the role (faculty vs student). After 5 failed attempts for one ID the account returns 429 for 10 minutes; if Redis is down all authenticated requests return 503. Check `SEED_DEMO_PASSWORD`. |
| **Upload fails** | 413 too large (limit is the assignment's size, at most `MAX_UPLOAD_MB`); 415 type or content mismatch; 409 deadline passed / already accepted / identical to the latest version; 503 storage unavailable (check `minio`). |
| **Download or preview fails** | The file is served only to its owner or the assignment's faculty; check the `minio` service health and `docker compose exec backend python scripts/find_orphans.py` for storage/database mismatches. |
| **No deadline reminders** | Check `REMINDER_SCHEDULER_ENABLED` is not `false`; `docker compose logs backend` (look for `assignflow.reminders`); the assignment must be PUBLISHED with its deadline 22–24 h away, and students who already submitted are skipped. A reminder is created once per effective deadline. |
| **Ignored files were pushed to GitHub** | `.env` and `backups/` are listed in `.gitignore`; check with `git check-ignore -v .env`. If a secret was ever committed, ignoring it later does **not** remove it from history: rotate that credential immediately. |

---

## 16. Roadmap

The following are **planned ideas, not implemented**:

- Numeric marks/grades for file submissions and a mark-release policy.
- Supporting-document uploads on late-work requests.
- E-mail or push delivery of notifications (currently in-app only).
- A frontend unit/component test suite.
- Optional integration with external quiz tools (currently quizzes are built in the app).
- Configurable reminder lead times (currently a fixed 24-hour reminder).

---

## 17. Screenshots and demo

All screenshots show the seeded **fictional demo data**. The images are stored in [`docs/images/`](docs/images/).

### Public pages

| Landing page |
|---|
| ![Landing page with the hero, navigation and login buttons](docs/images/landing-page.png) |

| Student login | Faculty login |
|---|---|
| ![Student login page](docs/images/student-login.png) | ![Faculty login page](docs/images/faculty-login.png) |

### Faculty portal

**Dashboard.** Counts of active assignments, expected and missing submissions and pending late requests, the per-assignment
submission health table, and the recent-activity feed. The bell shows the unread notification badge.

![Faculty dashboard](docs/images/faculty-dashboard.png)

**New assignment.** A selector at the top chooses between a *File / Instructions Assignment* and a *Quiz Assignment*; the form below
holds the class, title, instructions, reference documents, deadline and file rules.

![Faculty new assignment form with the file and quiz type selector](docs/images/faculty-new-assignment.png)

**Submissions roster.** One row per student of the section, with the completion status (*Pending*, *On time*), the review status
(*Accepted*) and the version count with the upload time in IST.

![Faculty roster of student submissions](docs/images/faculty-submissions-roster.png)

### Student portal

**Dashboard.** Active, submitted and due-this-week counts, upcoming assignments with their status and the teacher's feedback,
and recent activity (late-request decision, review).

![Student dashboard](docs/images/student-dashboard.png)

**Assignment page.** The student's submission with its status, the immutable version history (file, size, server receive time and
the deadline that applied) with **View** and **Download**, and the teacher's review history.

![Student assignment page with version history and review](docs/images/student-assignment-submission.png)

> Screenshots not yet included: the quiz builder and quiz-taking pages, the late-request pages, the faculty health board, and the
> notification panel. Add them to `docs/images/` and reference them the same way.

---

## 18. License and contributions

**License.** The repository does not currently contain a `LICENSE` file, so no license has been selected. Until the owners choose
one, all rights are reserved by default. Add a `LICENSE` file when the team decides.

**Contributing.** There is no formal contribution policy yet. Suggested flow: open an issue describing the change, fork and create a
branch, keep changes focused, run the backend tests, `ruff`, and the frontend lint/format/build commands in
[section 13](#13-testing-and-quality-assurance), and open a pull request describing what changed and how it was verified. Never
include `.env` files, database dumps or real student data. Report bugs through GitHub issues with the steps to reproduce, the
expected and actual behaviour, and relevant log lines (remove any sensitive data first).

---

## 19. Further documentation

| Document | Content |
|---|---|
| [`architecture.md`](architecture.md) | Blueprint: decisions, rules, data model, planned API |
| [`docs/IMPLEMENTATION_LOG.md`](docs/IMPLEMENTATION_LOG.md) | Chronological implementation log and decisions |
| [`docs/DATABASE_SCHEMA.md`](docs/DATABASE_SCHEMA.md) | Tables, constraints and indexes |
| [`docs/REQUIREMENTS_TRACEABILITY.md`](docs/REQUIREMENTS_TRACEABILITY.md) | Requirement-to-implementation traceability |
| [`docs/DEMO_DATASET_NAME_MAPPING.md`](docs/DEMO_DATASET_NAME_MAPPING.md) | Demo dataset notes |
| [`docs/DATASET_TRANSITION_DRYRUN.md`](docs/DATASET_TRANSITION_DRYRUN.md) | Dry-run report for the dataset transition tool |
