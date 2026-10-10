# AssignFlow

**Student Assignment Submission & Late Work Manager** — Team CODE24, CBC 2.0 Hackathon, Problem Statement 73.

AssignFlow keeps assignments, submissions, deadlines, reviews and late-work requests in one trustworthy place. The
**server** decides every status (on time, late, pending, missing); the browser clock is never used.

## Features (what exists)

- **Two roles.** Faculty create and manage assignments for the classes they teach; students see and submit work for
  their own section only. Authentication is JWT-based with Redis rate limiting and a token deny-list; every
  endpoint enforces role and ownership on the backend.
- **File assignments.** Title, instructions, deadline (entered and shown in IST, stored in UTC), allowed file types and
  size, optional PDF/PPT/PPTX reference materials (locked once published, with in-app View for PDF/PNG/JPEG and Download).
  Drafts can be edited, published, deleted (only if nothing refers to them) or, once published, **archived and restored**.
- **Quiz assignments.** Faculty build quizzes in the app (single choice, multiple select, true/false; marks; optional
  time limit); students take them once, the server grades them (all-or-nothing per question) and releases the answer key
  only after the deadline.
- **Submissions.** Every upload is an immutable version with its own deadline snapshot; content-type validation; private
  MinIO storage with authenticated downloads only.
- **Late-work requests.** A missing student can ask for a limited window; faculty approve or reject; the window is
  enforced by the server on every upload.
- **Reviews and timeline.** Append-only reviews (under review / accepted / revision requested) and a Deadline Integrity
  Timeline built from real records; a faculty Submission Health Board with subject/section filters.
- **Notifications.** Stored notifications with an unread badge on the bell for both roles: new submission (to the
  owning teacher), late requests and decisions, reviews, deadline changes, new quizzes, and a **24-hour deadline reminder**
  created by a backend scheduler (once per effective deadline). Computed "needs attention" alerts are shown too.
- **Public pages.** A landing page with scroll-animated feature cards, and redesigned student and faculty login pages
  with background videos.

## Technology stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, Argon2 password hashing |
| Database | PostgreSQL 16 |
| Cache / security | Redis 7 (rate limits, JWT deny-list) |
| File storage | MinIO (S3 API, private bucket) via boto3 |
| Frontend | React 18, TypeScript, Vite 6, React Router 7, TanStack Query, react-hook-form + zod, Framer Motion, lucide-react, plain CSS |
| Runtime | Docker Compose (backend, frontend, postgres, redis, minio) |

## Architecture overview

```
Browser (React SPA, :5173)  --HTTP/JSON-->  FastAPI backend (:8000, /api/v1)
                                              |-- PostgreSQL  (users, assignments, submissions, quizzes, notifications ...)
                                              |-- Redis       (rate limiting, token deny-list)
                                              `-- MinIO       (private submission and reference files)
```

Only ports 5173 (frontend) and 8000 (API) are published; the other services are internal to the Compose network.
Routers (`backend/app/routers`) call services (`backend/app/services`) that hold the business rules; models live in
`backend/app/db/models`, migrations in `backend/alembic/versions`. The blueprint is `architecture.md`; progress and
decisions are in `docs/IMPLEMENTATION_LOG.md`.

## Prerequisites

- **Docker Desktop** (Windows) installed and **running**. Allocate at least 4 GB RAM to Docker.
- PowerShell. Python/Node on the host are not required to run the stack.

## First-time setup (PowerShell, from the project root)

```powershell
Copy-Item .env.example .env
```

Edit `.env` and replace every `change-me…` / `CHANGE_ME…` placeholder. `.env` is git-ignored; never commit it.

- `POSTGRES_PASSWORD` must be identical to the password inside `DATABASE_URL`.
- `S3_ACCESS_KEY` / `S3_SECRET_KEY` must equal `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`.
- `MINIO_ROOT_PASSWORD` must be at least 8 characters.
- Use letters and digits only in passwords (special characters would need URL-encoding inside `DATABASE_URL`).
- **`SEED_DEMO_PASSWORD` is required.** It is the one demo-only password given to every seeded account. There is no default; startup fails with a clear message if it is missing. Share it with judges verbally — do not commit it.
- **`JWT_SECRET` is required (at least 32 random characters).** The API refuses to start with a missing, short or placeholder value. Generate one: `python -c "import secrets;print(secrets.token_urlsafe(48))"`. Changing it signs everyone out.
- `VITE_API_BASE_URL` is a **public, build-time** value baked into the frontend (`http://localhost:8000/api/v1`, never `http://backend:8000`). After changing it: `docker compose up --build -d frontend`.
- `FRONTEND_ORIGIN` is the CORS origin and must exactly match the URL in your browser.

> If you previously started the stack with different database or MinIO credentials, the existing volumes keep the
> *old* credentials and the new ones will be rejected. For a one-time reset of a throwaway dev setup:
> `docker compose down -v` (**this deletes all data**).

## Start, status, stop

```powershell
docker compose config --quiet            # validate configuration
docker compose up --build -d             # build and start all five services
docker compose ps                        # all five should become "healthy"
docker compose logs -f backend           # follow logs (also: frontend, postgres, redis, minio)
docker compose down                      # stop; data volumes are KEPT
```

`docker compose down -v` **deletes all data volumes** (pgdata, redisdata, miniodata). Use it only for a deliberate full reset.

## What happens when the backend starts (Phase 2)

`backend/entrypoint.sh` runs `python -m app.db.init_db` before starting the API:

1. Waits for PostgreSQL, Redis and MinIO (retry every 2 s, give up after 60 s with a non-zero exit).
2. Takes a PostgreSQL advisory lock so two starts cannot migrate/seed at once.
3. Runs `alembic upgrade head`.
4. Seeds sections, subjects, the configured faculty and students (15 faculty, 50 students in CSE-5A/5B/5C), student profiles and teaching slots, then verifies the counts. A database seeded earlier with a different dataset is reported, never silently changed (see the dataset transition note below).
5. Creates the private `assignflow-submissions` bucket if it does not exist (no public policy is ever set).

It is idempotent: restarting creates no duplicates and does not re-hash existing passwords. The very first start takes
roughly 15–30 s (hashing the demo passwords with Argon2); later starts take about a second.

## Demo accounts (fictional)

Password for every account: the `SEED_DEMO_PASSWORD` you set in `.env`.

| Role | Login ID | Notes |
|---|---|---|
| Faculty | `FAC001` | Teaches CS503 Database Systems in **CSE-5A** (the demo class) |
| Students (CSE-5A) | `STU0101`, `STU0102`, `STU0103` | Section CSE-5A (17 students) |
| Other faculty / sections | `FAC002`..`FAC015`, `STU0118`.. (CSE-5B), CSE-5C | Used to check that scope is enforced |

## Signing in (Phase 3)

Open http://localhost:5173 and choose **Faculty Login** or **Student Login**. Enter the ID (e.g. `FAC001`, `STU0101`;
case-insensitive) and the demo password. The ID must be used on the matching form. You land on a profile page that
shows what `GET /api/v1/auth/me` returns (students: section and subjects; faculty: classes taught). Log out revokes the
token in Redis. The token is kept in `sessionStorage` (survives refresh, not closing the tab) and expires after 2 hours.

Limits: 10 login requests per minute per client IP, and after 5 failed attempts for one ID the account form returns
HTTP 429 for 10 minutes (a correct password does not bypass it). If Redis is down, login and all authenticated
requests return HTTP 503 (fail closed).

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/auth/login` | `{role, login_id, password}` → token + user |
| `GET /api/v1/auth/me` | profile and academic mapping |
| `POST /api/v1/auth/logout` | revoke the current token (204) |

## Assignments (Phase 4)

Faculty (`FAC001` teaches CS503 in CSE-5A): **New assignment** → choose the class, title, instructions, deadline (entered
and shown in **IST**), allowed file types and size → **Create and publish** or **Save as draft**. A draft can be edited and
published; once published, only the deadline can change (**Change deadline**, with an optional reason). Every change is
kept in the deadline history. Students (e.g. `STU0101`) see published assignments of their own section only.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/faculty/assignments` | own assignments (subject, section, status, deadline, student count) |
| `POST /api/v1/faculty/assignments` | create (draft or publish) |
| `GET /api/v1/faculty/assignments/{id}` | detail + deadline history |
| `PATCH /api/v1/faculty/assignments/{id}` | edit a **draft** (not in the blueprint's endpoint table, see log) |
| `POST /api/v1/faculty/assignments/{id}/publish` | publish a draft |
| `PATCH /api/v1/faculty/assignments/{id}/deadline` | change a published deadline (new deadline must be in the future) |
| `GET /api/v1/student/assignments`, `GET /api/v1/student/assignments/{id}` | own-section published assignments |

Rules: deadlines must carry a UTC offset and are stored in UTC; at create/publish the deadline must be at least 1 minute
away; out-of-scope assignments return 404, a class you do not teach returns 403.

## Submissions (Phase 5)

Student: open an assignment → choose a file → **Submit**. Each upload becomes a new version (earlier versions and their
files are always kept); the page shows the status, the version history (with the deadline that applied to each version)
and a **Download** button. Faculty: the assignment page lists every student of the section with their status
(**Submissions**, filterable), and a student's page lists their versions with downloads.

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/student/assignments/{id}/submissions` | multipart `file` → 201 new version |
| `GET /api/v1/student/assignments/{id}` | now includes own `versions`, `timing`, `can_upload` |
| `GET /api/v1/faculty/assignments/{id}/roster?status=` | one row per student of the section |
| `GET /api/v1/faculty/assignments/{id}/students/{student_id}/timeline` | the student's versions (event timeline: Phase 7) |
| `GET /api/v1/files/versions/{version_id}` | authenticated download (owner student or the assignment's teacher) |

Rules: allowed types PDF, DOCX, PPTX, ZIP, PNG, JPG (`.jpeg` counts as JPG) limited by the assignment; the *content* must
match the extension (DOCX/PPTX must contain their main part); size limit = assignment limit, at most `MAX_UPLOAD_MB`
(10); an identical file to the latest version is rejected; after the deadline uploads are closed (409
`DEADLINE_PASSED`) unless faculty requested a revision. Exactly at the deadline counts as on time. The browser's clock
is never used. Files live in the **private** MinIO bucket under server-generated keys and are only served by the backend.

## Late requests (Phase 6)

Student: once the deadline has passed and nothing was submitted, the assignment page offers **Request late submission**
(reason of 20–1000 characters; one request per assignment). Faculty: **Late requests** in the top bar lists the requests
on their own assignments (with a pending count); open one to read the reason, then **Approve** (window of 1–72 hours,
default 24, optional note) or **Reject**. The approved student sees the window and can upload inside it; that upload is
recorded with its real time and shown as **Late (approved)**. After the window closes the request shows *Window
expired* and the assignment stays missing.

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/student/assignments/{id}/late-request` | `{reason}` → 201 pending request (409 `NOT_MISSING`, `REQUEST_EXISTS`) |
| `GET /api/v1/faculty/late-requests?status=&assignment_id=` | requests on own assignments |
| `GET /api/v1/faculty/late-requests/{id}` | one request with the student's current status and versions |
| `POST /api/v1/faculty/late-requests/{id}/decision` | `{decision: APPROVE or REJECT, note?, window_hours?}` (409 `ALREADY_DECIDED`) |

The server enforces the window on every upload (not the button), sets all times itself, and a decision can be made only
once.

## Reviews, timeline, health board, notifications (Phase 7)

- **Review:** on a student's page (faculty) record *Under review*, *Accepted* or *Revision requested* with feedback
  (required for a revision request). Reviews are an append-only log that applies to the latest version and never changes
  the timing status. *Accepted* closes uploads; *Revision requested* lets the student upload once after the deadline.
  A new version starts as *Not reviewed*; earlier reviews stay in history.
- **Timeline:** the student's page (and the student's own assignment page) shows the chronological history from real
  records (creation, deadline changes, request and decision, every version with its deadline snapshot, reviews) and a
  "Why" box.
- **Health board** (`/faculty/board`): counts per student, never per file, from SQL, filterable by assignment, subject,
  section, timing and review status. A student is in exactly one of on time / late / pending / missing.
- **Notifications:** the bell shows an unread count, "Needs attention" alerts computed from the server clock (due in
  24 h / 3 h, missing, window closing / expired) and stored notifications (new late request, decision, review, deadline
  change) with *Mark as read*. Each event notifies once, even if the action is retried.

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/faculty/submissions/{id}/reviews` | record a review |
| `GET /api/v1/faculty/overview`, `GET /api/v1/faculty/overview/students` | board counts and the students behind them |
| `GET /api/v1/notifications`, `POST /api/v1/notifications/{id}/read` | alerts, notifications, unread count, mark as read |

Storage housekeeping: `docker compose exec backend python scripts/find_orphans.py` reports objects that no version
references (add `--delete` to remove them).

## Tests and lint

```powershell
docker compose run --rm backend pytest        # 490+ tests: database, migrations, seed, init, MinIO, auth, scope, assignments, quizzes, submissions, late requests, reviews, board, notifications, reminders
docker compose run --rm backend ruff check .
cd frontend; npm ci; npm run lint; npm run format:check; npm run build
```

`pytest` points the process at Redis DB 1 (never the demo Redis DB). The backend image contains the tests, so rebuild
(`docker compose build backend`) after editing them.

Tests run against dedicated databases (`assignflow_test`, `assignflow_migtest`, `assignflow_inittest`), Redis DB 1 and the
`assignflow-test` bucket. They never touch the normal demo database. Required services (PostgreSQL, Redis, MinIO) start
automatically. Other useful commands:

```powershell
docker compose exec backend alembic current   # current migration revision
docker compose exec backend python -m app.db.init_db   # re-run initialization manually
```

## URLs

| What | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Health endpoint | http://localhost:8000/api/v1/health |
| API docs (FastAPI) | http://localhost:8000/docs |

Health returns HTTP 200 `{"status":"ok","db":"ok","redis":"ok","storage":"ok"}` when PostgreSQL, Redis and MinIO are
all reachable, and HTTP 503 (with the failing dependency marked `"down"`) otherwise.

PostgreSQL, Redis and MinIO are reachable only on the internal Compose network; they are not published to the host.

## Note on the MinIO image

The upstream `minio/minio` (Docker Hub) and `quay.io/minio/minio` images are no longer available. The Compose file uses
`pgsty/minio` pinned to `RELEASE.2026-08-04T00-00-00Z`: a **third-party, community-maintained build** of the MinIO server
(not an official MinIO image). Phase 2 verified it supports what the app needs: bucket create/head, put/get/head/delete
object, bucket policy/ACL inspection, and 403 on anonymous access.

## Dashboards and demo dataset

Students and faculty land on a light, card-based dashboard. All numbers come from the API; with no data they show empty states, and on API failure an error with Try again (never sample records).

The seeded demo dataset is **15 faculty (`FAC001..FAC015`) and 50 students (`STU0101..STU0150`)** in CSE-5A (17), CSE-5B (17) and CSE-5C (16), all fictional, with one Argon2 hash each from `SEED_DEMO_PASSWORD`. Moving an older 50/200 database to this dataset is a controlled step: `docker compose run --rm backend python -m app.db.transition_dataset` is a dry run; add `--apply` only after reviewing its report. See `docs/IMPLEMENTATION_LOG.md`.

Teachers can attach PDF, PPT or PPTX reference documents to a draft assignment (locked once published); students open them from the assignment page. Every file has **View** (in-app preview for PDF, PNG and JPEG; other types say they must be downloaded) and **Download** (the original file). Files are served only by authenticated endpoints from private storage.

Faculty can filter the dashboard, assignment list and health board by subject and section (only the classes they teach are offered; the server re-checks every filter). **Delete assignment** permanently removes an assignment only when no student work or history refers to it; otherwise the assignment and all its records are kept and the dialog explains why.

**Removing an assignment:** a draft can be deleted permanently (only while nothing refers to it). A published assignment is **archived** instead: it leaves students' active work, the dashboard counts and the health board, accepts no new work, and keeps every submission, review and file (students with a submission can still read it, faculty keep the roster and timeline). An archived assignment can be **restored** at any time with its original deadline.

## Quizzes, notifications and reminders

- **Quizzes:** on *New assignment* choose **Quiz Assignment**. Endpoints: `POST/GET/PUT /api/v1/faculty/quizzes`,
  `GET /faculty/quizzes/{id}/participation`, student `GET /student/quizzes/{id}`, `POST .../attempts`,
  `PUT /student/quiz-attempts/{id}/answers`, `POST .../submit`, `GET .../result`. One attempt per student; the server
  enforces the deadline and time limit and never sends the answer key while the quiz is being taken.
- **Notifications:** `GET /notifications`, `GET /notifications/unread-count`, `POST /notifications/{id}/read`,
  `POST /notifications/read-all`. The bell polls the count every 10 s while the tab is visible.
- **24-hour reminders:** a backend job (one pass per minute; set `REMINDER_SCHEDULER_ENABLED=false` to disable) notifies
  each student of the section who has not finished an assignment about 24 h before its current deadline, once per
  effective deadline.

## Troubleshooting

- *Backend refuses to start:* check `docker compose logs backend`; usually a missing `SEED_DEMO_PASSWORD` or a weak/missing
  `JWT_SECRET`.
- *Login fails with 429:* too many attempts; wait 10 minutes or restart Redis.
- *Frontend cannot reach the API / CORS errors:* `FRONTEND_ORIGIN` must equal the URL in the browser and
  `VITE_API_BASE_URL` must be host-reachable; rebuild the frontend after changing it.
- *Services unhealthy after changing credentials:* existing volumes keep the old credentials (see the note above).
- *Database dumps and uploads are never part of the repository* (`backups/` is git-ignored); create your own with
  `docker compose exec postgres pg_dump ...` before risky operations.
