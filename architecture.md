# AssignFlow — Architecture Blueprint

**AssignFlow — Student Assignment Submission & Late Work Manager**
Team CODE24 · CBC 2.0 Hackathon · Domain: Software & Web Development · Problem Statement 73

| Item | Value |
|---|---|
| Document status | **Draft for team approval.** No code has been written. Nothing here is implemented yet. |
| Applies to | Round 2 (implementation, 20 h) and Round 3 (demo) |
| Owner | Team CODE24 |
| Last updated | 2026-10-10 |

Each decision in this document is labelled:

- **[C] Confirmed** — already agreed (problem statement, agreed stack, earlier team decisions, the Round 1 deck).
- **[P] Proposed** — an implementation detail recommended here. It stands unless the team objects.
- **[Q] Open question** — needs an explicit team decision. All of these are collected in §31.

---

## 1. Document purpose and scope

This is the single technical blueprint for AssignFlow. Developers should be able to build each phase from it without re-deciding the design. It defines:

- what we build: requirements, scope and rules;
- how it fits together: services, modules, data and APIs;
- how we prove it works: tests, traceability and the demo script.

It deliberately contains **no application code, Dockerfiles, models or migrations**. Those are produced phase by phase in Round 2 (§27).

**Source priority when sources conflict** [C]:

1. Hackathon rules and Problem Statement 73.
2. The submitted Round 1 PPT.
3. The agreed technical stack.
4. Previously agreed requirements.
5. Recommendations in this document.

### 1.1 Conflicts found while preparing this document

Each of these must be resolved before Phase 1 (see §31).

| # | Conflict | Sources | Effect |
|---|---|---|---|
| X1 | **Product name.** The Round 1 deck we prepared is titled **DueTrace**; this brief names the product **AssignFlow**. | Round 1 deck vs. this brief | If the deck was submitted as DueTrace, the jury will see a different name in Round 3. This document uses AssignFlow as instructed. |
| X2 | **Hosted deployment.** Slide 6 of the deck lists Vercel, Railway, Supabase PostgreSQL and Supabase Storage. This brief makes local Docker Compose primary and cloud optional. | Deck slide 6 + notes vs. this brief | If the deck was submitted with hosted deployment, it is a stated commitment. §26.6 keeps hosted deployment as a config-only variant, so no code differs. |
| X3 | **Exact PPT not in the project.** The project contains only the draft deck we prepared, not a confirmation of what was submitted. | Project files | Traceability (§28) is mapped to the draft deck's six features. It must be re-checked against the submitted file. |

---

## 2. Project overview

AssignFlow is a web application for one college with exactly two roles: **Faculty** and **Student** [C]. Its job is to track assignments through to a final, explainable status.

1. Faculty publish assignments with deadlines to the sections they teach.
2. Students upload work. Every upload is kept as an immutable version with a server timestamp.
3. The backend classifies each student as Pending, On time, Late or Missing.
4. A student who missed a deadline may request permission to submit late. The responsible teacher approves or rejects the request. An approval grants a limited upload window.
5. Faculty review the work and record the final review status and feedback.
6. A **Deadline Integrity Timeline** shows, for one student and one assignment, the whole history behind the current status. It covers deadlines and their changes, versions, the late request, the decision and the review.

**Primary differentiator** [C]: teacher-approved late submission combined with the Deadline Integrity Timeline. This is a focused, integrated workflow. We make no claim that other platforms lack these individual features.

---

## 3. Official problem statement

The wording below is as given by the organizers.

> **Problem Statement 73: Student Assignment Submission & Late Work Manager**
> **Problem:** Teachers receive many assignments with different deadlines. Late submissions, resubmissions, and missing work can be difficult to track.
> **Objective:** Build a system that manages assignment submissions and identifies late, missing, and resubmitted work.
> **Workflow:** Faculty creates assignments with deadlines. Students submit their work. System validates submission time and status. Faculty reviews submissions. Final status is recorded.
> **Key Requirements:** Assignment and deadline management. Student submission. Late/missing detection. Resubmission handling. Submission status/history.
> **Edge Cases:** Submission after deadline. Student submits multiple versions. Assignment deadline changes.
> **Scope — Must Have:** Assignment creation, submission, deadline validation, and status tracking. **Stretch:** Automatic late-risk alerts or submission analytics.
> **Demo:** Create an assignment, submit work before and after the deadline, and demonstrate late and resubmission handling.

---

## 4. Confirmed requirements and assumptions

### 4.1 Confirmed requirements [C]

| ID | Requirement | Source |
|---|---|---|
| R1 | Faculty create assignments with deadlines for authorized subject + section | PS73, deck F2 |
| R2 | Deadline management, including changes with preserved history | PS73 edge case, deck F2/F4 |
| R3 | Students submit files | PS73 |
| R4 | Server validates submission time; status Pending / On time / Late / Missing | PS73, deck F3 |
| R5 | Resubmission creates new versions; earlier versions preserved | PS73 edge case, deck F4 |
| R6 | Submission status and history visible | PS73, deck F4 |
| R7 | Faculty reviews submissions; final status recorded | PS73 workflow |
| R8 | Roster-only ID + password login: 50 faculty, 200 students, fictional | Agreed idea A, deck F1 |
| R9 | Assignment visibility follows semester / section / subject mapping | Deck F1 |
| R10 | Teacher-approved late request with reason, decision, note and limited window | Deck F5 |
| R11 | Deadline Integrity Timeline | Deck F4, slide 7 |
| R12 | In-app deadline alerts + faculty overview with real counts and status filters | Deck F6 (covers PS73 stretch) |
| R13 | Security: hashed passwords, server-side role and ownership checks, private files, server UTC timestamps | Project rules |

### 4.2 Assumptions [P]

| ID | Assumption |
|---|---|
| A1 | One college and one programme. Academic structure lives in tables (sections, subjects, teaching mappings), so it is configurable without code changes. |
| A2 | Every student in a section takes every subject of that section's semester. No per-student elective enrollment. |
| A3 | One faculty member teaches a given subject in a given section. |
| A4 | All times are stored in UTC and displayed in IST (Asia/Kolkata). |
| A5 | Demo users are fictional (Faker). Names do not match real people. |
| A6 | Supported upload types are PDF, DOCX, PPTX, ZIP, PNG and JPG. The size cap is ≤ 10 MB per file and configurable per assignment. |

---

## 5. Scope boundaries

**In scope** [C]: everything in §4.1.

**Explicitly out of scope** [C]:

- **Accounts and integrations:**
  - public sign-up, password reset, user or class administration screens (all users and mappings are seeded);
  - OAuth or SSO.
- **Not built at all:**
  - AI/ML, plagiarism checks, auto-grading, marks or grades;
  - chat, parent accounts, attendance;
  - multi-college tenancy.
- **Infrastructure:**
  - email, SMS, WhatsApp or push notifications;
  - Celery, cron, schedulers, message queues, websockets;
  - refresh tokens, Kubernetes, microservices.
- **Other:**
  - chart libraries (the overview uses number cards and filters);
  - editing or deleting submissions;
  - faculty overriding a timing status;
  - more than one late request per student per assignment;
  - bulk download.

---

## 6. Functional requirements

| FR | Behaviour | Role |
|---|---|---|
| FR-01 | Landing page offers **Faculty Login** and **Student Login** | Public |
| FR-02 | Login with ID + password. The account must exist, be active, have a matching hash, and have the role chosen on the landing page. | Both |
| FR-03 | Logout revokes the current token | Both |
| FR-04 | Student dashboard shows name, ID, semester, section, class label, subjects with their faculty, and assignments with deadline, remaining time, timing status, review status and feedback | Student |
| FR-05 | Faculty sees their teaching mappings (subject × section) | Faculty |
| FR-06 | Faculty creates an assignment: title, instructions, subject + section (from own mappings), deadline, allowed types, max size, publish now or save as draft | Faculty |
| FR-07 | Faculty publishes a draft | Faculty |
| FR-08 | Faculty changes the deadline of own published assignment, with an optional reason. The change is logged. | Faculty |
| FR-09 | Student uploads a file when eligible (§16.3). The server records the timestamp and creates a new version. | Student |
| FR-10 | Student sees own version history. Faculty sees each student's versions. Files are downloadable only by authorized users. | Both |
| FR-11 | Missing student submits one late request with a reason | Student |
| FR-12 | Faculty approves (with a window of 1–72 h, default 24 h, plus an optional note) or rejects (with an optional note) | Faculty |
| FR-13 | Student uploads within an approved window. The upload is classified as **Late (approved)**. | Student |
| FR-14 | Faculty records a review: Under review, Accepted or Revision requested, with feedback | Faculty |
| FR-15 | Deadline Integrity Timeline per student × assignment | Both (own data only for students) |
| FR-16 | Faculty overview: expected, on time, late, pending, missing, resubmitted, requests awaiting decision. Filter by assignment and status. All values are counted from the database. | Faculty |
| FR-17 | In-app alerts: due within 24 h, due within 3 h, missing, approved window closing or expired, request decided, feedback recorded. Faculty see new late requests. | Both |

## 7. Non-functional requirements

| NFR | Target |
|---|---|
| Reproducibility | `docker compose up --build` on a laptop with Docker starts the full stack with no cloud account |
| Correctness | Timing rules are covered by automated tests, including the exactly-at-deadline case and deadline changes |
| Security | Server-side authorization on every route, Argon2 hashes, private files, no secrets in Git, CORS limited to the frontend origin |
| Integrity | Versions, deadline changes, request decisions and reviews are insert-only |
| Performance | Adequate for 250 users on one laptop. List endpoints return < 500 ms locally. This is not a scale claim. |
| Usability | Clear status badges and loading, empty and error states. Works at laptop and phone widths. |
| Observability | Structured request logs without credentials, tokens or file contents. `/api/v1/health` reports DB, Redis and MinIO. |

---

## 8. User roles and permissions

### 8.1 Permission matrix [C]

| Action | Student | Faculty |
|---|---|---|
| View own profile and academic mapping | ✅ | ✅ (teaching mappings) |
| View assignments | Published, own section only | Own (created by them, in their mappings) |
| Create / publish assignment | ❌ 403 | ✅ for own subject × section only |
| Change deadline | ❌ 403 | ✅ own assignments only |
| Upload submission | ✅ own, when eligible | ❌ 403 |
| View or download versions | Own only | Students in own assignments only |
| Create late request | ✅ own, when MISSING | ❌ 403 |
| Decide late request | ❌ 403 | ✅ for own assignments only |
| Record review | ❌ 403 | ✅ for own assignments only |
| Faculty overview | ❌ 403 | ✅ own assignments only |
| Change role, mapping, timestamps or statuses directly | ❌ (no endpoint exists) | ❌ (no endpoint exists) |

### 8.2 How authorization is enforced [P]

Checks run in three layers, all on the server.

1. **Authentication** (`get_current_user` dependency):
   - verify the JWT signature and expiry;
   - check the `jti` against the Redis denylist;
   - load the user from PostgreSQL and require `is_active = true`.

   The role always comes from the **database row**. The token's role is a hint only.
2. **Role** (`require_role("FACULTY" | "STUDENT")`) on every router.
3. **Scope and ownership** in the service layer, using these rules:

| Resource | Rule |
|---|---|
| Assignment (student) | `assignment.section_id == student.section_id` and `status == PUBLISHED` |
| Assignment (faculty) | `assignment.created_by == me`, and a `teaching_assignment(me, subject, section)` exists |
| Submission / version / review | Its assignment passes the rule above. Students additionally require `submission.student_id == me`. |
| Late request | Student: `request.student_id == me`. Faculty: the request's assignment passes the faculty rule. |

**Response codes** [P]:

| Code | When |
|---|---|
| `401` | Missing, expired or revoked token |
| `403` | Wrong role for the route (e.g. a student calling a faculty endpoint) |
| `404` | A resource exists but is outside the caller's scope. Returned instead of 403 so record IDs cannot be probed. |
| `409` | A rule conflict, such as the deadline having passed or a request already existing |

The frontend hides controls the user cannot use. That is for usability only; the backend is the security boundary.

---

## 9. High-level architecture

A modular monolith [C]: one React SPA, one FastAPI service, PostgreSQL, Redis and MinIO.

```mermaid
flowchart LR
    subgraph Client["User layer"]
        B["Browser<br/>React 18 + TypeScript SPA"]
    end
    subgraph App["Application layer (FastAPI)"]
        R["Routers<br/>auth, student, faculty, files, notifications"]
        S["Services<br/>status engine, eligibility, late requests,<br/>reviews, timeline, alerts, storage"]
        D["Dependencies<br/>JWT auth, role guard, scope checks"]
    end
    subgraph Data["Data and storage layer"]
        PG[("PostgreSQL<br/>records and history")]
        RD[("Redis<br/>rate limits, token denylist")]
        MN[("MinIO<br/>private bucket: files")]
    end
    B -- "HTTPS/HTTP REST + Bearer JWT" --> R
    R --> D
    R --> S
    S -- "SQLAlchemy 2.0 / psycopg 3" --> PG
    D -- "denylist lookup" --> RD
    R -- "login rate limit" --> RD
    S -- "boto3 S3 API" --> MN
```

**Why a monolith:** one deployable backend owns every rule, which is the fastest design to build and test in 20 hours. Modules are separated by folder (§12), not by service.

---

## 10. Docker Compose architecture

### 10.1 Services [P]

| Service | Image / build | Responsibility | Internal address | Host port | Volume | Health check |
|---|---|---|---|---|---|---|
| `frontend` | `./frontend/Dockerfile` (Node 20: `npm ci` → `vite build` → `vite preview`) | Serves the built SPA | `frontend:5173` | `5173` | none | `wget -qO- http://localhost:5173` |
| `backend` | `./backend/Dockerfile` (Python 3.12-slim) | REST API. Runs the initializer, then Uvicorn. | `backend:8000` | `8000` | none | `GET /api/v1/health` |
| `postgres` | `postgres:16` | Relational data | `postgres:5432` | **none** | `pgdata` | `pg_isready -U $POSTGRES_USER` |
| `redis` | `redis:7` | Rate limits, denylist | `redis:6379` | **none** | `redisdata` | `redis-cli ping` |
| `minio` | `minio/minio` (`server /data`) | Object storage for files | `minio:9000` (S3 API); console 9001 not published | **none** | `miniodata` | `mc ready local`, falling back to `curl -f http://localhost:9000/minio/health/live` if `mc` is missing. Verify in Phase 1. |

Notes:

- **Only the frontend (5173) and backend (8000) are published to the host** [C].
- PostgreSQL, Redis and the MinIO API/console are reachable only on the Compose network.
- For debugging, a developer may add a git-ignored `docker-compose.override.yml` that binds Postgres to `127.0.0.1:5432`. It is never in the default file.
- **Containers address each other by service name** (`postgres`, `redis`, `minio`), never `localhost` [C]. `localhost:8000` appears only in the browser-side `VITE_API_BASE_URL`, because the browser runs on the host machine.
- File downloads stream through the backend, so the browser never needs to reach MinIO.
- **Frontend serving** [P]: `vite preview` serves the static build using Node and Vite, which are already in the stack. Nginx is not in the agreed stack and is not used. `vite preview` is adequate for a local demo, not for production; hosted deployment uses Vercel (§26.6).

### 10.2 Communication

```mermaid
flowchart TB
    U["Laptop browser"] -- "http://localhost:5173" --> FE["frontend<br/>vite preview :5173"]
    U -- "http://localhost:8000/api/v1<br/>Bearer JWT" --> BE["backend<br/>uvicorn :8000"]
    BE -- "postgresql+psycopg://postgres:5432" --> PG[("postgres :5432<br/>volume pgdata")]
    BE -- "redis://redis:6379/0" --> RD[("redis :6379<br/>volume redisdata")]
    BE -- "http://minio:9000 (S3, private bucket)" --> MN[("minio :9000<br/>volume miniodata")]
    subgraph net["Compose network: assignflow_net (internal)"]
        FE
        BE
        PG
        RD
        MN
    end
```

### 10.3 Startup, readiness and initialization [P]

1. `postgres`, `redis` and `minio` start.
2. `backend` declares `depends_on: {postgres, redis, minio: condition: service_healthy}`.
3. The backend does **not** rely on start order alone. Its entrypoint runs `python -m app.db.init_db`, which:
   1. **Waits** for PostgreSQL (`SELECT 1`), Redis (`PING`) and MinIO (`head_bucket` or `list_buckets`). It retries every 2 s for up to 60 s, then exits non-zero.
   2. **Takes a PostgreSQL advisory lock**, so two starts can never seed at the same time.
   3. **Runs migrations**: `alembic upgrade head`.
   4. **Seeds** academic structure and users idempotently (§13.5).
   5. **Ensures the MinIO bucket exists**: boto3 `head_bucket`, then `create_bucket` if absent. The bucket stays private and no public policy is ever set. This replaces a separate MinIO init container; `mc` is not needed.
   6. Releases the lock. The entrypoint then `exec`s `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
4. `frontend` depends on `backend: service_healthy`. This is for convenience; the SPA itself retries API calls.

**Restart and recovery:**

- Every service uses `restart: unless-stopped`.
- If PostgreSQL restarts, SQLAlchemy's `pool_pre_ping=True` discards dead connections.
- If Redis or MinIO is down, the affected endpoints return `503` (§19.3, §23) and `/health` shows which dependency failed.

**Persistence:**

- Named volumes survive `docker compose down` and container rebuilds.
- `docker compose down -v` deletes all data. It is the explicit reset command and the README warns about it.

### 10.4 Commands (to be documented in the README)

| Purpose | Command |
|---|---|
| First start or rebuild | `cp .env.example .env` → fill values → `docker compose up --build -d` |
| Logs | `docker compose logs -f backend` |
| Stop (keep data) | `docker compose down` |
| Full reset (deletes data) | `docker compose down -v` |
| Backend tests | `docker compose run --rm backend pytest` (uses the separate `assignflow_test` database, §24.4) |
| Load demo assignments | `docker compose exec backend python -m app.db.seeds.seed_demo` |

---

## 11. Technology stack and component responsibilities

Everything below is from the agreed stack [C] unless marked [P].

| Layer | Technology | Responsibility in AssignFlow |
|---|---|---|
| Frontend | React 18+, TypeScript, Vite | SPA, type-safe UI |
| | React Router | Public, student and faculty routes; route guards |
| | TanStack Query | Server state, caching, 60 s refetch for alerts and overview |
| | Axios | API client; attaches Bearer token; handles 401 centrally |
| | Tailwind CSS, shadcn/ui, Lucide React | Styling, accessible components, icons |
| | React Hook Form + Zod | Forms and client-side validation (a convenience only; the server re-validates) |
| | date-fns (+ `date-fns-tz` [Q4]) | Countdown, IST formatting |
| Backend | Python 3.12, FastAPI, Uvicorn | REST API |
| | Pydantic v2, pydantic-settings | Schemas; typed configuration from env |
| | python-multipart, filetype | Multipart uploads; content-based type detection (named in the deck's notes) |
| Auth / security | pwdlib (Argon2), PyJWT | Password hashing; HS256 access tokens, 2 h expiry |
| | Redis + SlowAPI | Per-IP login rate limit (SlowAPI) and per-ID failure counter plus `jti` denylist (direct Redis) |
| Data | PostgreSQL 16, psycopg 3, SQLAlchemy 2.0, Alembic | Schema, constraints, migrations |
| | Faker (`en_IN`, fixed seed) | Deterministic fictional names |
| Storage | MinIO, boto3 | Private S3-compatible object storage |
| Quality | pytest, FastAPI TestClient, Ruff, ESLint, Prettier | Tests, lint, format |
| DevOps | Docker, Docker Compose, Git + GitHub | Local environment, version control |
| Hosted (per deck, see X2) | Vercel, Railway (+ Redis), Supabase PostgreSQL + Storage | Optional hosted variant; config-only (§26.6) |

**Not used:** Node/Express backend, MongoDB, Firebase, Nginx, Celery, cron, websockets, chart libraries, AI APIs.

---

## 12. Application module design (backend)

| Module | Owns | Must not |
|---|---|---|
| `core/config.py` | `Settings` (pydantic-settings) | Read env anywhere else |
| `core/clock.py` | `now_utc()`: the **only** source of "now", overridable in tests | — |
| `core/security.py` | Hash and verify, JWT encode and decode | Touch the DB |
| `core/deps.py` | DB session, `get_current_user`, `require_role` | Contain business rules |
| `core/errors.py` | `AppError(code, http_status, message)` and the exception handlers | — |
| `db/models/*` | SQLAlchemy models (§14) | Contain business logic |
| `db/init_db.py`, `db/seeds/*` | Wait, lock, migrate, seed, bucket | Run in request paths |
| `schemas/*` | Pydantic request and response models | — |
| `services/status.py` | Pure timing and display-status functions (§15) | Do I/O |
| `services/eligibility.py` | Can this student upload now, and in which context? (§16.3) | — |
| `services/submissions.py` | Upload transaction, versioning | — |
| `services/late_requests.py` | Create, decide, derived EXPIRED | — |
| `services/reviews.py`, `services/deadlines.py` | Reviews; deadline changes plus history | — |
| `services/timeline.py` | Merge events into one ordered list | — |
| `services/alerts.py`, `services/notifications.py` | Computed alerts; stored event notifications | — |
| `services/overview.py` | Faculty counts via SQL aggregation | Hard-code numbers |
| `services/storage.py` | boto3 put, get, delete, bucket check | Know about users |
| `services/ratelimit.py`, `services/tokens.py` | Redis counters; denylist | — |
| `routers/*` | HTTP mapping, role guard | Contain rules beyond calling services |

---

## 13. Authentication and security

### 13.1 Login flow

```mermaid
sequenceDiagram
    actor U as User
    participant FE as React SPA
    participant API as FastAPI
    participant RD as Redis
    participant DB as PostgreSQL
    U->>FE: Choose Faculty or Student Login, enter ID + password
    FE->>API: POST /api/v1/auth/login {role, login_id, password}
    API->>RD: Check per-IP limit and per-ID failure counter
    alt Limit exceeded
        API-->>FE: 429 RATE_LIMITED (Retry-After)
    else Allowed
        API->>DB: SELECT user WHERE login_id = ?
        API->>API: Argon2 verify (dummy hash if user not found)
        alt Bad password, inactive, or role mismatch
            API->>RD: INCR fail counter (TTL 10 min)
            API-->>FE: 401 INVALID_CREDENTIALS (generic)
        else Valid
            API->>RD: DEL fail counter
            API-->>FE: 200 {access_token, expires_at, user}
            FE->>FE: Store token in sessionStorage, route by DB role
        end
    end
    FE->>API: Later requests: Authorization Bearer token
    API->>API: Verify signature and exp
    API->>RD: EXISTS deny:jti
    API->>DB: Load user, require active, role from DB
```

### 13.2 Rules [P]

- **Credentials:** Faculty ID and Student ID plus password only [C]. Date of birth is never used [C].
- **Generic failure message:**
  - The response is identical for an unknown ID, a wrong password, an inactive account, or a role mismatch, e.g. a student ID used on the faculty form.
  - When the ID doesn't exist, the server verifies against a dummy Argon2 hash so response timing does not reveal valid IDs.
- **JWT** [C]:
  - HS256 with `JWT_SECRET` (≥ 32 random bytes) from env.
  - Claims: `sub` (user UUID), `role`, `jti` (UUID4), `iat`, `exp = iat + 2 h`.
  - No refresh tokens [C]. After 2 h the user logs in again.
- **Token storage (browser):**
  - `sessionStorage`, so the session survives a page refresh but not closing the tab.
  - Trade-off: a Bearer token can be read by script if there is XSS. Mitigations: React escaping, no `dangerouslySetInnerHTML`, user text rendered as plain text.
  - Cross-site cookies were rejected because they break across the hosted domains (decided before the deck).
- **CORS:** `allow_origins = [FRONTEND_ORIGIN]` (e.g. `http://localhost:5173`); methods GET, POST, PATCH; headers Authorization and Content-Type. No wildcard.
- **Logging:** request method, path, status, duration and user UUID. Never passwords, tokens, file contents or full late-request reasons.
- **Headers:** downloads set `X-Content-Type-Options: nosniff` and `Content-Disposition: attachment`.

### 13.3 Redis-backed controls

Detailed in §19. In short:

- **Per-IP limit:** 10 login requests per minute (SlowAPI).
- **Per-ID failures:** 5 failures per login ID per 10 minutes, after which login returns 429.
- **Logout:** the token's `jti` is added to the denylist with TTL equal to its remaining lifetime.

### 13.4 Demo dataset [C, details P]

| Item | Proposed structure (fictional) |
|---|---|
| Programme | "B.E. Computer Science & Engineering" (one college, label configurable) |
| Semesters | 1, 3, 5, 7 (the odd-semester term matches the October date) |
| Sections | A, B per semester → **8 sections** (e.g. `CSE-3A`) |
| Students | **200** = 25 per section; IDs `STU0001`–`STU0200` |
| Subjects | 6 per semester → **24 subjects** (codes like `CS301`) |
| Teaching slots | 24 subjects × 2 sections = **48** (subject, section) slots |
| Faculty | **50**, IDs `FAC001`–`FAC050`. Slots 1–48 go one-to-one to `FAC001`–`FAC048`. `FAC049` and `FAC050` get no teaching slot and are documented as "unassigned" accounts, which proves faculty scope enforcement. |
| Names | Faker `en_IN` with `Faker.seed(73)`, so names are deterministic across rebuilds |

These numbers are proposals. The structure is data-driven, so changing it means editing the seed config only.

### 13.5 Seeding and demo credentials [P]

- **Idempotent:**
  - Each insert uses `INSERT … ON CONFLICT (natural key) DO NOTHING`. Natural keys: `login_id`, `subjects.code`, `(semester, section name)`, `(subject_id, section_id)`.
  - Runs under the advisory lock.
  - After seeding, the initializer asserts exactly 50 FACULTY and 200 STUDENT rows and fails loudly otherwise.
- **Passwords:**
  - All demo accounts use one demo-only password from `.env` (`SEED_DEMO_PASSWORD`). The README tells the team to set it; `.env.example` holds a placeholder only.
  - Each account gets its own Argon2 hash (unique salt). Hashing 250 accounts runs once, taking about 10–30 s on first start.
  - Plaintext is never stored or logged.
- **Judge access:**
  - The README holds a short "Demo accounts" table: one faculty (`FAC001`), that faculty's section, and 3 students in it. The password is given verbally or on the demo sheet, not committed to Git.
  - The UI labels the environment "Demo data — fictional accounts".
- **Demo assignments** (`seed_demo.py`, run manually):
  - Create a few assignments prefixed `[DEMO]`.
  - **No submissions with fabricated timestamps are seeded.** All submissions in the demo are real uploads timed by the server.

---

## 14. Database schema and ER diagram

### 14.1 Conventions [P]

- Primary keys are UUID v4 (`uuid` type).
- Timestamps are `timestamptz` in UTC with a DB default `now()`. Business timestamps (`uploaded_at`, `requested_at`, `decided_at`, `changed_at`) are written explicitly from `clock.now_utc()` so tests can control them.
- Enums are PostgreSQL enums created via Alembic.
- **Deletion policy:** no API deletes anything. Every FK is `ON DELETE RESTRICT`, so history cannot be erased by a cascade. Users are deactivated (`is_active = false`), never deleted.
- **Insert-only (never UPDATEd):** `submission_versions`, `deadline_changes`, `reviews`, `notifications` (except `read_at`). For `late_requests`, only the decision fields are written, once.

### 14.2 Entities

| Table | Purpose | Key fields | Constraints and indexes |
|---|---|---|---|
| `users` | Both roles | `id`, `login_id`, `full_name`, `role` (FACULTY/STUDENT), `password_hash`, `is_active`, `created_at`, `updated_at` | `UNIQUE(login_id)`; `CHECK role IN (…)` |
| `sections` | Class group = semester + section | `id`, `semester` (1–8), `name` ('A'), `label` ('CSE-3A') | `UNIQUE(semester, name)`, `UNIQUE(label)` |
| `subjects` | Subject offered in a semester | `id`, `code`, `name`, `semester` | `UNIQUE(code)` |
| `student_profiles` | Authoritative student mapping | `user_id` (PK, FK users), `section_id` (FK) | Index `section_id`. Must reference a STUDENT user (checked in seed and service). |
| `teaching_assignments` | Faculty authorization | `id`, `faculty_id` (FK users), `subject_id`, `section_id` | `UNIQUE(subject_id, section_id)` (A3); index `faculty_id`. Subject semester must equal section semester (seed check). |
| `assignments` | An assignment for one subject × section | `id`, `title` (≤ 150), `instructions` (≤ 5000), `subject_id`, `section_id`, `created_by` (FK users), `status` (DRAFT/PUBLISHED), `original_deadline`, `deadline`, `allowed_types` (text[]), `max_file_mb` (1–10), `published_at`, `created_at`, `updated_at` | Index `(section_id, status)`, `created_by`. `deadline` is the only mutable business field, and only via the deadline endpoint. |
| `deadline_changes` | Audit of every change | `id`, `assignment_id`, `old_deadline`, `new_deadline`, `changed_by`, `changed_at`, `reason` (≤ 500, nullable) | Index `(assignment_id, changed_at)` |
| `submissions` | One logical submission per student per assignment | `id`, `assignment_id`, `student_id`, `created_at`, `latest_version_no` (int) | **`UNIQUE(assignment_id, student_id)`** |
| `submission_versions` | Each upload, immutable | `id`, `submission_id`, `version_no`, `storage_key`, `original_filename`, `mime_type`, `size_bytes`, `sha256`, `uploaded_at` (server), `uploaded_by`, `deadline_at_upload`, `upload_context` (REGULAR / LATE_APPROVED / REVISION), `late_request_id` (nullable FK) | **`UNIQUE(submission_id, version_no)`**, `UNIQUE(storage_key)`; `CHECK (upload_context = 'LATE_APPROVED') = (late_request_id IS NOT NULL)` |
| `late_requests` | Late-submission permission | `id`, `assignment_id`, `student_id`, `reason` (20–1000), `requested_at`, `deadline_at_request`, `status` (PENDING/APPROVED/REJECTED), `decided_by`, `decided_at`, `decision_note` (≤ 500), `window_start`, `window_end` | **`UNIQUE(assignment_id, student_id)`** (one request per student per assignment); `CHECK` that decision fields are set iff status ≠ PENDING and window fields are set iff APPROVED; index `(assignment_id, status)` |
| `reviews` | Append-only review log | `id`, `submission_id`, `version_id` (the version reviewed), `reviewer_id`, `status` (UNDER_REVIEW/ACCEPTED/REVISION_REQUESTED), `feedback` (≤ 2000), `reviewed_at` | Index `(submission_id, reviewed_at DESC)`. The current review is the latest row; no row means NOT_REVIEWED. |
| `notifications` | Stored event notifications (§22) | `id`, `user_id`, `type`, `title`, `body`, `ref_type`, `ref_id`, `dedup_key`, `created_at`, `read_at` | **`UNIQUE(dedup_key)`**; index `(user_id, read_at, created_at DESC)` |

`EXPIRED` is a **derived** display state of an APPROVED request, not a stored status (§17.2). This avoids needing a background job.

### 14.3 ER diagram

```mermaid
erDiagram
    USERS ||--o| STUDENT_PROFILES : "has (students)"
    SECTIONS ||--o{ STUDENT_PROFILES : groups
    USERS ||--o{ TEACHING_ASSIGNMENTS : "teaches (faculty)"
    SUBJECTS ||--o{ TEACHING_ASSIGNMENTS : "taught in"
    SECTIONS ||--o{ TEACHING_ASSIGNMENTS : "taught to"
    USERS ||--o{ ASSIGNMENTS : creates
    SUBJECTS ||--o{ ASSIGNMENTS : for
    SECTIONS ||--o{ ASSIGNMENTS : targets
    ASSIGNMENTS ||--o{ DEADLINE_CHANGES : "audited by"
    ASSIGNMENTS ||--o{ SUBMISSIONS : receives
    USERS ||--o{ SUBMISSIONS : "submits (students)"
    SUBMISSIONS ||--|{ SUBMISSION_VERSIONS : "has versions"
    ASSIGNMENTS ||--o{ LATE_REQUESTS : "has requests"
    USERS ||--o{ LATE_REQUESTS : "requests (students)"
    LATE_REQUESTS |o--o{ SUBMISSION_VERSIONS : authorizes
    SUBMISSIONS ||--o{ REVIEWS : "reviewed in"
    SUBMISSION_VERSIONS ||--o{ REVIEWS : "version reviewed"
    USERS ||--o{ NOTIFICATIONS : receives

    USERS {
        uuid id PK
        string login_id UK
        string full_name
        enum role
        string password_hash
        bool is_active
    }
    SECTIONS {
        uuid id PK
        int semester
        string name
        string label UK
    }
    SUBJECTS {
        uuid id PK
        string code UK
        string name
        int semester
    }
    STUDENT_PROFILES {
        uuid user_id PK
        uuid section_id FK
    }
    TEACHING_ASSIGNMENTS {
        uuid id PK
        uuid faculty_id FK
        uuid subject_id FK
        uuid section_id FK
    }
    ASSIGNMENTS {
        uuid id PK
        string title
        uuid subject_id FK
        uuid section_id FK
        uuid created_by FK
        enum status
        timestamptz original_deadline
        timestamptz deadline
        int max_file_mb
    }
    DEADLINE_CHANGES {
        uuid id PK
        uuid assignment_id FK
        timestamptz old_deadline
        timestamptz new_deadline
        uuid changed_by FK
        timestamptz changed_at
    }
    SUBMISSIONS {
        uuid id PK
        uuid assignment_id FK
        uuid student_id FK
        int latest_version_no
    }
    SUBMISSION_VERSIONS {
        uuid id PK
        uuid submission_id FK
        int version_no
        string storage_key UK
        string sha256
        timestamptz uploaded_at
        timestamptz deadline_at_upload
        enum upload_context
        uuid late_request_id FK
    }
    LATE_REQUESTS {
        uuid id PK
        uuid assignment_id FK
        uuid student_id FK
        string reason
        enum status
        timestamptz window_start
        timestamptz window_end
    }
    REVIEWS {
        uuid id PK
        uuid submission_id FK
        uuid version_id FK
        uuid reviewer_id FK
        enum status
        string feedback
        timestamptz reviewed_at
    }
    NOTIFICATIONS {
        uuid id PK
        uuid user_id FK
        string type
        string dedup_key UK
        timestamptz read_at
    }
```

---

## 15. Assignment and deadline business rules

### 15.1 Three independent status dimensions [C]

| Dimension | Values | Stored or derived |
|---|---|---|
| Timing | PENDING, ON_TIME, LATE, MISSING (plus the qualifier "approved" when the first version came through a late request) | **Derived** at read time |
| Review | NOT_REVIEWED, UNDER_REVIEW, ACCEPTED, REVISION_REQUESTED | Latest `reviews` row (none = NOT_REVIEWED) |
| Request | NONE, PENDING, APPROVED, REJECTED, EXPIRED | Stored, plus EXPIRED derived |

Each pair of dimensions is independent. For example, **LATE + ACCEPTED** and **ON_TIME + REVISION_REQUESTED** are both valid.

### 15.2 Timing rules [C, policy P]

Let `D` be the assignment's **current** `deadline` and `now = clock.now_utc()`.

| Situation | Timing |
|---|---|
| No submission, `now ≤ D` | PENDING |
| No submission, `now > D` | MISSING |
| Version `v`: `v.uploaded_at ≤ D` | ON_TIME (**exactly at the deadline is ON_TIME**) |
| Version `v`: `v.uploaded_at > D` | LATE |

- **Submission-level timing (shown in rosters and counts)** [Q1]: the timing of the **first version**. This answers "was the work handed in on time?". Later versions never change it.
  - The **RESUBMITTED** badge is shown when `latest_version_no > 1`.
  - Each version's own timing and `upload_context` appear in history and the timeline.
  - If the first version's context is LATE_APPROVED, the display is **"Late (approved)"**. It is never ON_TIME just because a late request was approved [C].
- **No stored status column:** timing is computed in `services/status.py` (pure functions) and in SQL for counts. No teacher action is needed to move students from PENDING to MISSING.
- **Frontend display:** badges come from API fields (`timing`, `review_status`, `request_status`, `is_resubmitted`). The frontend never computes status itself; it only formats the countdown to `deadline`.

### 15.3 Deadline changes [C, policy P — flag Q2]

| Rule | Detail |
|---|---|
| Who | The assignment's creating faculty only, on a PUBLISHED assignment |
| Constraint | `new_deadline > now`. The deadline can't be moved into the past, so changes never retroactively make existing on-time work late or instantly create MISSING students. Extensions after the deadline has passed are allowed. |
| Recording | One transaction: insert `deadline_changes(old, new, changed_by, changed_at, reason)` and update `assignments.deadline`. `original_deadline` is never changed. |
| Effect on status | All timing is recomputed against the **current** deadline (consistent and simple). Example: after an extension, a LATE first version that falls before the new deadline shows ON_TIME. |
| History preserved | Every version keeps `deadline_at_upload`, and the timeline shows "Uploaded 18:05 IST · deadline at upload 18:00 · Late at upload; On time after deadline extended to 20:00 on …" |
| Requests | See §17.4 |

### 15.4 Publication

- A DRAFT assignment is visible only to its creator. Publishing sets `published_at`.
- A deadline must be at least 1 minute in the future at create or publish time. This allows the short-deadline live demo.
- Drafts cannot receive submissions.

---

## 16. Submission and versioning

### 16.1 Upload sequence

```mermaid
sequenceDiagram
    actor S as Student
    participant FE as React SPA
    participant API as FastAPI
    participant MN as MinIO
    participant DB as PostgreSQL
    S->>FE: Choose file, click Submit (button disabled while pending)
    FE->>API: POST /student/assignments/{id}/submissions (multipart)
    API->>API: Auth, role STUDENT, assignment in own section and published
    API->>API: Stream file, enforce size cap, detect type by content, compute SHA-256
    API->>API: received_at = clock.now_utc() (official time)
    API->>DB: Eligibility check at received_at (deadline, review state, late window)
    alt Not eligible or invalid
        API-->>FE: 409/413/415/422 with error code
    else Eligible
        API->>MN: put_object(private key)
        alt Storage error
            API-->>FE: 503 STORAGE_UNAVAILABLE (no DB row written)
        else Stored
            API->>DB: BEGIN, upsert submission, lock row FOR UPDATE
            API->>DB: Reject if sha256 equals latest version (duplicate)
            API->>DB: INSERT version (version_no = latest + 1, uploaded_at = received_at)
            API->>DB: COMMIT
            alt DB failure or duplicate
                API->>MN: delete_object (best effort)
                API-->>FE: 409 DUPLICATE_UPLOAD or 500
            else Committed
                API-->>FE: 201 {version_no, uploaded_at, timing, upload_context}
            end
        end
    end
```

### 16.2 Rules [P]

- **Official time:**
  - `received_at` is captured once, after the whole file has been received and validated.
  - That one value is used for eligibility, for `uploaded_at` and for timing.
  - The browser's clock is never sent or used [C].
- **Versioning:**
  - `version_no = latest_version_no + 1`, allocated under `SELECT … FOR UPDATE` on the submission row.
  - `UNIQUE(submission_id, version_no)` guarantees no two versions collide.
  - Versions are never updated or deleted [C].
- **Current version:** `submissions.latest_version_no` identifies it; older versions stay listed.
- **Duplicate clicks:**
  - The frontend disables Submit while the request is in flight.
  - The backend returns `409 DUPLICATE_UPLOAD` if the new file's SHA-256 equals the latest version's, so an accidental double submit creates no extra version.
- **Concurrent first upload:** the submission row is created with `INSERT … ON CONFLICT (assignment_id, student_id) DO NOTHING`, then locked.

### 16.3 Upload eligibility (evaluated at `received_at`) [P — flag Q3]

| # | Condition | Result | `upload_context` |
|---|---|---|---|
| 1 | Assignment not published, or not in the student's section | 404 | — |
| 2 | Latest review is ACCEPTED | 409 `SUBMISSION_ACCEPTED` | — |
| 3 | `received_at ≤ deadline` | Allowed | REGULAR |
| 4 | After deadline and latest review is REVISION_REQUESTED | Allowed (faculty-requested revision) | REVISION |
| 5 | After deadline, **no submission yet**, own late request APPROVED and `window_start ≤ received_at ≤ window_end` | Allowed | LATE_APPROVED (links `late_request_id`) |
| 6 | After deadline, student already has a submission (not in revision) | 409 `DEADLINE_PASSED`. Replacing after the deadline needs the faculty to request a revision. | — |
| 7 | After deadline, otherwise | 409 `DEADLINE_PASSED` (UI offers "Request late submission" when MISSING) | — |

Additional rules:

- Within an approved window, the first upload creates the submission. Further uploads in the same window are allowed as new LATE_APPROVED versions.
- When a new version is uploaded, the review for it starts as NOT_REVIEWED. The previous review remains in history attached to the earlier version.

---

## 17. Late-submission request workflow (primary differentiator)

### 17.1 Sequence

```mermaid
sequenceDiagram
    actor St as Student
    participant API as FastAPI
    participant DB as PostgreSQL
    actor Fa as Faculty
    Note over St,API: Deadline passed and no submission, so timing is MISSING
    St->>API: POST /student/assignments/{id}/late-request {reason}
    API->>DB: Check MISSING, no existing request (UNIQUE)
    API->>DB: INSERT late_request PENDING, notify faculty
    API-->>St: 201 PENDING
    Fa->>API: GET /faculty/late-requests?status=PENDING
    Fa->>API: POST /faculty/late-requests/{rid}/decision
    alt APPROVE with window_hours
        API->>DB: UPDATE where status = PENDING: APPROVED, window [now, now + h]
        API->>DB: Notify student (dedup key)
        St->>API: Upload within window
        API->>DB: Version context LATE_APPROVED, timing LATE (approved)
        Fa->>API: Review: Accepted or Revision requested
    else REJECT
        API->>DB: UPDATE where status = PENDING: REJECTED, notify student
        Note over St: Remains MISSING, no further request allowed
    end
```

### 17.2 State transitions [P]

```mermaid
stateDiagram-v2
    [*] --> PENDING: student submits reason (only while MISSING)
    PENDING --> APPROVED: assigned faculty approves with window
    PENDING --> REJECTED: assigned faculty rejects
    APPROVED --> USED: upload inside window (derived label)
    APPROVED --> EXPIRED: window_end passed with no upload (derived)
    REJECTED --> [*]
    USED --> [*]
    EXPIRED --> [*]
```

`USED` and `EXPIRED` are **derived for display** from `status = APPROVED`, `window_end` and whether a linked LATE_APPROVED version exists. Nothing is stored and no background job is needed.

### 17.3 Policies [P — flag Q3]

| Case | Behaviour |
|---|---|
| Who can request | A student whose own timing for the assignment is MISSING. A student who already submitted cannot request. |
| Reason | Required, 20–1000 characters, stored as plain text |
| Repeated requests | One request per student per assignment (`UNIQUE`). A second attempt returns `409 REQUEST_EXISTS`. |
| Double click or retry | The UNIQUE constraint makes the request idempotent; the second call gets 409 and the UI shows the existing request |
| Who decides | Only the faculty who manages the assignment. A student calling the endpoint gets 403. |
| Decision race (two tabs) | Conditional update `WHERE status = 'PENDING'`. If 0 rows change, return `409 ALREADY_DECIDED`. |
| Approve | `window_hours` 1–72 (default 24). Window = `[decided_at, decided_at + window_hours]`. Optional note. |
| Reject | Optional note. Final: student stays MISSING. |
| Approved but no upload | After `window_end`: request shown EXPIRED, student stays MISSING, no new request |
| Already submitted, wants to replace after deadline | Not via late request. Allowed only if faculty sets REVISION_REQUESTED (§16.3 rule 4). |
| Classification | A LATE_APPROVED upload keeps its real `uploaded_at` and the original/current deadline. It is shown "Late (approved)", never ON_TIME [C]. |

### 17.4 Deadline changed while a request exists [P]

- The request record is never modified by a deadline change. It keeps `deadline_at_request`.
- If the new deadline is in the future, the student is PENDING again and may upload normally (REGULAR, ON_TIME). A pending request can still be decided, but approval is unnecessary; the UI shows a note.
- If an approved window and an extended deadline overlap, an upload at or before the current deadline is REGULAR / ON_TIME, since rule 3 is checked before rule 5. This is a legitimate extension that applies to everyone.

### 17.5 Deadline Integrity Timeline

`services/timeline.py` merges these events for one student × assignment, sorted by time (ties broken by event order):

- `ASSIGNMENT_PUBLISHED` (with `original_deadline`)
- each `DEADLINE_CHANGED` (old → new, who, reason)
- `LATE_REQUESTED` (reason), `REQUEST_APPROVED` (window) or `REQUEST_REJECTED` (note)
- each `VERSION_UPLOADED` (no, filename, `uploaded_at`, `deadline_at_upload`, timing at upload, timing now, context)
- each `REVIEW_RECORDED` (status, feedback, version)
- derived `REQUEST_WINDOW_EXPIRED` and `DEADLINE_PASSED_NO_SUBMISSION` markers

It ends with a **"Why this status"** summary computed by the same status functions, e.g. "Late (approved): first upload 14 Oct 10:12 IST, 16 h after the 13 Oct 18:00 deadline, inside the window approved by FAC012."

---

## 18. File storage architecture (MinIO)

| Aspect | Design [P] |
|---|---|
| Bucket | `assignflow-submissions` (env `S3_BUCKET`), private, created by `init_db` via boto3; no bucket policy, so there is no anonymous access |
| Client | boto3 S3 client with `endpoint_url=http://minio:9000`, path-style addressing, credentials from env |
| Object key | `submissions/{assignment_id}/{student_id}/{uuid4}.{ext}`. It contains no user-supplied text, so path traversal or name collisions are impossible. |
| Allowed types | Per-assignment subset of {pdf, docx, pptx, zip, png, jpg}. A file must pass all three checks: (1) its extension is in the subset, (2) `filetype` content detection matches an allowed MIME, (3) for docx/pptx (ZIP containers), the archive contains `word/document.xml` / `ppt/presentation.xml`. |
| Size | Read in chunks and stop at `max_file_mb + 1 byte`, returning `413 FILE_TOO_LARGE`. Global hard cap 10 MB [P]. Empty files return 422. |
| Filename | `original_filename` is stored for display only, sanitized (basename, ≤ 200 chars, control characters stripped) |
| Integrity | SHA-256 stored per version (used for duplicate detection and shown in the timeline) |
| Download | `GET /api/v1/files/versions/{version_id}` runs the scope checks in §8.2, then streams via `get_object`. No presigned or public URLs [C]. |
| DB/storage consistency | Upload order is: validate → put object → DB transaction. On DB failure the object is deleted (best effort). If that delete also fails, the object is an orphan: harmless because nothing references it, and it is listed by `scripts/find_orphans.py` (dry-run report; deletion is a manual flag). A committed DB row always points to an object that was stored successfully. If storage is down, upload returns 503 and nothing is written. |
| Backup and reset | Data lives in the `miniodata` volume and `down -v` resets it. No backup tooling is in scope. |

---

## 19. Redis usage

### 19.1 Keys [P]

| Purpose | Key | Value / TTL |
|---|---|---|
| Per-IP login limit | SlowAPI-managed (`LIMITER_STORAGE=redis://redis:6379/0`) | 10 requests per minute per IP on `/auth/login` |
| Per-ID failed logins | `rl:loginfail:{role}:{login_id}` | `INCR`; `EXPIRE 600` on first failure; at ≥ 5 → 429 with `Retry-After = TTL`; deleted on success |
| Token denylist | `deny:jti:{jti}` | `"1"` with TTL = `exp − now` (≤ 7200 s), so entries clean themselves up |

Redis holds no passwords, names or file data.

### 19.2 Token validation order

1. Signature.
2. `exp`.
3. `EXISTS deny:jti:{jti}` (revoked → 401 `TOKEN_REVOKED`).
4. User loaded from DB and active.

### 19.3 Redis unavailable [P]

The system **fails closed**:

- login returns `503 SERVICE_UNAVAILABLE`;
- authenticated requests return 503, because revocation cannot be verified;
- `/health` reports `redis: down`.

This is acceptable because Redis is a local container with `restart: unless-stopped`. The demo checklist includes verifying `/health`. Fail-open would silently re-enable logged-out tokens and skip rate limits, so it was rejected.

---

## 20. API contracts

### 20.1 Conventions [P]

- **Base URL:** `/api/v1`. JSON throughout, except the upload (multipart) and download (binary).
- **Auth:** `Authorization: Bearer <jwt>` on everything except `/auth/login` and `/health`.
- **Timestamps:** ISO-8601 UTC (`2026-10-11T12:30:00Z`); the UI converts them to IST.
- **Error envelope**, for all errors including validation:

```json
{ "error": { "code": "DEADLINE_PASSED", "message": "The deadline for this assignment has passed.", "details": {} } }
```

**Status codes:**

| Code | Meaning |
|---|---|
| 401 | Unauthenticated |
| 403 | Wrong role |
| 404 | Not found or out of scope |
| 409 | Business-rule conflict |
| 413 | File too large |
| 415 | Wrong type |
| 422 | Validation (FastAPI errors reshaped into the envelope) |
| 429 | Rate limited |
| 503 | Dependency down |

### 20.2 Endpoints

| # | Method & path | Role | Purpose / request → response | Key errors |
|---|---|---|---|---|
| **Auth** |||||
| 1 | `POST /auth/login` | Public | `{role, login_id, password}` → `{access_token, token_type, expires_at, user:{id, login_id, full_name, role}}` | 401 INVALID_CREDENTIALS, 429 |
| 2 | `POST /auth/logout` | Any | Denylist the current `jti` → 204 | 401 |
| 3 | `GET /auth/me` | Any | Profile. Student: `section{label, semester, name}` and `subjects[{code, name, faculty_name}]`. Faculty: `teaching[{subject, section}]`. | 401 |
| **Faculty: assignments and deadlines** |||||
| 4 | `GET /faculty/assignments` | Faculty | Own assignments with counts (same shape as #13) | — |
| 5 | `POST /faculty/assignments` | Faculty | Create (body below) → 201 assignment | 403 NOT_YOUR_CLASS (subject × section not in own mappings); 422 deadline < now + 1 min |
| 6 | `POST /faculty/assignments/{id}/publish` | Faculty | DRAFT → PUBLISHED | 404, 409 ALREADY_PUBLISHED, 422 deadline passed |
| 7 | `GET /faculty/assignments/{id}` | Faculty | Detail + deadline history | 404 |
| 8 | `PATCH /faculty/assignments/{id}/deadline` | Faculty | `{new_deadline, reason?}` → assignment + new history row | 404, 409 NOT_PUBLISHED, 422 DEADLINE_IN_PAST |
| 9 | `GET /faculty/assignments/{id}/roster?status=` | Faculty | One row per expected student: `{student, timing, is_resubmitted, version_count, latest_uploaded_at, review_status, request_status}`; filter by status | 404 |
| 10 | `GET /faculty/assignments/{id}/students/{student_id}/timeline` | Faculty | Versions + timeline events + "why this status" | 404 |
| 11 | `POST /faculty/submissions/{submission_id}/reviews` | Faculty | `{status, feedback}` → review (targets the latest version) | 404, 422 |
| 12 | `GET /faculty/late-requests?status=PENDING` | Faculty | Requests on own assignments | — |
| 13 | `GET /faculty/overview?assignment_id=` | Faculty | Counts (below) | 404 |
| 14 | `POST /faculty/late-requests/{id}/decision` | Faculty | `{decision: APPROVE\|REJECT, note?, window_hours?}` | 404, 409 ALREADY_DECIDED, 422 |
| **Student** |||||
| 15 | `GET /student/assignments` | Student | Published assignments for own section: `{id, title, subject, faculty_name, published_at, deadline, timing, review_status, latest_feedback, request_status, is_resubmitted}` | — |
| 16 | `GET /student/assignments/{id}` | Student | Detail + own versions + own request + reviews + timeline | 404 |
| 17 | `POST /student/assignments/{id}/submissions` | Student | multipart `file` → 201 version | 404, 409 DEADLINE_PASSED / SUBMISSION_ACCEPTED / DUPLICATE_UPLOAD, 413, 415, 503 |
| 18 | `POST /student/assignments/{id}/late-request` | Student | `{reason}` → 201 request | 404, 409 NOT_MISSING / REQUEST_EXISTS, 422 |
| **Shared** |||||
| 19 | `GET /files/versions/{version_id}` | Both (scoped) | Binary stream, `Content-Disposition: attachment` | 404, 503 |
| 20 | `GET /notifications` | Both | `{alerts:[computed], items:[stored], unread_count}` | — |
| 21 | `POST /notifications/{id}/read` | Both (own) | → 204 | 404 |
| 22 | `GET /health` | Public | `{status, db, redis, storage}`; 200 or 503 | — |

Endpoint 3 also gives faculty their subject × section list for the create form. That is the whole surface: **22 endpoints**, each tied to a deck feature (§28).

### 20.3 Representative payloads

**Create assignment** (#5):

```json
// request
{ "title": "DBMS Lab 4 – Normalization", "instructions": "Upload your report as PDF.",
  "subject_id": "7c1…", "section_id": "2b9…", "deadline": "2026-10-11T12:30:00Z",
  "allowed_types": ["pdf"], "max_file_mb": 5, "publish": true }
// 201
{ "id": "a41…", "status": "PUBLISHED", "deadline": "2026-10-11T12:30:00Z",
  "original_deadline": "2026-10-11T12:30:00Z", "section": "CSE-5A", "subject": "CS503 Database Systems" }
```

**Upload result** (#17):

```json
{ "submission_id": "s88…", "version_no": 2, "uploaded_at": "2026-10-11T12:31:07Z",
  "deadline_at_upload": "2026-10-11T12:30:00Z", "upload_context": "REGULAR",
  "version_timing": "LATE", "submission_timing": "ON_TIME", "is_resubmitted": true }
```

**Late-request decision** (#14):

```json
// request
{ "decision": "APPROVE", "window_hours": 24, "note": "Medical certificate seen." }
// 200
{ "id": "r12…", "status": "APPROVED", "decided_at": "2026-10-12T05:00:00Z",
  "window_start": "2026-10-12T05:00:00Z", "window_end": "2026-10-13T05:00:00Z" }
```

**Overview** (#13): every value comes from SQL aggregation over `student_profiles`, `submissions`, `submission_versions` and `late_requests`.

```json
{ "assignment_id": "a41…", "expected": 25, "on_time": 18, "late": 3, "late_approved": 1,
  "pending": 0, "missing": 3, "resubmitted": 4, "requests_pending": 2, "reviewed": 10 }
```

Invariant (tested): `on_time + late + pending + missing = expected`. `late_approved` is a subset of `late`.

---

## 21. Frontend structure

### 21.1 Routes [P]

| Path | Page | Guard |
|---|---|---|
| `/` | Landing: Faculty Login / Student Login | Public |
| `/login/faculty`, `/login/student` | Login form (RHF + Zod) | Public |
| `/student` | Dashboard: profile card, subjects, alerts, assignment list with status badges and countdown | STUDENT |
| `/student/assignments/:id` | Detail: instructions, upload, versions, request form or status, feedback, timeline | STUDENT |
| `/faculty` | Overview: number cards, filters, pending requests | FACULTY |
| `/faculty/assignments/new` | Create form | FACULTY |
| `/faculty/assignments/:id` | Roster with status filters, deadline change dialog, history | FACULTY |
| `/faculty/assignments/:id/students/:studentId` | Versions + download, review form, timeline | FACULTY |
| `/faculty/requests` | Late-request queue with approve/reject dialog | FACULTY |

### 21.2 Directory and responsibilities

```
frontend/src/
├── main.tsx              # React root, QueryClientProvider, RouterProvider
├── app/router.tsx        # Route table + RequireRole guard
├── api/
│   ├── client.ts         # Axios instance: baseURL from VITE_API_BASE_URL, Bearer header, 401 → logout
│   ├── types.ts          # TS types mirroring backend schemas
│   └── queries.ts        # TanStack Query hooks + query keys (one place)
├── auth/AuthContext.tsx  # token + user in sessionStorage; login/logout
├── components/
│   ├── ui/               # shadcn/ui generated components
│   ├── StatusBadge.tsx   # timing / review / request badges
│   ├── Countdown.tsx     # date-fns, IST
│   ├── Timeline.tsx      # Deadline Integrity Timeline
│   ├── FileUpload.tsx    # type/size hints, disabled while pending
│   └── NotificationBell.tsx
├── layouts/              # StudentLayout, FacultyLayout (nav + bell + logout)
├── pages/
│   ├── public/           # Landing, Login
│   ├── student/          # Dashboard, AssignmentDetail
│   └── faculty/          # Overview, AssignmentNew, AssignmentRoster, StudentSubmission, Requests
└── lib/                  # zod schemas, date formatting helpers
```

### 21.3 Behaviour rules [P]

- **TanStack Query:**
  - defaults `staleTime 30 s` and `retry 1`;
  - notifications and overview refetch every 60 s and on window focus;
  - mutations invalidate the related keys, so after an upload the assignment, overview and notifications refresh.
- **Every page has:**
  - a loading state (skeleton);
  - an empty state (e.g. "No assignments yet");
  - an error state that shows the API `error.message`;
  - success toasts on mutations.
- **Role-based UI:** students never see create, deadline, review or decision controls. This is for usability; the server enforces the rules.
- **Plain-text rendering:** user-supplied text (instructions, reasons, feedback) is rendered as text only.

---

## 22. Notification architecture

**No scheduler** [C]. There are two mechanisms.

1. **Computed alerts** are calculated on each `GET /notifications` from the server clock. They are not stored, so duplicates are impossible.

| Alert | Who | Condition |
|---|---|---|
| DUE_24H | Student | Published, own section, no submission, `now < deadline ≤ now + 24 h` (and not within 3 h) |
| DUE_3H | Student | Same, with `deadline ≤ now + 3 h` |
| MISSING | Student | `deadline < now`, no submission, no open approved window |
| WINDOW_CLOSING | Student | Approved request, no upload, `window_end ≤ now + 3 h` |
| WINDOW_EXPIRED | Student | Approved request, no upload, `window_end < now` |

2. **Stored event notifications** are inserted in the same transaction as the event. Each has a deterministic `dedup_key`, inserted with `ON CONFLICT DO NOTHING`.

| Event | Recipient | `dedup_key` |
|---|---|---|
| Late request created | Assignment's faculty | `LR_CREATED:{request_id}` |
| Request approved / rejected | Student | `LR_DECIDED:{request_id}` |
| Review recorded | Student | `REVIEW:{review_id}` |
| Deadline changed | Students in section | `DL_CHANGED:{change_id}:{student_id}` (25 rows per change) |

The bell shows `unread_count` from stored items. Computed alerts are shown as a "Needs attention" list. The frontend polls every 60 s; the deck states 30–60 s.

---

## 23. Error handling and data consistency

| Concern | Approach |
|---|---|
| Uniform errors | `AppError` subclasses map to the §20.1 envelope. Unexpected exceptions are logged with a request ID and return 500 `INTERNAL_ERROR` without stack traces. |
| Transactions | One DB transaction per mutating request (session dependency commits on success, rolls back on error) |
| Races | Unique constraints + `SELECT … FOR UPDATE` (versions) + conditional `UPDATE … WHERE status = 'PENDING'` (decisions) |
| Idempotency | Request (UNIQUE), decision (conditional), upload (SHA-256 duplicate check), notifications (`dedup_key`), seed (`ON CONFLICT`) |
| Storage vs DB | §18 order and compensation; orphan report script |
| Dependency down | DB down → 503 via health and the session error handler; Redis down → 503 (§19.3); MinIO down → upload/download 503 |
| Clock | Only `clock.now_utc()`. Container clocks follow the host; the demo never changes the system clock [C]. |

---

## 24. Testing strategy and acceptance criteria

### 24.1 Layers [P]

| Layer | Tooling | Focus |
|---|---|---|
| Unit | pytest | `services/status.py`, eligibility table, timeline ordering, window derivation, all with a frozen clock |
| API integration | pytest + TestClient against a real PostgreSQL test DB, Redis DB 1, and a MinIO test bucket | Auth, authz, workflows, error codes |
| Database | pytest | Constraints (unique version, unique request, CHECKs), seed counts, idempotent re-seed |
| Storage | pytest | Put/get/delete, type spoofing (a `.pdf` that is really a PNG → 415), size cap, unauthorized download |
| Frontend | `npm run lint` (ESLint), `npm run build` (`tsc` + Vite), Prettier check | Type and build correctness |
| End-to-end | Manual checklist (`docs/TEST_AND_DEMO_CHECKLIST.md`) in the browser on Docker Compose | The jury script (§29) |

**Clock control:** `app.dependency_overrides[get_now]` and the services' `clock` parameter let tests set "now" to exactly the deadline, one second before it, or one second after it, without sleeping or changing system time.

### 24.2 Acceptance tests

None of these has been run yet; no code exists.

| # | Test | Type |
|---|---|---|
| AT1 | Seed creates exactly 50 FACULTY + 200 STUDENT; a second run changes nothing | DB |
| AT2 | Valid faculty login → 200 + FACULTY | API |
| AT3 | Valid student login → 200 + STUDENT | API |
| AT4 | Wrong password / unknown ID / student ID on faculty form → identical 401; 6th failure → 429 | API |
| AT5 | Student `POST /faculty/assignments` → 403 | API |
| AT6 | Student A requests student B's assignment detail data or version file → 404 | API |
| AT7 | FAC049 (no slots) or FAC001 creating for another faculty's subject × section → 403; managing another's assignment → 404 | API |
| AT8 | Faculty creates assignment in own slot → 201; draft invisible to students until published | API |
| AT9 | Student in that section sees it; a student of another section does not | API |
| AT10 | Valid PDF upload → 201, version 1, server `uploaded_at` | API |
| AT11 | Upload at deadline − 1 s → ON_TIME | Unit + API |
| AT12 | Upload at exactly the deadline → ON_TIME | Unit + API |
| AT13 | Upload at deadline + 1 s via approved request → Late (approved); without permission → 409 | API |
| AT14 | No submission, now > deadline → MISSING; now ≤ deadline → PENDING | Unit + API |
| AT15 | Second upload → version 2; version 1 row and object intact; RESUBMITTED shown; identical file → 409 | API |
| AT16 | Deadline extension → history row (old, new, actor, time); `original_deadline` unchanged; timing recomputed; past `new_deadline` → 422 | API |
| AT17 | MISSING student creates request → 201; second → 409; non-missing student → 409 | API |
| AT18 | Owning faculty approves/rejects → 200; other faculty → 404; student → 403; second decision → 409 | API |
| AT19 | Upload inside approved window → 201 LATE_APPROVED | API |
| AT20 | Upload after `window_end` → 409; request shows EXPIRED | API |
| AT21 | Download of another student's version → 404; no token → 401; revoked token after logout → 401 | API |
| AT22 | Overview counts equal the counts from an independent SQL query on the fixture; buckets sum to expected | API |
| AT23 | Fresh clone → `cp .env.example .env` → `docker compose up --build` → full §29 script works offline, with no cloud account | E2E manual |
| AT24 | Review: Late + Accepted shown together; ACCEPTED blocks further upload; REVISION_REQUESTED allows after-deadline upload (REVISION) | API |
| AT25 | Upload with content not matching the extension → 415; > max size → 413 | Storage |

### 24.3 Running tests locally

- **Backend:** `docker compose run --rm backend pytest -q`. A fixture creates `assignflow_test` and runs migrations; Redis DB 1; bucket `assignflow-test`.
- **Lint:** `docker compose run --rm backend ruff check .`
- **Frontend:** `cd frontend && npm ci && npm run lint && npm run build` (or the same inside the frontend image).

---

## 25. Repository directory structure

```
assignflow/
├── architecture.md                # this blueprint (authoritative)
├── README.md                      # setup, Docker, env, seed, demo logins, tests, troubleshooting
├── .env.example                   # placeholders only
├── .gitignore                     # .env, node_modules, __pycache__, docker-compose.override.yml
├── docker-compose.yml             # frontend, backend, postgres, redis, minio + volumes + healthchecks
├── docs/
│   ├── DATABASE_SCHEMA.md
│   ├── API_DOCUMENTATION.md
│   ├── REQUIREMENTS_TRACEABILITY.md
│   ├── TEST_AND_DEMO_CHECKLIST.md
│   └── IMPLEMENTATION_LOG.md
├── backend/
│   ├── Dockerfile
│   ├── entrypoint.sh              # init_db then exec uvicorn
│   ├── pyproject.toml             # deps pinned; ruff + pytest config
│   ├── alembic.ini
│   ├── alembic/                   # env.py + versions/ (migrations)
│   ├── app/
│   │   ├── main.py                # app factory, CORS, routers, error handlers
│   │   ├── core/                  # config, clock, security, deps, errors, logging
│   │   ├── db/
│   │   │   ├── base.py, session.py
│   │   │   ├── models/            # users, academics, assignments, submissions, late_requests, reviews, notifications
│   │   │   ├── init_db.py         # wait → lock → migrate → seed → bucket (also MinIO initialization)
│   │   │   └── seeds/             # seed_config.py, seed_academics.py, seed_users.py, seed_demo.py
│   │   ├── schemas/
│   │   ├── services/
│   │   └── routers/               # auth, me, faculty, student, files, notifications, health
│   ├── scripts/find_orphans.py
│   └── tests/                     # conftest.py (test DB, clock, clients), unit/, api/
└── frontend/
    ├── Dockerfile
    ├── package.json, vite.config.ts, tsconfig.json, tailwind.config.ts, components.json
    ├── .eslintrc.cjs, .prettierrc
    └── src/                       # see §21.2
```

MinIO initialization lives in `backend/app/db/init_db.py`; there is no separate script or container.

---

## 26. Docker setup and environment configuration

### 26.1 `.env.example` (placeholders only) [P]

| Variable | Used by | Example placeholder |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | postgres, backend | `assignflow` / `change-me` / `assignflow` |
| `DATABASE_URL` | backend | `postgresql+psycopg://assignflow:change-me@postgres:5432/assignflow` |
| `REDIS_URL` | backend | `redis://redis:6379/0` |
| `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` | minio | `change-me` / `change-me-min-8-chars` |
| `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, `S3_REGION` | backend | `http://minio:9000` / … / `assignflow-submissions` / `us-east-1` |
| `JWT_SECRET` | backend | `generate-with: python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `JWT_EXPIRE_MINUTES` | backend | `120` |
| `FRONTEND_ORIGIN` | backend (CORS) | `http://localhost:5173` |
| `SEED_DEMO_PASSWORD` | init_db | `set-a-demo-password` |
| `MAX_UPLOAD_MB` | backend | `10` |
| `APP_TIMEZONE_DISPLAY` | frontend/backend | `Asia/Kolkata` |
| `VITE_API_BASE_URL` | frontend build arg | `http://localhost:8000/api/v1` |

`pydantic-settings` validates these at startup and fails fast with a clear message if any is missing.

### 26.2 Images

- **Backend:** `python:3.12-slim`. Install pinned deps from `pyproject.toml`, run as a non-root user, `ENTRYPOINT ["./entrypoint.sh"]`.
- **Frontend:** `node:20-alpine`. `npm ci`, then `vite build` with the `VITE_API_BASE_URL` build arg, then `vite preview --host 0.0.0.0 --port 5173`.

### 26.3 Volumes

`pgdata`, `redisdata`, `miniodata`. They persist across `down` and `up`, and are removed only by `down -v`.

### 26.4 Port exposure

Only 5173 and 8000 are published. The MinIO console is not published by default.

### 26.5 Local demo procedure

1. `docker compose up -d` at least 15 min before judging.
2. Check `GET http://localhost:8000/api/v1/health` shows all dependencies up.
3. Log in once with each demo account.
4. Keep a second browser profile (or incognito) open for the student, so the faculty and student sessions stay separate.

### 26.6 Hosted variant (only if the submitted deck commits to it — X2) [Q5]

The code is identical; only configuration changes.

| Setting | Hosted value |
|---|---|
| Frontend | Vercel build with `VITE_API_BASE_URL=https://<railway-app>/api/v1`, plus an SPA rewrite |
| Backend | Railway from `backend/Dockerfile`; the entrypoint runs `init_db` |
| `DATABASE_URL` | Supabase pooler string |
| `REDIS_URL` | Railway Redis |
| `S3_ENDPOINT_URL` / keys | Supabase Storage S3 endpoint + generated keys |
| `FRONTEND_ORIGIN` | The Vercel domain |

This is attempted only after the local demo passes the AT23 check (Phase 9).

---

## 27. Implementation phases and time estimates

Total **20 h**. About 25% is reserved for integration, testing and demo preparation [P]. With 3–4 people, the **frontend track runs in parallel** from Phase 3 onward against the API contract in §20.

| Phase | Objective | Key outputs | Tests / definition of done | Est. | Main risk |
|---|---|---|---|---|---|
| **0** Approval & repo check | Resolve §31; confirm the submitted deck; create traceability doc | `docs/REQUIREMENTS_TRACEABILITY.md`, empty repo layout | Every §28 row agreed | 0.5 h | Unresolved name or scope questions |
| **1** Docker foundation | Skeletons + Compose with 5 services, healthchecks, `.env.example`, `/health` | compose file, Dockerfiles, `main.py`, Vite app | `up --build` is healthy; `/health` reports db, redis and storage ok; SPA loads | 2 h | Image or healthcheck quirks (MinIO), Docker on team laptops |
| **2** Database & seed | Models, first migration, `init_db`, idempotent seed, bucket creation | `models/*`, `alembic/versions/0001_*`, `seeds/*` | AT1; constraint tests | 2 h | Argon2 seed time; enum migrations |
| **3** Auth & authz | Login, logout, me; JWT; denylist; rate limits; role and scope deps | `routers/auth`, `core/security`, `deps` | AT2–AT5, AT21 (auth part) | 2 h | Redis integration |
| **4** Assignments | Create, publish, list (both roles), deadline change + history | `services/deadlines`, faculty/student routers | AT7–AT9, AT16 | 2 h | Scope checks |
| **5** Submission engine | Upload pipeline, eligibility, versions, status engine, download | `services/status`, `eligibility`, `submissions`, `storage` | AT10–AT15, AT21, AT25 | 3 h | File validation, transaction ordering |
| **6** Late requests | Create, decide, window, derived EXPIRED, LATE_APPROVED uploads | `services/late_requests` | AT13, AT17–AT20 | 2 h | Rule interactions (§16.3) |
| **7** Reviews, timeline, overview, notifications + UI integration | Reviews; timeline; overview SQL; alerts and stored notifications; all pages wired | `services/reviews`, `timeline`, `overview`, `alerts`; frontend pages | AT22, AT24; every page has loading, empty and error states | 3 h | Frontend integration volume |
| **8** Integration & testing | Full pytest run, lint/build, manual E2E, defect fixes, docs update | test report in `IMPLEMENTATION_LOG.md` | All AT pass; AT23 on a clean clone | 2.5 h | Late-found defects |
| **9** Demo readiness | Demo accounts sheet, `seed_demo`, rehearsals ×2, fallback check; hosted deploy only if X2 requires it | README demo section, `TEST_AND_DEMO_CHECKLIST.md` | Script §29 runs in ≤ 5 min twice in a row | 1 h | Hosted setup time (if any) |
| | | | | **20 h** | |

**Sequencing notes:**

- Phase 2 precedes 3 because login needs seeded users.
- The frontend login, layouts and dashboard shells can start in parallel with Phases 2–3.
- The frontend Phase 7 pages can start against stubbed TanStack hooks once the §20 types are written. Stubs are dev-only and are never in the demo build.

**If time runs short** [P]:

- Trim UI polish first.
- Hold Phase 8 and Phase 9 time; they are protected.
- No approved feature is dropped silently. Any cut is reported and agreed (§31).

---

## 28. Requirements traceability matrix

| Req | Deck feature / slide | Implementation | Test | Demo step (§29) |
|---|---|---|---|---|
| R1 Create assignments | F2 / s4–5 | #5–#7, `assignments` | AT8 | 2 |
| R2 Deadline changes | F2, F4 / s5 | #8, `deadline_changes` | AT16 | 8 |
| R3 Submission | F3 / s4–5 | #17, storage | AT10 | 4 |
| R4 Late/missing detection | F3 / s5 | `services/status` | AT11–AT14 | 4, 5, 6 |
| R5 Resubmission/versions | F4 / s5 | `submission_versions` | AT15 | 5 |
| R6 Status/history | F4 / s5, s7 | #9, #10, #16, Timeline | AT15, AT16 | 5, 9 |
| R7 Review + final status | PS workflow / s4 | #11, `reviews` | AT24 | 10 |
| R8 Roster login | F1 / s5 | #1–#3, seed | AT1–AT4 | 1, 3 |
| R9 Mapping-based visibility | F1 / s5, s7 | scope checks | AT6, AT7, AT9 | 3 |
| R10 Late requests | F5 / s5, s7 | #12, #14, #18 | AT17–AT20 | 6, 7 |
| R11 Timeline | F4 / s7 | `services/timeline` | AT16 | 9 |
| R12 Alerts + overview | F6 / s5 | #13, #20, #21 | AT22 | 3, 11 |
| R13 Security | s6, s8 | §13, §18, §19 | AT4–AT7, AT21, AT25 | 3 (role-blocked action) |
| Docker-first | brief §6 (deck: fallback) | §10 | AT23 | Setup |

---

## 29. Demonstration workflow (≈ 5 min)

All timestamps are live and server-recorded. The clock is never changed [C].

1. **Faculty login** (`FAC001`). The overview shows real counts.
2. **Create** "[DEMO] Lab 4" for `CSE-5A`, deadline **now + 4 min**, PDF only. Publish.
3. **Student A login** (second browser). Shows profile, section and subjects, and the new assignment (PENDING, countdown, DUE_3H alert). Optionally show that the student cannot reach `/faculty` and the API returns 403.
4. Student A uploads v1 → **ON_TIME**, server time shown.
5. Student A uploads v2 (different file) → **RESUBMITTED**; v1 is still downloadable.
6. Wait for the deadline. Talk through the overview while waiting. Student B (no upload) → **MISSING**. Student C uploading now → blocked with `DEADLINE_PASSED`.
7. Student B **requests late submission** with a reason. Faculty sees the request in the bell and queue, then **approves with a 1 h window**. Student B uploads → **Late (approved)**.
8. Faculty **extends the deadline**. The history shows old → new, who and when.
9. Open Student B's **Deadline Integrity Timeline**: original deadline → deadline passed → request → approval → upload → change, plus the "why this status" line.
10. Faculty reviews Student B → **Accepted** with feedback (Late + Accepted). Student B sees the feedback.
11. The overview counts have changed to match.

**Fallback:**

- If the live wait is risky, run steps 6–7 on a second `[DEMO]` assignment created at the start with a 2-min deadline.
- If the hosted variant fails, use the local Compose stack (it is the primary anyway).

---

## 30. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Name/scope mismatch with submitted deck (X1–X3) | High | Resolve in Phase 0 before any code |
| Docker issues on team laptops (RAM, Apple Silicon images) | High | Multi-arch official images; verify Docker on ≥ 2 laptops in Phase 1; document min 4 GB RAM for Docker |
| Status-rule mistakes | High | Pure status functions, clock injection, AT11–AT16 |
| Eligibility rule interactions | Medium | Single eligibility table (§16.3) implemented as one function with a test per row |
| Upload/DB inconsistency | Medium | §18 order + compensation + orphan report |
| Redis down = login down (fail-closed) | Medium | Restart policy, `/health` check in the demo checklist |
| Frontend integration takes longer than planned | High | Contract-first API (§20), parallel track, 3 h Phase 7, protected Phase 8 |
| Seed hashing slow or Faker drift | Low | One-time cost, fixed Faker seed, pinned versions |
| Hosted deployment consumes time | Medium | Local first; hosted only after AT23 passes (§26.6) |
| Demo wait time | Low | Short deadlines + pre-created fallback assignment |

---

## 31. Decisions requiring confirmation

| # | Question | Recommendation |
|---|---|---|
| **X1** | Which name is on the **submitted** deck: DueTrace or AssignFlow? | Use whatever was submitted. If it was DueTrace, either keep DueTrace in the UI or confirm a rename is allowed. |
| **X2 / Q5** | Did the submitted deck commit to Vercel / Railway / Supabase? | If yes: keep the §26.6 config-only hosted variant as Phase 9 work. If no: local Compose only. |
| **X3** | Upload the exact submitted PPTX/PDF to the project | Needed to finalize §28 |
| **Q1** | Roster timing = **first version** (recommended) or latest version? | First version: a revision requested by faculty after the deadline does not make an on-time student "late" |
| **Q2** | Deadline-change policy: current deadline governs; new deadline must be in the future; per-version `deadline_at_upload` snapshot | Approve as written |
| **Q3** | After-deadline policy: late request only when MISSING; one request per assignment; replacement after deadline only via faculty REVISION_REQUESTED; window 1–72 h, default 24 h | Approve as written. Note that the deck notes say "uploads need an approved late request (or faculty requesting a revision)", which matches. |
| **Q4** | Add `date-fns-tz` for IST formatting, or use built-in `Intl.DateTimeFormat` with `timeZone: 'Asia/Kolkata'`? | Use `Intl`, which adds no new dependency |
| **Q6** | Demo dataset shape: 4 semesters × 2 sections × 25 students, 24 subjects, 48 slots, FAC049–FAC050 unassigned | Approve, or give the real structure to mirror |
| **Q7** | Allowed file types {pdf, docx, pptx, zip, png, jpg}, cap 10 MB | Approve |
| **Q8** | Frontend served by `vite preview` in Docker (no Nginx) | Approve |
| **Q9** | Redis fail-closed | Approve |

---

## 32. Definition of done

AssignFlow is done only when **all** of the following hold:

1. A fresh clone with `.env` from `.env.example` and `docker compose up --build` gives all five services healthy, with no cloud account.
2. The §29 demo script runs end-to-end through the UI → API → PostgreSQL/MinIO, twice in a row.
3. AT1–AT25 have been **executed** and pass. Results are recorded in `docs/IMPLEMENTATION_LOG.md` with the command used.
4. Frontend lint and build pass. Ruff passes.
5. Every row of §28 has a working implementation, a passing test and a demo step. No feature exists outside it.
6. No hard-coded counts, mock responses or dead buttons remain. Demo data is labelled fictional and `[DEMO]`.
7. No secrets are in Git. `.env.example` holds placeholders only.
8. The README, `docs/*` and the presentation script match the actual behaviour.
