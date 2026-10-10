# AssignFlow — Implementation Log

Records, per phase: what was done, commands run, tests and results, errors and fixes.
Rule (architecture §32 #3): a test is "passed" only if it was **executed**; record the command and output summary here.

Phase plan (from `architecture.md` §27): 0 Approval & repo check · 1 Docker foundation · 2 Database & seed · 3 Auth & authz · 4 Assignments · 5 Submission engine · 6 Late requests · 7 Reviews/timeline/overview/notifications + UI · 8 Integration & testing · 9 Demo readiness.

| Phase | Status | Completed | Approved by |
|---|---|---|---|
| 0 Approval & repo setup | Complete (decisions X1–X3, Q1–Q9 still unrecorded) | 2026-10-10 | User (proceeded to Phase 1) |
| 1 Docker foundation | Complete | 2026-10-10 | User (proceeded to Phase 2) |
| 2 Database & seed | Complete | 2026-10-10 | User (proceeded to Phase 3) |
| 3 Auth & authz | Complete | 2026-10-10 | User (verified faculty login; proceeded to Phase 4) |
| 4 Assignment management | Complete | 2026-10-10 | User (approved with three decisions; proceeded to Phase 5) |
| 5 Submission engine | Complete | 2026-10-10 | User (confirmed Q1 first-version timing, deadline snapshots and `.jpeg` as JPG; proceeded to Phase 6) |
| 6 Late requests | Complete | 2026-10-10 | User (approved; proceeded to Phase 7) |
| 7 Reviews, timeline, board, notifications | Complete | 2026-10-10 | User (approved; proceeded to Phase 8) |
| 8 Final testing and QA | Complete, awaiting user approval | 2026-10-10 | — |
| 9 | Not started | — | — |

---

## Phase 0 — Approval and repository setup

**Date:** 2026-10-10
**Scope:** documentation and folder structure only. No application code, Dockerfiles, models, migrations, compose file or frontend components.

### Actions
- Read `architecture.md` in full (1,366 lines).
- Created `.gitignore`.
- Created `docs/REQUIREMENTS_TRACEABILITY.md` (from §28, expanded with FR, NFR, AT and demo mappings).
- Created `docs/IMPLEMENTATION_LOG.md` (this file).
- Created the §25 directory skeleton; empty directories hold a `.gitkeep` placeholder.

### Commands
| Command | Purpose | Result |
|---|---|---|
| `mkdir -p` + `touch .gitkeep` over the §25 folders | Create layout | OK |
| `Get-FileHash architecture.md` (SHA-256) before and after | Prove blueprint unchanged | See verification below |

### Not created (deliberately deferred)
`README.md`, `.env.example`, `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `entrypoint.sh`, `pyproject.toml`, `alembic.ini`, frontend config files, and the other `docs/` files (`DATABASE_SCHEMA.md`, `API_DOCUMENTATION.md`, `TEST_AND_DEMO_CHECKLIST.md`). These are Phase 1+ deliverables or were not requested for Phase 0.

### Open decisions (architecture §1.1 and §31) — all unresolved
| # | Decision | Recommendation in blueprint |
|---|---|---|
| X1 | Submitted deck name: DueTrace or AssignFlow? | Use what was submitted |
| X2 / Q5 | Did submitted deck commit to Vercel/Railway/Supabase? | If yes, config-only hosted variant in Phase 9 |
| X3 | Provide submitted PPTX/PDF | Needed to finalize §28 |
| Q1 | Roster timing = first version or latest? | First version |
| Q2 | Deadline-change policy | Approve as written |
| Q3 | After-deadline / late-request policy | Approve as written |
| Q4 | `date-fns-tz` vs `Intl.DateTimeFormat` | `Intl` |
| Q6 | Demo dataset shape | Approve |
| Q7 | File types and 10 MB cap | Approve |
| Q8 | `vite preview`, no Nginx | Approve |
| Q9 | Redis fail-closed | Approve |

### Issues found
See `docs/REQUIREMENTS_TRACEABILITY.md` §7 (I1–I6), plus:
- Blueprint §25 names the root `assignflow/`; the actual folder is `AssignFlow`. No change made.
- Blueprint states the whole product name is AssignFlow while the draft deck is DueTrace (X1) — not changed; flagged.

### Verification
- `architecture.md` SHA-256 before and after: `464EB56AD7707FFFC928351057BC44D3D04D0CC8B18764EE40C7893BBEF5601C` (identical), 79,492 bytes.
- All files are inside `C:\Users\harsh\Desktop\AssignFlow`.
- No secrets in any created file.

### Errors and fixes
None so far.

---

## Phase 1 — Docker foundation and service skeletons

**Date:** 2026-10-10
**Scope:** five-service Compose environment + `GET /api/v1/health` + minimal React page. No models, migrations, seeds, auth, assignments, uploads or any later-phase feature. Git was not initialised; nothing pushed.

### Files created
`docker-compose.yml`, `.env.example`, `README.md`, `backend/{Dockerfile,.dockerignore,entrypoint.sh,pyproject.toml}`, `backend/app/{__init__.py,main.py}`, `backend/app/core/{__init__.py,config.py}`, `frontend/{Dockerfile,.dockerignore,package.json,package-lock.json,index.html,vite.config.ts,tsconfig.json,tsconfig.app.json,tsconfig.node.json}`, `frontend/src/{main.tsx,App.tsx,index.css,vite-env.d.ts}`.
Modified: this log only. `architecture.md` and `docs/REQUIREMENTS_TRACEABILITY.md` untouched.

### Versions chosen
| Item | Choice |
|---|---|
| Backend base | `python:3.12-slim`; fastapi ~0.115, uvicorn ~2, pydantic-settings ~2.7, psycopg[binary] ~3.2, redis ~5.2, httpx ~0.28 (compatible-release ranges; no lock file) |
| Frontend base | `node:20-alpine`; React 18.3.1, Vite ^6.4, TypeScript ~5.9, @vitejs/plugin-react ^4.7 (`package-lock.json` + `npm ci`) |
| postgres / redis | `postgres:16`, `redis:7` (`--appendonly yes`) |
| MinIO | **`pgsty/minio:RELEASE.2026-08-04T00-00-00Z`** — see deviation below |

### Deviation: MinIO image (needs your confirmation)
The blueprint's `minio/minio` no longer exists on Docker Hub (`pull access denied / repository does not exist`) and `quay.io/minio/minio` returns 401. I chose `pgsty/minio` (maintained fork of the MinIO server; reports `minio version RELEASE.2026-08-04…`, ships `curl`, `mc`, `bash`). The healthcheck uses `curl -fsS http://localhost:9000/minio/health/live` (verified working). Command and S3 API are unchanged (`server /data`). Alternative options: `bitnamilegacy/minio` (frozen, old) or `cgr.dev/chainguard/minio` (rolling `latest` only). Supply-chain note: this is a third-party image.

### Other decisions / notes
- Health body: `{status, db, redis, storage}` with `ok`/`down`; `status` is `ok` or `degraded`. The blueprint does not define the degraded wording — provisional.
- `DATABASE_URL` keeps the SQLAlchemy form (`postgresql+psycopg://`); the health check rewrites the prefix for plain psycopg.
- Compose volumes are declared `pgdata`, `redisdata`, `miniodata`; Compose prefixes them `assignflow_` on disk.
- No `.env` was created in the project (instructed not to invent credentials). Runtime tests used a temporary env file with random throwaway values stored outside the project and deleted afterwards.
- Phase 0 open decisions remain unresolved in the repo; none block Phase 1.

### Commands executed and results
| Command | Result |
|---|---|
| `docker --version`, `docker compose version`, `node -v`, `npm -v` | Docker 29.7.2, Compose v5.5.0, Node 22.15.0, npm 10.9.2 |
| `docker info` (first) | Daemon not running; launched Docker Desktop, daemon came up (8 GB) |
| `docker pull minio/minio`, `quay.io/minio/minio` | Failed (unavailable) |
| `docker pull pgsty/minio`; `docker run … sh -c 'command -v curl mc bash'` | OK; curl, mc, bash present |
| `npm install --package-lock-only`, `npm ci`, `npm run build` (host) | Passed: `tsc -b` + `vite build` OK, 0 vulnerabilities |
| `python tomllib` parse of `pyproject.toml` | OK, 6 dependencies |
| `docker compose --env-file .env.example config --quiet` | exit 0; also exit 0 with runtime env |
| `docker compose --env-file <temp> up --build -d` | Built and started; all five services reached **healthy** |
| `GET http://localhost:8000/api/v1/health` | HTTP 200 `{"status":"ok","db":"ok","redis":"ok","storage":"ok"}` |
| `GET http://localhost:5173` | HTTP 200, `<title>AssignFlow</title>` |
| CORS check with `Origin: http://localhost:5173` | `access-control-allow-origin: http://localhost:5173` |
| Headless Edge `--dump-dom http://localhost:5173` | React rendered AssignFlow page ("Development Foundation") |
| Stop redis / minio / postgres one at a time, probe health, restart | Each gave HTTP 503 with only that dependency `down` (≈4 s, bounded); returned to 200 after restart; server logs show dependency + exception class only |
| Frontend bundle scan for `POSTGRES|MINIO_|JWT|S3_SECRET|change-me` | 0 matches; bundle contains `http://localhost:8000/api/v1` |
| `docker compose exec backend id` | `uid=10001(appuser)` (non-root) |
| `docker compose down` | Containers/network removed; all three volumes preserved |

### Not verified
- The "Check backend health" **button** was not clicked in a real browser (page render and CORS header were verified, but not the in-browser fetch result states).
- Fresh-clone flow (AT23) not run; no `.env` copy flow exercised by the project's own `.env.example` (it was validated with `compose config` only, since it holds placeholders).
- Ruff lint not run. No automated tests exist yet (none required in Phase 1).
- Windows CRLF handling of `entrypoint.sh` is handled by `sed` in the Dockerfile; worked in this build (file was LF as written).

### Known issues / risks
- MinIO image provenance (above).
- Backend deps use ranges, not a lock; a rebuild later may pick newer minor versions.
- Health takes about 4 s to answer 503 when a container is stopped (DNS/connect timeout); acceptable with the 10 s healthcheck timeout.
- Unhealthy dependencies make the backend container report `unhealthy`, which also holds the frontend's `depends_on` at startup only (not at runtime).

### Later-phase features
Confirmed not implemented: models, migrations, seeds, auth, assignments, submissions, late requests, reviews, timeline, notifications, bucket creation.

---

## Phase 2 — Database schema, Alembic migration and demo-account seeding

**Date:** 2026-10-10
**Scope:** SQLAlchemy 2.0 models (12 tables), one Alembic migration, idempotent seed (50 faculty + 200 students), initializer with advisory lock, private MinIO bucket creation, 37 automated tests. No authentication, endpoints or any Phase 3+ feature. Git not initialised; nothing pushed.

### Files created
- `backend/alembic.ini`, `backend/alembic/{env.py,script.py.mako,versions/0001_initial_schema.py}`
- `backend/app/db/{__init__,base,session,init_db}.py`, `backend/app/db/models/{__init__,users,academics,assignments,late_requests,submissions,reviews,notifications}.py`
- `backend/app/db/seeds/{__init__,seed_config,seed_academics,seed_users,runner}.py`
- `backend/app/core/security.py` (Argon2 hash/verify only; no JWT), `backend/app/services/{__init__,storage}.py`
- `backend/tests/{__init__,conftest,helpers}.py`, `backend/tests/db/{__init__,test_migration,test_constraints,test_seed,test_init}.py`
- `docs/DATABASE_SCHEMA.md`

### Files modified
`backend/pyproject.toml` (new deps, pytest/ruff config), `backend/Dockerfile` (installs dev deps; copies alembic/tests/scripts), `backend/entrypoint.sh` (runs initializer; runs a given command directly when arguments are passed), `backend/.dockerignore` (tests now included), `backend/app/core/config.py` (initializer settings), `backend/app/main.py` (httpx log level), `docker-compose.yml` (backend healthcheck `start_period` 15 s to 90 s for first-run init), `.env.example` (SEED_DEMO_PASSWORD now required), `README.md`, `docs/REQUIREMENTS_TRACEABILITY.md` (partial status for R8/R9 + progress log only). `architecture.md` untouched.

### Dependencies added
sqlalchemy ~2.0, alembic ~1.14, pwdlib[argon2] ~0.2, faker **==40.43.0** (pinned so seeded names stay identical), boto3 ~1.35; dev: pytest ~8.3, ruff ~0.9 (installed in the image so `docker compose run --rm backend pytest` works). MinIO image unchanged from Phase 1: `pgsty/minio:RELEASE.2026-08-04T00-00-00Z` (third-party community build, not an official MinIO image; see README).

### Migration
`0001_initial_schema` was generated with `alembic revision --autogenerate --rev-id 0001` against an **empty** database, reviewed, and extended with explicit `DROP TYPE` for the five enums in `downgrade()`. It creates 12 tables + 5 enum types; every FK is `ON DELETE RESTRICT`.

### Commands executed and results
| Command | Result |
|---|---|
| `docker volume rm assignflow_pgdata assignflow_redisdata assignflow_miniodata` | Removed the three Phase 1 volumes (see "Volumes" note) |
| `docker compose up -d postgres redis minio`, then `alembic revision --autogenerate` in a one-off backend container | Migration file generated |
| `docker compose run --rm --no-deps backend pytest` (first run) | **37 passed** (28.7 s) |
| `docker compose up --build -d` (empty volumes) | Initializer log: migration `-> 0001` applied; `users created=250`; `verified 50 faculty, 200 students`; `bucket 'assignflow-submissions' created and is private`; all five services healthy |
| `docker compose restart backend` | `users created=0 already_present=250`; `bucket ... already exists and is private`; init finished in under 1 s |
| `psql` via `docker compose exec postgres` | faculty 50, students 200, sections 8, subjects 24, teaching_assignments 48, student_profiles 200, 250 `$argon2` hashes, 250 distinct hashes; tables = 12 + `alembic_version`; revision `0001`; only database `assignflow` present (test databases dropped) |
| FAC001 mapping query | FAC001 = CS503 Database Systems in CSE-5A; FAC048 = CS706 Project Phase I in CSE-7B; FAC049/FAC050 have 0 slots |
| Anonymous HTTP GET on bucket and object (from backend container) | 403 / 403 |
| `docker compose run --rm -e SEED_DEMO_PASSWORD= backend` | Exit code 1, "Missing required environment variables: SEED_DEMO_PASSWORD" |
| `docker compose run --rm --no-deps backend ruff check .` | All checks passed (after `ruff --fix`; explicit rule set E4,E7,E9,F,I,UP,B) |
| `docker compose run --rm --no-deps backend pytest` (final, after lint fixes and rebuild) | **37 passed** (26.3 s); demo DB counts unchanged afterwards |
| `docker compose config --quiet` (runtime env and `.env.example`) | exit 0 for both |

### Phase 1 regression check (after final rebuild)
Five services healthy; `GET /api/v1/health` returned 200 `{"status":"ok","db":"ok","redis":"ok","storage":"ok"}`; frontend HTTP 200; CORS preflight 200; stopping Redis gave HTTP 503 with `redis: down` and recovered to 200 after restart; backend runs as uid 10001; only 5173 and 8000 published.

### Tests (37, all executed and passing)
| File | Tests | Covers |
|---|---|---|
| `test_migration.py` | 5 | migration on an empty DB creates all 12 tables + 5 enums; models match migration (autogenerate diff empty); all FKs are RESTRICT; expected indexes exist; downgrade removes tables/enums and re-upgrade works |
| `test_constraints.py` | 15 | FK rejection and RESTRICT delete block; unique login_id, subject code, section (semester,name)/label, teaching slot, submission per assignment/student, version number, storage_key, one late request per student/assignment; invalid enum values; CHECK constraints (semester, max_file_mb, reason length, version context/late_request pairing, decision/window fields) |
| `test_seed.py` | 11 | exactly 50 FACULTY + 200 STUDENT with expected IDs; 8 sections / 24 subjects / 48 slots / 200 profiles; 25 students per section; all mappings valid; FAC001 teaches CS503 in CSE-5A; FAC049/FAC050 unassigned; Argon2 hashes unique, plaintext absent, verify works; deterministic names; second seed run creates no duplicates and does not re-hash; empty password rejected; seed config consistency |
| `test_init.py` | 6 | bucket created when absent / untouched when present; bucket private (no policy, no public ACL, anonymous GET 401/403); put/head/get/delete round trip; full `run_init` twice from an empty DB (counts and hashes identical; bucket absent, created, then exists); fails clearly without SEED_DEMO_PASSWORD; times out with a clear error when Redis is unreachable |

Isolation: databases `assignflow_test`, `assignflow_migtest`, `assignflow_inittest` (created and dropped by tests; an allow-list is checked before any destructive statement), Redis DB 1, bucket `assignflow-test`. Test passwords are random per run and never printed.

### Notes and decisions
- Phase 0 decisions (X1-X3, Q1-Q9) are still not recorded in the repo. None blocked Phase 2. The seed uses the blueprint's proposed dataset (Q6) as is.
- `FAC001` to `CS503 Database Systems` in `CSE-5A` is pinned in `seed_config.PINNED_SLOTS` (resolves traceability issue I5).
- Role/semester consistency of `student_profiles` and `teaching_assignments` is enforced by the seed and verified by tests, not by DB triggers (consistent with §14.2 "checked in seed and service").
- Insert-only tables are insert-only by application convention; no DB triggers (not in the blueprint).
- `users.role` uses the PostgreSQL enum instead of an additional `CHECK`.
- The test suite creates databases with the superuser from `POSTGRES_USER`; it requires `CREATEDB`.
- ruff `UP042` is ignored on purpose (`str, Enum` mixins kept).
- No `.env` was created in the project. Runtime verification used a temporary env file of random throwaway values kept outside the project and deleted afterwards.

### Volumes
Phase 1 volumes were initialised with throwaway credentials that were then deleted, so I removed those three specific volumes before Phase 2 (nothing of value in them). At the end of Phase 2 the stack was stopped and the volumes created during this verification were removed as well, because their database and MinIO credentials and the seeded demo password were throwaway values you do not know. Your first real `docker compose up --build -d` therefore starts from empty volumes with your own `.env`.

### Known issues / risks
- MinIO image is third-party (unchanged since Phase 1).
- Backend dependencies are version ranges, not a lock file.
- The 90 s backend `start_period` means a crash-looping backend takes up to 90 s to be marked unhealthy.
- AT23 (fresh clone, `.env`, up) has not been run by following the README; only the equivalent steps with a temporary env file.
- The frontend "Check backend health" button was still not clicked in a real browser (unchanged from Phase 1).

### Later-phase features
Confirmed not implemented: login/JWT/authorization, assignments, submissions/upload flow, late-request logic, reviews, timeline, notifications, overview, demo assignments (`seed_demo.py`), frontend pages.

---

## Phase 3 — Authentication and authorization

**Date:** 2026-10-10
**Scope:** login / logout / `GET /auth/me`, JWT access tokens, Redis `jti` revocation, per-IP and per-ID login throttling, fail-closed Redis behaviour, FastAPI auth dependencies and role guards, resource-scope helpers, error envelope, frontend login + route guards. No assignment, submission, review or notification features (Phase 4+). Git not initialised; nothing pushed.

### Files created
- Backend: `app/core/{clock,errors,deps}.py`, `app/schemas/{__init__,auth}.py`, `app/routers/{__init__,auth,health}.py`, `app/services/{tokens,ratelimit,profile,scope}.py`
- Backend tests: `tests/api/{__init__,conftest,test_auth,test_scope}.py`, `tests/unit/{__init__,test_security}.py`
- Frontend: `eslint.config.js`, `.prettierrc`, `.prettierignore`, `src/api/{client,types}.ts`, `src/auth/{AuthContext.tsx,useAuth.ts,tokenStorage.ts}`, `src/app/router.tsx`, `src/components/{HealthCheck,ProfilePage,RequireRole}.tsx`, `src/pages/public/{Landing,Login}.tsx`

### Files modified
`backend/app/main.py` (now an application factory `create_app(settings)`; health moved to `routers/health.py`, behaviour unchanged), `backend/app/core/security.py` (adds JWT + dummy hash; Argon2 functions unchanged), `backend/pyproject.toml` (+pyjwt, +slowapi; ruff bugbear config), `backend/tests/conftest.py` (forces Redis DB 1 for the test process), `frontend/package.json` + lockfile, `frontend/src/{App.tsx,index.css}`, `README.md`, `.env.example` (JWT_SECRET now required), `docs/REQUIREMENTS_TRACEABILITY.md`, this log. `architecture.md` untouched (SHA-256 prefix `464EB56A` unchanged). No database migration was added (schema unchanged).

### Behaviour implemented (architecture §8, §13, §19, §20)
- **Login** `POST /api/v1/auth/login {role, login_id, password}`: one generic 401 `INVALID_CREDENTIALS` ("Invalid ID or password.") for unknown ID, wrong password, inactive account and role mismatch; one Argon2 verification is always performed (dummy hash for unknown IDs). The login ID is trimmed and upper-cased; the password is capped at 128 characters.
- **Token**: HS256, claims `sub, role, jti (uuid4), iat, exp = iat + JWT_EXPIRE_MINUTES (120)`. Expiry is compared with the injectable clock (`core/clock.get_now`). `alg=none`/other algorithms rejected. `JWT_SECRET` must be at least 32 characters or the API refuses to start.
- **Authentication dependency** order: bearer present → signature/claims → expiry → Redis denylist → user loaded from PostgreSQL and active. The role always comes from the database row; the token's role claim is ignored.
- **Errors**: 401 `UNAUTHENTICATED / INVALID_TOKEN / TOKEN_EXPIRED / TOKEN_REVOKED`; 403 `FORBIDDEN` (wrong role); 404 for out-of-scope resources; 403 `NOT_YOUR_CLASS` when a faculty member targets a subject × section they do not teach (per §20.2 #5); 429 `RATE_LIMITED` with `Retry-After`; 503 `SERVICE_UNAVAILABLE` for Redis/database outages; 422 `VALIDATION_ERROR` (never echoes submitted values).
- **Logout** `POST /auth/logout` → 204; stores `deny:jti:{jti}` with TTL = remaining lifetime. If Redis fails the call returns 503 (it never claims an unrecorded logout).
- **Throttling**: SlowAPI 10 requests/minute per client IP on login (Redis storage); direct Redis counter `rl:loginfail:{role}:{login_id}` — 5 failures per 10 minutes, then 429 even with the correct password; success clears it. TTL starts at the first failure and is not extended.
- **Fail closed**: Redis unavailable → login 503, every authenticated request 503, logout 503.
- **`GET /auth/me`**: student → section + subjects with faculty names; faculty → teaching list (subject, section).
- **Scope helpers** (`services/scope.py`): student/faculty assignment rules, teaching-slot check (403 `NOT_YOUR_CLASS`), submission, version, late-request ownership (404 out of scope). They are used by tests only for now; no assignment/submission endpoints exist yet.
- **Logging**: request log has method, path, status, duration and user UUID only; login failures log only the role. Tests assert that passwords, tokens and hashes never appear in log records, and a log scan of the running backend found no password, token or JWT secret.
- **Frontend**: landing with Faculty Login / Student Login; login forms (React Hook Form + Zod); axios client with Bearer header and central 401 handling; `AuthContext` restores the session from `sessionStorage` via `/auth/me`; `RequireRole` guards `/student` and `/faculty`; profile page; logout. The Phase 1 health control is kept under "System status". React Router 7 is used (v6 had an advisory in `npm audit`; the SPA does not use the affected SSR code, but 7.x clears it).

### Commands executed and results
| Command | Result |
|---|---|
| `docker compose build backend` / `docker compose run --rm --no-deps -e JWT_SECRET=<random> backend pytest` (first run) | 4 test failures: three used the wrong path for test-only routes and one decoded a future-dated token with `iat` verification; test bugs, fixed |
| `docker compose build backend` + `docker compose run --rm --no-deps backend pytest` (final) | **78 passed** (31.6 s): 28 auth API, 7 scope, 6 JWT/password unit, plus the 37 Phase 2 DB/seed/init/MinIO tests (15+11+6+5) |
| `docker compose run --rm --no-deps backend ruff check .` | All checks passed (after `ruff --fix` for import order; `B008` handled via `extend-immutable-calls` for FastAPI `Depends`) |
| `npm install` (frontend) then `npm audit` | 0 vulnerabilities (after switching to React Router 7) |
| `npm run lint` | passed, no warnings |
| `npm run format:check` | passed |
| `npm run build` (`tsc -b && vite build`) | passed (`built in 1.4 s`) |
| `docker compose up --build -d` on the existing stack (your `.env`; `JWT_SECRET` overridden for this shell only) | five services healthy; initializer log `users created=0 already_present=250`, bucket already exists and private; existing data preserved |
| Live checks with `curl` against `localhost:8000` | wrong password and role mismatch → identical 401 JSON; `FAC001` login → token and user; `/auth/me` → teaching `CS503 / CSE-5A`; logout → 204; `/auth/me` afterwards → 401 `TOKEN_REVOKED`; `STU0101` → section `CSE-5A`, 6 subjects; CORS preflight for `POST /auth/login` with `Authorization` header allowed for `http://localhost:5173` only; actual cross-origin POST returned the correct `access-control-allow-origin` |
| `curl` on `/`, `/login/faculty`, `/student` (frontend) | HTTP 200 each (SPA fallback works) |
| psql counts afterwards | 50 faculty, 200 students, 48 teaching assignments, 8 sections — unchanged; only the `assignflow` database exists (test databases dropped) |

### Test coverage against the request
Successful and failed login for both roles; generic message for unknown/wrong/inactive/role-mismatch; expired token (frozen clock, boundary at exactly `exp`); revoked token and per-session revocation; tampered, foreign-signed, `alg=none` and HS512 tokens; token for unknown user; deactivated account loses access immediately; role taken from the DB not the token; role guards (401 vs 403); per-ID lockout, reset on success and TTL; per-IP limit; Redis outage for login, for the IP limiter, for authenticated requests and for logout; resource-scope rules across sections, subjects, ownership, other faculty and unassigned faculty (FAC049); no secrets in logs; validation errors do not echo passwords; Phase 1 health still reports real dependencies.

### Decisions and notes
- Per-IP limiting keys on the connection's remote address. Behind Docker Desktop all local clients may share one gateway IP, so the 10/min limit effectively applies to all browsers on that machine together. `X-Forwarded-For` is deliberately not trusted.
- The per-ID lockout follows §19 literally: an attacker can lock out a known ID for 10 minutes (per role). Accepted trade-off of the blueprint design.
- `GET /auth/me` carries the section/subject/teaching data, as in the blueprint's endpoint table; there is no separate `me` router.
- Test-only routes `/_test/faculty-only` and `/_test/student-only` are added inside the test fixture; they do not exist in the application.
- SlowAPI is used as specified; the "limiter storage down" test replaces SlowAPI's private `_limiter` attribute, so a SlowAPI upgrade could require adjusting that test.
- The test process is forced onto Redis DB 1 by `tests/conftest.py`, so tests cannot flush the application's Redis DB 0.
- Phase 0 decisions X1–X3 and Q1–Q9 are still not recorded in the repository.

### Known limitations / risks
- **Your `.env` still has the placeholder `JWT_SECRET`** (26 characters). I did not edit your file. The running backend was started with a random secret provided through my shell, so a later `docker compose up` without that variable will fail fast with a clear "JWT_SECRET must be set…" message. Put a real value in `.env` and run `docker compose up -d`.
- Your `.env` also still holds the placeholder `SEED_DEMO_PASSWORD`, so all 250 demo accounts currently use that placeholder password. Changing it later does not re-hash existing accounts (by design); reset with `docker compose down -v` before first real use if you want a new demo password.
- The login UI, route guards and logout button were built and compile/lint cleanly, and the pages are served (HTTP 200), but I did **not** click through them in a real browser; the API behaviour they rely on was exercised with curl and automated tests.
- No automated frontend tests exist (lint, format and build only).
- Tokens live in `sessionStorage` (architecture decision); an XSS bug would expose them. No refresh tokens: users log in again after 2 hours.
- `slowapi` and `pyjwt` are version ranges, not locked. PyJWT emits a key-length warning in one test that deliberately signs with HS512.

### Later-phase features
Confirmed not implemented: assignment CRUD and publishing, submissions/uploads and downloads, late requests, reviews, timeline, notifications, overview/analytics, `seed_demo.py`.

---

## Phase 4 — Assignment management

**Date:** 2026-10-10
**Scope:** faculty create / list / view / publish / edit-draft / change-deadline, student list and detail, deadline history, frontend pages. No uploads or submission versions, late requests, reviews, notifications or later dashboards. No schema change and no migration. Git not initialised; nothing pushed. `architecture.md` untouched (SHA-256 prefix `464EB56A`).

### Endpoints (all under `/api/v1`)
| Endpoint | Blueprint ref | Notes |
|---|---|---|
| `GET /faculty/assignments` | #4 | own assignments (created by me AND I teach the class), newest first; `expected_students` is a real count of the section's students; the other counts of #13 are not included (they need submissions, Phase 7) |
| `POST /faculty/assignments` | #5 | 201; `publish` true → PUBLISHED with `published_at` from the server clock, else DRAFT; 403 `NOT_YOUR_CLASS` for a subject × section the caller does not teach (also for unknown IDs); 422 for invalid input |
| `GET /faculty/assignments/{id}` | #7 | detail + `deadline_history`; 404 when not mine |
| `POST /faculty/assignments/{id}/publish` | #6 | 409 `ALREADY_PUBLISHED`; 422 `DEADLINE_IN_PAST` if the deadline is less than 1 minute away |
| `PATCH /faculty/assignments/{id}/deadline` | #8 | PUBLISHED only (409 `NOT_PUBLISHED`); new deadline must be after now (422 `DEADLINE_IN_PAST`); writes the `deadline_changes` row and updates the deadline in one transaction under a row lock; `original_deadline` never changes; `changed_at` is the server clock |
| `PATCH /faculty/assignments/{id}` | **not in the blueprint** | edit a DRAFT: title, instructions, deadline, allowed types, max size; 409 `NOT_DRAFT` once published; subject, section, status and timestamps are not editable (unknown fields → 422) |
| `GET /student/assignments` | #15 (subset) | published assignments of the student's own section, soonest deadline first, with `timing` PENDING / MISSING |
| `GET /student/assignments/{id}` | #16 (subset) | detail without versions/timeline; 404 for other sections and drafts |

`GET /auth/me` now also returns `id` for subjects and sections (additive; the create form needs them).

### Decisions that need your confirmation
1. **Draft editing endpoint (new).** You asked for faculty to edit assignments. The blueprint (§14.2) says the deadline is the only mutable business field, changed only through the deadline endpoint, and lists no edit endpoint. I added `PATCH /faculty/assignments/{id}` limited to **drafts**. Published assignments stay immutable except for the deadline, as the blueprint requires. If you want it removed, or want published titles/instructions editable, say so; the second option would need a policy decision (students may already have read the old text).
2. **Draft deadline edits** change `original_deadline` together with `deadline` (nothing is published yet, so there is no history to preserve; "original" is the deadline the assignment was published with).
3. **Required fields.** Title 1–150 characters, instructions 1–5000 characters (required, not optional), at least one allowed type from {pdf, docx, pptx, zip, png, jpg}, maximum size 1–10 MB (default 10). Surrounding whitespace is trimmed; duplicate types are collapsed. These are my reading of FR-06 / §14.2.
4. **Deadline policy applied exactly as §15.3/§15.4:** at create/publish ≥ now + 1 minute (a draft's deadline is also checked when it is created or edited); on change, > now; extensions after the old deadline has passed are allowed; no extra rules (an unchanged value is accepted and recorded).
5. **Timezones:** the API only accepts timestamps with a UTC offset (naive values → 422), stores UTC, returns ISO-8601 UTC. The UI shows and enters IST (UTC+05:30) using `Intl`, no extra library (Q4 recommendation).
6. **UI stack deviation.** Your brief says the UI uses TanStack Query, Tailwind CSS and shadcn/ui as "the existing stack". Only the first was missing but approved in the blueprint, so I added **TanStack Query**. **Tailwind and shadcn/ui were never installed** (Phase 1 deferred them; Phase 3 used plain CSS), and adding them now would restyle the whole app, so I kept the existing CSS design. Say if you want a Tailwind/shadcn migration as a separate step.
7. `timing` on the student list is computed server-side only for the "no submission" case (`now <= deadline` → PENDING, otherwise MISSING). When a submission exists it is `null` until Phase 5 provides the full status engine.

### Files created
- Backend: `app/schemas/assignments.py`, `app/services/{assignments,deadlines,status}.py`, `app/routers/{faculty,student}.py`; tests `tests/api/test_assignments.py`, `tests/unit/test_status.py`
- Frontend: `src/api/{queries,queryClient}.ts`, `src/lib/time.ts`, `src/layouts/AppLayout.tsx`, `src/components/{ui,AssignmentForm,AcademicSummary}.tsx`, `src/pages/faculty/{AssignmentList,AssignmentNew,AssignmentDetail}.tsx`, `src/pages/student/{AssignmentList,AssignmentDetail}.tsx`
### Files modified
`backend/app/main.py` (routers, version 0.4.0), `backend/app/schemas/auth.py` and `services/profile.py` (IDs in `/auth/me`), `backend/tests/api/{conftest,test_auth}.py` (cleanup fixture; assertions for the new IDs), `backend/pyproject.toml` (Ruff only, no new dependency), `frontend/package.json` + lockfile (`@tanstack/react-query`), `frontend/src/{App.tsx,index.css,api/types.ts,app/router.tsx,auth/AuthContext.tsx}`, `README.md`, the two docs. Removed: `frontend/src/components/ProfilePage.tsx` (replaced by the layout + pages).

### Frontend
Faculty: assignment list (subject, section, status, deadline with countdown, student count), create form (class picker built from `/auth/me`, RHF + Zod, "Create and publish" / "Save as draft"), detail page (facts, plain-text instructions, publish / edit draft, change-deadline form, deadline history). Student: assignment list (title, subject, faculty, deadline, countdown, Pending/Missing badge), detail page. Shared layout with navigation, logout. Loading, empty, error (with retry) and success states everywhere. Instructions are rendered as plain text. On logout the query cache is cleared and the user lands on the role's login page. Query data refetches on focus, and the student list polls every 60 s.

### Commands executed and results
| Command | Result |
|---|---|
| `docker compose build backend` + `docker compose run --rm --no-deps backend pytest` | **120 passed** (44 s): 41 new assignment tests + 1 status unit test + the 78 earlier tests (Phases 1–3 behaviour intact, including health, login, logout, throttling and Redis outages) |
| `docker compose run --rm --no-deps backend ruff check .` | All checks passed |
| `npm run lint`, `npm run format:check`, `npm run build`, `npm audit` (frontend) | passed; production build OK; 0 vulnerabilities |
| `docker compose up --build -d` (your `.env`) | five services healthy; seed counts unchanged (250 users, 48 teaching slots) |
| Real-browser run (Edge headless driven by `puppeteer-core` from a temp folder outside the project) against `http://localhost:5173` | **22/22 checks passed**: faculty login, session surviving a reload, class picker showing only `CS503 · CSE-5A`, client-side validation, create + publish, plain-text rendering of `<b>` in instructions, deadline change with reason appearing in the history and "Original deadline" appearing, draft create → edit → publish, list with subject/section/25 students, anonymous `/faculty` → faculty login, student `STU0101` sees the assignments with Pending badge and the detail page, student visiting `/faculty` redirected to `/student`, student `STU0126` (CSE-5B) sees the empty state and a not-found error for the other section's assignment URL |
| Cleanup of E2E data | the browser runs created 10 assignments and 5 deadline changes in your demo database, all titled `[E2E-PHASE4] …`; I deleted exactly those rows (verified beforehand that no other assignments existed). Afterwards: 0 assignments, 0 deadline changes, 250 users, 48 teaching slots |

### What the 41 + 1 new tests cover
Create in own class (published and draft); drafts hidden from students until published; UTC storage of any offset; unauthorized subject/section/unknown IDs → 403; students and anonymous → 403 / 401 on faculty endpoints; 16 invalid-input cases (empty/whitespace/oversized title, missing/oversized instructions, bad or empty or too many types, size 0/11, naive or garbled deadline, bad UUID, client-supplied `status`/`created_by`/`published_at`) and missing-field cases; trimming and de-duplication; deadline boundary (now+59 s rejected, now+60 s accepted, drafts too); draft edits (fields, deadline, immutability of subject/section/status, `NOT_DRAFT` after publishing); another faculty member and FAC049 cannot view/edit/publish/change-deadline (404); publish rules (`DEADLINE_IN_PAST`, `ALREADY_PUBLISHED`); faculty list scoped to own assignments with real counts, newest first; student list scoped to own section, ordered by deadline, PENDING / MISSING following the (frozen) server clock including exactly-at-deadline; student of another section gets 404; deadline change history (server-side timestamp, original preserved, several changes in order, old = previous new, students see current and original), extension after expiry allowed, past or equal deadline rejected without leaving history rows, draft → `NOT_PUBLISHED`, student 403, other faculty 404, unknown/timestamp fields rejected, blank reason stored as null.

### Known limitations
- Faculty list counts are only `expected_students`; on-time / late / missing / resubmitted counts need submissions (Phases 5–7). No assignment deletion or un-publishing exists (not in the blueprint).
- The "File submission is not available yet" note on the student detail page is a placeholder for Phase 5.
- No automated frontend tests (the browser run is a manual-style script kept outside the repository). Notification of students on deadline change (`DL_CHANGED`) belongs to Phase 7.
- A published assignment's title/instructions cannot be corrected (see decision 1).
- datetime-local inputs rely on the browser's date picker; their `min` hint uses the browser clock, the server remains the authority.
- Phase 0 decisions (X1–X3, Q1–Q9) are still not recorded in the repository.

### Later-phase features
Confirmed not implemented: uploads and versions, status engine beyond "no submission", late requests, reviews, timeline, notifications, overview counts, `seed_demo.py`.

---

## Phase 5 — Submission engine

**Date:** 2026-10-10
**Scope:** upload pipeline, immutable versions, status engine, upload eligibility, authenticated downloads, faculty roster and per-student versions, student/faculty UI. No late requests, review decisions, notifications or timeline events (later phases). No schema change and no migration (the Phase 2 tables already contain everything). Git not initialised; nothing pushed. `architecture.md` untouched (SHA-256 prefix `464EB56A`).

### Endpoints
| Endpoint | Blueprint | Behaviour |
|---|---|---|
| `POST /student/assignments/{id}/submissions` | #17 | multipart field `file` → 201 `{submission_id, version_id, version_no, uploaded_at, deadline_at_upload, upload_context, version_timing, submission_timing, is_resubmitted}`; 404 not visible / draft / other section; 409 `DEADLINE_PASSED`, `SUBMISSION_ACCEPTED`, `DUPLICATE_UPLOAD`; 413 `FILE_TOO_LARGE`; 415 `UNSUPPORTED_TYPE`; 422 empty / missing file; 411 without Content-Length; 503 `STORAGE_UNAVAILABLE` |
| `GET /student/assignments/{id}` | #16 (subset) | adds own `versions` (id, number, filename, MIME, size, SHA-256, `uploaded_at`, `deadline_at_upload`, context, `timing_at_upload`, `timing_now`), `timing`, `is_resubmitted`, `can_upload`, `upload_blocked_reason`. Reviews, request and timeline fields arrive in later phases |
| `GET /student/assignments` | #15 (subset) | `timing` is now the full submission-level status; adds `is_resubmitted` |
| `GET /faculty/assignments/{id}/roster?status=` | #9 (subset) | one row per student of the section: student, `timing`, `is_resubmitted`, `version_count`, `latest_uploaded_at`; filter by timing; 409 for drafts. `review_status` / `request_status` columns arrive with Phases 6–7 |
| `GET /faculty/assignments/{id}/students/{student_id}/timeline` | #10 (subset) | the student's versions and timing. The merged event timeline and "why this status" come in Phase 7. Student not in the assignment's section → 404 |
| `GET /files/versions/{version_id}` | #19 | streams through the backend after scope checks (own versions for a student, students of own assignments for faculty; otherwise 404); `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, `application/octet-stream`, `Cache-Control: private, no-store`; 503 if storage is down; 404 if the object is missing |

### Rules implemented (architecture §15.2, §16, §18)
- **Pipeline order:** scope (404) → validate size / extension / content / archive → capture `received_at` from the server clock once → eligibility → duplicate pre-check → store object → DB transaction → commit. Any failure after the object is stored deletes it again (best effort); if storage fails nothing is written.
- **Validation:** extension must be allowed by the assignment (`.jpeg` is treated as `.jpg`); content is detected with `filetype` (the client's Content-Type is ignored): PDF/PNG/JPEG/ZIP by signature; DOCX/PPTX must also contain `word/document.xml` / `ppt/presentation.xml`; size ≤ min(assignment limit, `MAX_UPLOAD_MB`), exactly the limit is accepted; empty files → 422. Filenames are sanitised (basename, control characters removed, ≤ 200 characters with the extension preserved) and used for display only. Storage keys are `submissions/{assignment_id}/{student_id}/{uuid4}.{ext}`.
- **Oversized bodies** are refused by an ASGI middleware from `Content-Length` before the multipart body is parsed (Starlette would otherwise spool the whole body to disk); bodies without `Content-Length` get 411.
- **Versions:** `version_no = latest + 1` under `SELECT … FOR UPDATE` on the submission row (created race-safely with `ON CONFLICT DO NOTHING`); versions are never updated or deleted; an upload identical (SHA-256) to the **latest** version is 409 (checked before storing and again under the lock, so double clicks and parallel tabs create one version); an upload identical to an older version is allowed.
- **Deadline snapshot:** every version stores `deadline_at_upload`. Timing is derived: `timing_at_upload` (against the snapshot) and `timing_now` (against the current deadline).
- **Status engine** (`services/status.py`, pure): no submission → PENDING while `now <= D` (exactly at D is PENDING) else MISSING; a version is ON_TIME if `uploaded_at <= D` (exactly at D is ON_TIME) else LATE; submission-level status = the **first** version's timing against the **current** deadline (Q1 recommendation); RESUBMITTED = more than one version. Timing is independent of review status.
- **Eligibility** (`services/eligibility.py`, §16.3): latest review ACCEPTED → 409; `received_at <= deadline` → REGULAR; after the deadline with latest review REVISION_REQUESTED → REVISION; otherwise 409 `DEADLINE_PASSED`. Rule 5 (late request → LATE_APPROVED) is not implemented (Phase 6). Reviews are only *read*; nothing in this phase creates them.
- **Orphans:** `app/services/orphans.py` + `scripts/find_orphans.py` (dry run; `--delete` removes) list objects no version references and references with no object.

### Files created
- Backend: `app/core/upload_limit.py`, `app/routers/files.py`, `app/schemas/submissions.py`, `app/services/{submissions,eligibility,file_validation,orphans}.py`, `scripts/find_orphans.py`; tests `tests/api/test_submissions.py`, `tests/unit/{test_eligibility,test_file_validation}.py`
- Frontend: `src/components/{VersionList,SubmissionPanel,Roster}.tsx`, `src/pages/faculty/StudentSubmission.tsx`
### Files modified
`backend/pyproject.toml` (+`python-multipart`, +`filetype`; Ruff `fastapi.File`), `backend/app/main.py` (middleware, S3 client, files router), `core/{clock,deps,errors}.py` (`get_clock`, `get_s3`, storage-error handler), `services/{status,storage,assignments}.py`, `schemas/assignments.py`, `routers/{student,faculty}.py`, `tests/conftest.py` (test process uses bucket `assignflow-test`), `tests/api/conftest.py` (bucket + table cleanup, clock override), `tests/unit/test_status.py`; frontend `api/{client,types,queries}.ts`, `app/router.tsx`, `pages/student/{AssignmentDetail,AssignmentList}.tsx`, `pages/faculty/AssignmentDetail.tsx`, `index.css`; `README.md`, both docs.

### Commands executed and results
| Command | Result |
|---|---|
| `docker compose build backend` + `docker compose run --rm --no-deps backend pytest` (final) | **203 passed** (64 s): 38 submissions API + 18 other new unit tests + 83 new in total, and the 120 earlier tests (Phases 1–4: health, login/logout/throttling/Redis outages, assignments, deadline history, DB constraints, seed counts, init and bucket tests) |
| first run of the new submission tests | 1 failure that was a **real bug**: truncating a very long filename to 200 characters dropped its extension, so valid files with long names were rejected 415. Fixed (shorten the stem, keep the extension) and covered by unit and API tests |
| `docker compose run --rm --no-deps backend ruff check .` | All checks passed |
| `npm run lint`, `npm run format:check`, `npm run build`, `npm audit` (frontend) | passed; 0 vulnerabilities |
| `docker compose up --build -d` against your running stack | healthy; no data lost (volumes were intact; the containers had been removed by a `docker compose down` on your side mid-session, so I started the stack again with `docker compose up -d`; the initializer re-ran idempotently) |
| Real-browser run (Edge headless driven by `puppeteer-core`, kept outside the repo) | **27/27**, after fixing a race the first run exposed (the "Version 2 received" banner appeared before the version list refreshed; the upload mutation now waits for the refetch). Covers: wrong extension / oversize / empty file caught in the browser; a PNG renamed `.pdf` rejected by the server with a clear message; first upload On time; resubmission → version 2 with version 1 kept and the Resubmitted flag; identical re-upload rejected; **downloads byte-identical to the originals** (student and faculty); faculty roster (25 students, real counts, status filter, per-student versions page); other-section student and classmate get 404 for files and assignments; **a real 2-minute deadline passing**: the student without a file sees Missing and no upload form, a direct API upload returns 409 `DEADLINE_PASSED`, the student who uploaded in time stays On time and cannot replace the file, and the faculty roster shows 1 on time and 24 missing |
| `scripts/find_orphans.py` on the live stack after the browser runs | 0 orphaned objects, 0 dangling references; 6 versions ↔ 6 distinct objects; anonymous GET of a stored object from inside the network → **403**; stored keys match the server-generated pattern |
| Cleanup | the browser runs created 4 assignments, 4 submissions, 6 versions and 6 objects, all titled `[E2E-PHASE5] …`. I deleted exactly those rows (verified that no other assignments existed) and then ran `find_orphans.py --delete`, which removed the 6 now-unreferenced objects (this also exercised `--delete`). Afterwards: 0 assignments, 0 submissions, 0 versions, bucket empty, 250 users, 48 teaching slots |

### Test coverage against the request
Valid and invalid uploads (every approved type, 9 wrong type/content cases, client Content-Type ignored, empty/missing file, assignment-level type limit); size (exact limit accepted, +1 byte rejected with nothing stored, global 10 MB cap before parsing, missing Content-Length); filename sanitising and key safety; server-controlled timestamps (client-supplied `uploaded_at`, `deadline_at_upload`, `upload_context`, `version_no`, `status` ignored); cross-student, cross-section, draft, faculty and anonymous access; resubmission preserving rows and objects, duplicate rules, concurrency (parallel different uploads get distinct numbers; parallel identical uploads create one version); status boundaries (deadline − 1 s, exactly the deadline, + 1 s, PENDING/MISSING, first-version rule, LATE read from data, extension recomputing against the current deadline); per-version deadline snapshots across a deadline change; extension reopening uploads; review-based eligibility (ACCEPTED blocks, REVISION_REQUESTED allows after the deadline without changing first-version timing); roster and per-student endpoints with authorization; download headers, scope matrix (owner, teacher, classmate, other section, other faculty, unassigned faculty, anonymous, revoked token); private bucket and no storage details in any JSON; storage down on upload (503, nothing written, recovers) and on download (503) and a missing object (404); database failure after storing removes the object; failed compensation leaves only an unreferenced orphan that the report finds; committed rows always reference stored objects.

### Decisions and notes
- **`.jpeg`** is accepted as JPG (same format; the blueprint lists only `jpg`). **Rule 5 / `LATE_APPROVED`** and everything involving late requests are untouched.
- **Q1 (first version drives submission-level timing)** is used as the blueprint recommends; it is still not recorded as approved in the repository. A revision uploaded after the deadline therefore shows `version_timing: LATE` for that version while the submission stays ON_TIME.
- **LATE is reachable only with data created by Phase 6** (a first version after the deadline needs a late request). It is tested through rows inserted directly in the database.
- Eligibility reads review rows although no review can be recorded yet; tests insert review rows directly. The blueprint's #10 path is used for the faculty per-student endpoint although it only returns versions for now.
- The roster counts in the UI are derived from the real roster rows (not hard-coded); the architecture's overview endpoint (#13, SQL aggregation) remains Phase 7.
- Race window: the assignment's deadline is read before the object is stored and not re-read under the submission lock, so a deadline change landing in those few milliseconds is not seen by that one upload (its `deadline_at_upload` snapshot is the one used for eligibility). Documented, accepted.
- The test process is forced onto the `assignflow-test` bucket (like Redis DB 1 and the test databases), so tests never write to the application bucket.

### Known limitations
- Uploads are read fully into memory (≤ 10 MB) for validation and hashing; no virus scanning and no zip-bomb inspection (files are never extracted).
- `docx`/`pptx` are validated by archive structure only, not by opening them.
- The frontend has no automated tests (lint, format, build, plus the manual-style browser script that is not part of the repository).
- Deleting or replacing a *file* in place does not exist by design; storage backup is out of scope.
- A browser download needs the Bearer token, so files are fetched through the API client as blobs (very large files are held in browser memory; the limit is 10 MB).
- Phase 0 decisions (X1–X3, Q1–Q9) are still not recorded in the repository.

### Later-phase features
Confirmed not implemented: late-submission requests, faculty review decisions, notifications, deadline-integrity event timeline, overview counts, `seed_demo.py`.

---

## Phase 6 — Late submission requests

**Date:** 2026-10-10
**Scope:** student late requests, faculty list / inspect / decide, the approved upload window (eligibility rule 5), derived EXPIRED / USED states, student and faculty UI. No timeline events, review workflow or notifications (Phase 7). **No schema change and no migration:** the Phase 2 `late_requests` table and its CHECK / UNIQUE constraints already hold everything. Git not initialised; nothing pushed. `architecture.md` untouched (SHA-256 prefix `464EB56A`).

### Endpoints
| Endpoint | Blueprint | Behaviour |
|---|---|---|
| `POST /student/assignments/{id}/late-request` | #18 | body `{reason}` only (20–1000 chars after trimming, plain text, control characters rejected, any other field → 422) → 201 request `{id, status, state, reason, requested_at, deadline_at_request, decided_*, decision_note, window_*}`; 404 not visible / draft / other section; 403 faculty; 409 `NOT_MISSING` (deadline not passed, exactly at the deadline, or the student already submitted); 409 `REQUEST_EXISTS` (one per student per assignment, also after a rejection or an expiry) |
| `GET /faculty/late-requests?status=&assignment_id=` | #12 | requests on assignments the faculty member created **and** teaches; `status` accepts PENDING / APPROVED / REJECTED plus the derived EXPIRED / USED; pending first (oldest first), then decided (newest first) |
| `GET /faculty/late-requests/{id}` | (inspect) | request + student + assignment + current deadline + the student's submission timing and versions; 404 outside the faculty member's scope |
| `POST /faculty/late-requests/{id}/decision` | #14 | `{decision: APPROVE or REJECT, note?≤500, window_hours?}`; `window_hours` must be a strict integer 1–72 (default 24) and is refused for REJECT; `decided_at`, `window_start` and `window_end` are the server clock (`[decided_at, decided_at + hours]`); 404 for other faculty, 403 for students, 409 `ALREADY_DECIDED`, 422 |
| `GET /student/assignments[/{id}]` | #15 / #16 | adds `late_approved`, `request_status`; detail adds `late_request` (own request incl. window) and `can_request_late`; `can_upload` / `upload_blocked_reason` now account for an approved window |
| roster / per-student endpoints | #9 / #10 | add `late_approved` and `request_status` |

### Rules implemented (architecture §16.3 rule 5, §17)
- **Who may request:** only a student whose timing is MISSING (no version and `now > deadline`; exactly at the deadline is still PENDING). One request per student per assignment (`UNIQUE`); `INSERT … ON CONFLICT DO NOTHING` makes double clicks and parallel tabs create one row (the rest get `REQUEST_EXISTS`). The assignment row is share-locked while the request is stored, so a deadline change in flight cannot be missed; `deadline_at_request` snapshots the deadline.
- **Who decides:** the faculty member who created the assignment and teaches that subject × section (same rule as everywhere else); anyone else gets 404 and the request is unchanged. A student gets 403.
- **Decision is written once:** `UPDATE … WHERE id = :id AND status = 'PENDING' RETURNING id`; the loser of a race matches no row and gets 409 `ALREADY_DECIDED`. The DB CHECK constraints (decision fields iff decided, window fields iff APPROVED, window order, reason length) back this up.
- **Eligibility rule 5** (`services/eligibility.py`, pure): after the deadline, no review block, own request APPROVED, `window_start ≤ received_at ≤ window_end` (both ends inclusive) **and** the student has no submission yet or their first version is itself LATE_APPROVED (rule 6: a late request never lets a student replace work already submitted regularly). Order of rules is 2 (ACCEPTED blocks) → 3 (on time: REGULAR) → 4 (revision requested: REVISION) → 5 (window: LATE_APPROVED) → `DEADLINE_PASSED`. Further uploads inside the window are further LATE_APPROVED versions.
- **Server enforcement, not UI:** the rule runs in the upload service twice, before the object is stored and again under the submission row lock. The request is re-read from the database each time (the decision fields are written once, so what is read is final). The client's form fields (`upload_context`, `late_request_id`, status) are ignored. A LATE_APPROVED version stores its **real** `uploaded_at`, the **deadline snapshot** and `late_request_id` (DB CHECK pairs context and link). Nothing is backdated, and timing is never ON_TIME just because of an approval.
- **Derived states** (`services/late_windows.py`, nothing stored, no job): PENDING / REJECTED as stored; APPROVED becomes **USED** when a linked LATE_APPROVED version exists and **EXPIRED** when `now > window_end` with no upload. EXPIRED leaves the student MISSING with no new request.
- **Display:** the API returns `late_approved` (first version came through a request and is still late); the UI shows "Late (approved)". If the deadline is later extended past that upload, timing is recomputed against the current deadline (§15.3) and the flag is false.
- **Deadline changes (§17.4):** the request row is never modified; if the new deadline is in the future the student can upload normally (REGULAR / ON_TIME, rule 3 before rule 5) and a pending request can still be decided.

### Files created
- Backend: `app/schemas/late_requests.py`, `app/services/{late_requests,late_windows}.py`; test `tests/api/test_late_requests.py`
- Frontend: `src/components/{LateRequestPanel,LateDecisionForm}.tsx`, `src/pages/faculty/{LateRequests,LateRequestDetail}.tsx`
### Files modified
Backend `services/{eligibility,submissions,assignments}.py` (rule 5; `require_upload_allowed` now returns the decision), `schemas/{assignments,submissions}.py`, `routers/{student,faculty}.py`, `main.py` (0.6.0), `tests/api/conftest.py` (cleans `late_requests`), `tests/unit/test_eligibility.py`; frontend `api/{types,queries}.ts`, `components/{ui,Roster,SubmissionPanel}.tsx`, `pages/student/{AssignmentDetail,AssignmentList}.tsx`, `pages/faculty/StudentSubmission.tsx`, `layouts/AppLayout.tsx` (Late requests link with a live pending count), `app/router.tsx`, `index.css`; `README.md`, both docs.

### Commands executed and results
| Command | Result |
|---|---|
| `docker compose build backend` + `docker compose run --rm backend pytest` (final) | **268 passed**: the 203 earlier tests unchanged and passing, plus 65 new (5 unit tests for rule 5, 60 API tests incl. parametrised) |
| first run of the new tests | 2 failures, both **test bugs** (a draft and a second assignment were created after the frozen clock had moved past the 1-minute-lead rule); fixed by creating them first. No application bug was found by the tests |
| `ruff check .` | one import-ordering finding in `routers/faculty.py`, fixed; then All checks passed |
| `npm run lint`, `prettier --check src`, `npm run build` | passed (build 267 modules) |
| `docker compose build backend frontend` + `up -d` on your stack | all five services healthy; no data lost |
| Real-browser run (Edge headless via `puppeteer-core`, outside the repo; reads the demo password from your `.env` without printing it) | **40/40**: assignment created in the UI with a real ~90 s deadline; before the deadline no late panel and the upload form present; after it the missing student sees the request form, a short reason keeps submit disabled and shows the counter, a valid reason is sent and shows **Request pending**, survives a reload, uploads stay closed, a second request → 409 `REQUEST_EXISTS`, a student cannot read the faculty list (403); two more students request (no one sees another's request); **another faculty member** sees an empty list and gets 404 on read and on decide; the owning faculty member sees 3 pending with the nav count, **approves one from the list (2 h + note)**, **rejects one**, and **opens the detail page and approves the third**; empty state; rejected filter; the approved student sees window, note and upload form and uploads → **"Late (approved)"** in the success message, badge, version history (deadline snapshot, "Late when received") and list; the rejected student sees the note and no upload form; the third student's window (shortened to 25 s by one SQL `UPDATE` for this run only, because the UI minimum is 1 h) shows **Window expired**, upload closed, API `can_upload=false`; roster shows Late (approved) / Request rejected / Window expired; "used" filter lists exactly one request; one LATE_APPROVED version linked to its request; 250 users unchanged; no unexpected console errors |
| `scripts/find_orphans.py` after the browser run | 1 orphan (the E2E upload, whose rows I had deleted), removed with `--delete`; then 0 orphaned, 0 dangling |
| Cleanup | the browser run created 1 assignment `[E2E-PHASE6] Late flow`, 3 requests, 1 submission, 1 version, 1 object. All deleted. Afterwards: 0 assignments, 0 submissions, 0 versions, 0 late requests, bucket empty, 250 users, 48 teaching slots |

### Test coverage against the request
Valid and invalid requests (reason boundaries 19/20/1000/1001, trimmed, whitespace-only, NUL, null, non-string, missing, extra/forged fields, malformed JSON); eligibility (before, exactly at, 1 s after the deadline; already submitted; per-assignment limit); duplicates (sequential, after rejection, 5 parallel requests → one row); wrong role / anonymous / other section / draft / unknown id; faculty list, filters (all states incl. derived), ordering, assignment filter, inspect; unauthorised faculty (two other faculty) and students deciding; approval (default 24 h, 1/2/24/72 h, server decision time and window, note), invalid decision bodies (hours 0, −1, 73, 1000, 1.5, 24.0, "24", true, window with reject, forged times, over-long / NUL note); rejection final; `ALREADY_DECIDED` (sequential and 2 / 4 parallel decisions, exactly one winner and the stored row matching it); uploads pending / rejected / no request (409, nothing stored), inside the window (LATE_APPROVED, real timestamp, deadline snapshot, `late_request_id`, never ON_TIME, shown in student list, roster and faculty view), exactly at `window_start` and at `window_end`, 1 s after (409), expiry (derived, stored status unchanged, no new request), several versions in the window, a window not usable to replace regular work, an extended deadline taking precedence (REGULAR, not linked), deadline change leaving the request untouched, forged form fields ignored, another student / another assignment unable to use an approval, ACCEPTED blocking inside the window, REVISION_REQUESTED after the window (REVISION, no link); a decision racing an upload and 3 parallel uploads inside the window (distinct LATE_APPROVED versions); DB CHECK constraints reject inconsistent rows; no orphans or dangling references; 250 seeded accounts, health and login unchanged.

### Decisions and notes
- **Confirmed by you for this phase:** submission-level timing = first version (Q1); per-version timestamp and deadline snapshot preserved; `.jpeg` accepted as JPG.
- **Not invented:** one request per assignment, MISSING-only, 20–1000 reason, 1–72 h window with default 24, inclusive window, derived EXPIRED / USED are all the blueprint's. Added beyond the blueprint's endpoint list: `GET /faculty/late-requests/{id}` (the "inspect" screen), the `assignment_id` filter, and `EXPIRED` / `USED` as list filters; `window_hours` is a strict integer.
- Approving does not check whether the student has meanwhile become eligible by a deadline extension; the blueprint says approval is then merely unnecessary, and the detail page shows that note.
- After a rejection or expiry the student has no further route except a faculty-requested revision (blueprint §17.3), which Phase 7 builds.
- A faculty member who is not the assignment's creator cannot decide, even if they teach the same class (blueprint §8.2 faculty rule).
- Race window carried over from Phase 5: a deadline change landing in the few milliseconds of an upload is not seen by that one upload.

### Known limitations
- Faculty and student alerts for requests and decisions (FR-17) and the event timeline entries (`LATE_REQUESTED`, `REQUEST_APPROVED`, …) are Phase 7.
- The window's UI minimum is 1 hour, so expiry can only be observed in a browser by shortening a window in the database (done once, for the E2E run, and documented above); expiry itself is covered by the API tests with a frozen clock.
- No automated frontend tests (lint, format, build and the external browser script).
- Phase 0 decisions X1–X3 and Q2–Q9 are still not recorded in the repository.

### Later-phase features
Confirmed not implemented: faculty review decisions, notifications / alerts, deadline-integrity event timeline, overview counts, `seed_demo.py`.

---

## Phase 7 — Reviews, Deadline Integrity Timeline, Health Board and notifications

**Date:** 2026-10-10
**Scope:** faculty reviews, the per-student timeline with "why this status", the Faculty Submission Health Board, stored notifications plus computed alerts, and their UI. **No schema change and no migration** (the Phase 2 `reviews` and `notifications` tables hold everything). No email, SMS, WhatsApp, push, new service or AI. Git not initialised; nothing pushed. `architecture.md` untouched (SHA-256 prefix `464EB56A`).

### Endpoints
| Endpoint | Blueprint | Behaviour |
|---|---|---|
| `POST /faculty/submissions/{submission_id}/reviews` | #11 | `{status: UNDER_REVIEW or ACCEPTED or REVISION_REQUESTED, feedback?≤2000, expected_version_no?}` → 201 review. Reviewer, version (always the latest) and `reviewed_at` are server-set; extra fields → 422; feedback required for REVISION_REQUESTED; 404 outside the faculty member's scope, 403 students, 409 `REVIEW_UNCHANGED` (same status and feedback already current), 409 `STALE_VERSION` (a newer upload arrived), 409 `NO_VERSION` |
| `GET /faculty/assignments/{id}/students/{student_id}/timeline` | #10 | now also returns `submission_id`, `latest_version_no`, `review_status`, `reviews`, `events` and `why_this_status` |
| `GET /student/assignments[/{id}]` | #15 / #16 | list adds `review_status`, `latest_feedback`; detail adds own `reviews`, `events` (the same timeline) and `why_this_status` |
| `GET /faculty/assignments/{id}/roster` | #9 | adds `review_status` |
| `GET /faculty/overview?assignment_id=&subject_id=&section_id=` | #13 | `{totals, assignments[]}`; SQL aggregation (see semantics) |
| `GET /faculty/overview/students?…&timing=&review_status=&limit=` | (list behind #13) | the students behind the counts, same query; `{total, items, truncated}`; `limit` 1–500 |
| `GET /notifications` | #20 | `{alerts, items (newest first, max 50), unread_count}` for the caller |
| `POST /notifications/{id}/read` | #21 | 204; 404 unless the notification is the caller's own; repeating it keeps the first `read_at` |

### Rules and semantics
- **Reviews are append-only.** A new decision is a new row; no endpoint edits or deletes (PATCH / PUT / DELETE → 405). `NOT_REVIEWED` is never stored. The submission row is locked, so a review cannot interleave with an upload; consecutive reviews in the same instant are given strictly increasing `reviewed_at`, so "latest" is never a tie.
- **Current review = latest review of the LATEST version** (architecture §16.3: a new version "starts as NOT_REVIEWED" and the earlier review stays in history). Phase 5 read "latest review of the submission"; I changed `latest_review_status` to this version-scoped rule and all 268 earlier tests still pass. Consequences: ACCEPTED blocks uploads (409 `SUBMISSION_ACCEPTED`) until a later review changes it; REVISION_REQUESTED after the deadline allows exactly one REVISION upload, after which a new revision request is needed.
- **Review and timing are independent**: "Late (approved)" + "Accepted" and "On time" + "Revision requested" are both shown and tested.
- **Timeline** (`services/timeline.py`): events come only from real records with their own timestamp and actor: assignment created / published, each deadline change (old → new, who, reason), late request, decision (window, note), each version (number, file, SHA-256, context, deadline snapshot, timing at upload and now) and each review (status, feedback, version). Two derived markers (`REQUEST_WINDOW_EXPIRED`, `DEADLINE_PASSED_NO_SUBMISSION`) are flagged `derived` and shown as such. Sorted by time, ties by event order then version number. Read-only (tested: reading writes nothing; events appear when a row is inserted directly in the database). `assignments.created_at` is now set from the server clock (it was the database transaction time) so the timeline and tests share one clock.
- **"Why this status"** is generated with the same status functions (first version vs current deadline; approver named; resubmission note; review stated as a separate dimension).
- **Health board counts** (`services/overview.py`): one SQL CTE `grid` with **one row per (assignment, student of the section)**; counts and the student list both come from it, so a student with several versions is counted once and `on_time + late + pending + missing = expected` holds by construction. Scope: published assignments the faculty member created and teaches. Definitions: `late_approved` ⊂ `late` (first version through an approved request and still late); `submitted` = on_time + late; `resubmitted` = students with more than one version; `under_review` / `accepted` / `revision_requested` = students whose current review has that status; `not_reviewed` = submitted students without a current review; `reviewed` = accepted + revision_requested; `requests_pending` = requests awaiting a decision. The timing filter applies to the student list (and clickable cards), the assignment / subject / section filters to both.
- **Stored notifications** (same transaction as the event, `dedup_key` UNIQUE, `ON CONFLICT DO NOTHING`): `LR_CREATED:{request}` → the assignment's faculty; `LR_DECIDED:{request}` → the student; `REVIEW:{review}` → the student (title and status only, feedback stays on the assignment page); `DL_CHANGED:{change}:{student}` → every student of the section (blueprint §22; not in your list but in the architecture, so implemented). Retries are no-ops: a repeated request → `REQUEST_EXISTS`, a repeated decision → `ALREADY_DECIDED`, a repeated review → `REVIEW_UNCHANGED`, none adds a notification.
- **Computed alerts** (students only, never stored): DUE_24H, DUE_3H (inclusive boundaries, exactly at the deadline is still due), MISSING (not while an approved window is open), WINDOW_CLOSING, WINDOW_EXPIRED; none after a submission or a used window.
- **Privacy:** a student's detail, list, timeline and notifications contain only their own data; another student's timeline → 403, another section → 404; faculty outside the class → 404; marking someone else's notification → 404.

### Files created
- Backend: `schemas/{reviews,timeline,overview,notifications}.py`, `services/{reviews,timeline,overview,notifications,alerts}.py`, `routers/notifications.py`; tests `tests/api/test_reviews_timeline.py`, `tests/api/test_overview_notifications.py`
- Frontend: `components/{Timeline,Reviews,NotificationBell}.tsx`, `pages/faculty/HealthBoard.tsx`
### Files modified
Backend `main.py` (0.7.0, notifications router), `routers/faculty.py`, `services/{submissions,assignments,late_requests,deadlines}.py`, `schemas/{submissions,assignments}.py`, `tests/api/conftest.py` (cleans `notifications`), `tests/api/test_assignments.py` (one test now advances the frozen clock between two creations: ordering by `created_at` is by the server clock); frontend `api/{types,queries}.ts`, `components/{ui,Roster}.tsx`, `pages/student/{AssignmentDetail,AssignmentList}.tsx`, `pages/faculty/StudentSubmission.tsx`, `layouts/AppLayout.tsx` (bell, Health board link), `app/router.tsx`, `index.css`; `README.md`, both docs.

### Commands executed and results
| Command | Result |
|---|---|
| `docker compose build backend` + `docker compose run --rm backend pytest` (final) | **335 passed**: the 268 earlier tests plus 67 new (reviews and timeline, health board, notifications and alerts) |
| intermediate runs | the new tests first failed for four reasons, all test-side: the login throttle (10/min) when a fixture logged in 11 users (fixture now flushes the test Redis DB), an assignment created after the frozen clock had passed its deadline, a hand-inserted review whose database-default time is real time, and a Phase 4 ordering test that relied on database time (now advances the frozen clock). No application defect was found by the tests |
| `ruff check .` | All checks passed |
| `npm run lint`, `prettier --check src`, `npm run build` | passed (one TypeScript narrowing error fixed during the build) |
| `docker compose build backend frontend` + `up -d` on your stack | all five services healthy |
| Real-browser run (Edge headless via `puppeteer-core`, outside the repo; reads the demo password from your `.env` without printing it) | **36/36** (a first attempt stopped at a script selector bug, the bell button text includes the unread count; its data was cleaned and the script fixed). Covers: faculty creates a real ~100 s assignment; two students submit; after the deadline a missing student sees the computed MISSING alert in the bell; a student requests late; the board shows 25 expected, 2 on time, 0 pending, 23 missing, 1 request awaiting, the Missing card filters the list to 23; the faculty bell shows the request as unread and opening it marks it read; approve; review form (revision request needs feedback), history, badge, timeline in order with "Why: On time" and no invented events; accept another student; the first student's bell shows 1 unread, sees the feedback, uploads a REVISION after the deadline (first-version timing stays On time, review resets to Not reviewed, version-1 review stays in history), marks the notification read; the accepted student sees no upload form; **another student's mark-as-read → 404 and another student's faculty timeline → 403 and an upload after acceptance refused**; the approved student is notified, uploads and sees Late (approved); final board: on time 2, late 1 (1 approved), missing 22, 1 accepted, 2 awaiting review, 0 requests; review filter lists only the accepted student; 250 users unchanged; reviews append-only; unique dedup keys; no unexpected console errors |
| `scripts/find_orphans.py` | the E2E uploads were removed with `--delete` (2 after the aborted attempt, 4 after the full run); then 0 orphaned, 0 dangling |
| Cleanup | all `[E2E-PHASE7]` assignments, requests, submissions, versions, reviews and their notifications deleted. Afterwards: 0 assignments, versions, late requests, reviews and notifications; bucket empty; 250 users; 48 teaching slots |

### Test coverage against the request
Reviews: valid recording with server-set fields on the latest version, 13 invalid bodies (derived NOT_REVIEWED, forged reviewer / time / version, over-long or control-character feedback, non-strict `expected_version_no`), feedback rules and boundaries, owner-only access (two other faculty, students, anonymous, unknown id), no rewriting through PATCH / PUT / DELETE, every status transition, strict ordering of same-instant reviews, Late + Accepted and On time + Revision requested together, ACCEPTED blocking before and after the deadline, re-opening by a later review, exactly one revision upload per revision request, reset of the current review on a new version, duplicate / parallel identical reviews (one row, one notification), stale-version guard, review racing an upload, feedback privacy between students and faculty. Timeline: complete ordered event set with actors, timestamps, windows, snapshots and reviews; student and faculty views identical and scoped; read-only; reflects database rows; ties; snapshot vs current deadline; rejection, expiry and no-submission markers flagged derived; "why" text for pending, exactly-at-deadline, resubmitted, approved-late, missing. Board: exact counts for a mixed scenario (multi-version students counted once, a review on a replaced version ignored, late vs late-approved, requests in each state), equality with independent SQL, bucket invariants, pending → missing at the deadline, student list = counts for every timing, review and combined filters, limit and truncation, assignment / subject / section filters, drafts excluded, other faculty see nothing and get 404 for foreign assignments, students 403. Notifications: creation for each event and recipient, no leakage to others, deduplication on every retry path and at service level, 50-item cap with full unread count, mark-as-read (own, idempotent, only `read_at` changes), ownership (404) for 5 other users, unknown, malformed and anonymous; alerts at exact 24 h / 3 h / deadline / +1 s boundaries, silenced by submission or used window, per-section and role scoping, window closing / expired.

### Decisions and notes
- **Interpretations to confirm:** (1) current review is scoped to the latest version (above); (2) feedback is mandatory for REVISION_REQUESTED only (the blueprint gives `{status, feedback}` without saying); (3) the optional `expected_version_no` guard and the `REVIEW_UNCHANGED` rule are additions for retry safety; (4) any status may follow any other (ACCEPTED is reversible by a new review, which keeps a mistaken accept fixable and the history intact).
- **Board design:** the blueprint's #13 returns counts for one assignment; I return totals plus one row per assignment and a separate student-list endpoint so every filter (assignment, subject, section, timing, review) is real. The board is a new page `/faculty/board`; `/faculty` still lists assignments (the blueprint puts the overview at `/faculty`).
- The `DL_CHANGED` notification and the computed alerts are from the architecture §22, not from your list.
- Phase 0 decisions X1–X3 and Q2–Q9 are still unrecorded.

### Known limitations
- The bell polls every 60 s (and refetches on focus); there is no push. Notification list shows the latest 50.
- Alerts exist for students only; faculty are informed by stored notifications (new requests).
- No automated frontend tests (lint, format, build and the external browser script).
- The review form always targets the latest version; reviewing an older version is not possible by design.
- Race window carried over from Phase 5: a deadline change within the milliseconds of an upload is not seen by that upload.

### Later-phase features
Confirmed not implemented: `seed_demo.py`, full end-to-end integration pass and demo readiness (Phases 8–9).

---

## Phase 8 — Final testing and quality assurance

**Date:** 2026-10-10
**Scope:** verification, defect fixing and release readiness. No new product feature, no change to `architecture.md` (SHA-256 prefix `464EB56A`), the database schema or any approved policy; no migration. Git not initialised; nothing pushed.

### Defects found and fixed (all verified before and after)
| # | Where | Type | Finding | Fix |
|---|---|---|---|---|
| D1 | frontend `auth/AuthContext.tsx`, `RequireRole.tsx` | **application defect** | Reloading a page while the API was unreachable (restart, network blip) treated *any* `/auth/me` failure as an invalid session: the token was deleted and the user was sent to the login page. Found by the browser run (stop the backend, reload) | Only a 401 ends the session. A network error or 5xx now keeps the token and shows "The server cannot be reached · You are still signed in" with **Try again**, which restores the session when the API is back. Re-verified in the browser |
| D2 | frontend `index.css` | **application defect** | At 375 px (and 768 px) the notification panel was anchored to the bell button and ran off the left edge of the screen (−175 px / −250 px), and the faculty top bar overflowed the page by 25 px | The panel is anchored to the top bar and sized to the viewport; the nav wraps (own row on narrow screens). Re-verified at 320 / 375 / 768 / 1280 px on 8 pages and with the panel open |
| T1 | `test_qa_regression.py` (new) | **test defect** | First version of the authorization matrix read FastAPI's route table; this FastAPI version nests routes, so the matrix was **empty and passing vacuously** | The matrix now reads the generated OpenAPI document and a floor test fails if fewer than 22 operations are found |
| T2 | same | test defect | The randomized walk never reached a late request for one seed, and tokens expired during 40 days of simulated time | Phase-based walk (three students never submit before the deadline), long-lived test tokens, and assertions that every event type occurred |
| T3 | `run8.mjs` (outside the repo) | script defects | deadline input has minute resolution (a 100 s deadline fell inside the 1-minute minimum); the bell button's text includes the unread count; a stale download directory; my clean-up one-liner removed the setup block once | corrected; the final run used a fresh download directory |

No other application defect was found. Findings are recorded as they happened; nothing was changed to hide a failure.

### Commands executed and results (final state)
| Command | Result |
|---|---|
| `docker compose build backend frontend`, `docker compose up -d` | all five services healthy; `GET /api/v1/health` → `{"status":"ok","db":"ok","redis":"ok","storage":"ok"}` |
| `docker compose run --rm backend pytest` | **349 passed**: 335 earlier tests unchanged plus 14 new in `tests/api/test_qa_regression.py` (see below) |
| `docker compose run --rm backend ruff check .` | All checks passed |
| `npm run lint`, `npx prettier --check src`, `npm run build` | passed |
| `npm audit` (all) and `npm audit --omit=dev` | **0 vulnerabilities** each |
| Python dependency audit (`pip-audit` run in a separate throw-away `python:3.12-slim` container against the backend image's 52 pinned packages) | 1 finding: **pytest 8.4.2, PYSEC-2026-1845 (fix 9.0.3)**: a test-time dependency that is only used to run the suite. No runtime dependency has a known vulnerability |
| Real-browser end-to-end (`run8.mjs`, Edge headless via `puppeteer-core`, outside the repo, against the running Compose stack) | **50/50 passed** on the final build (earlier same-day attempts: 44/46 with D1 found, then 49/50 with D2 found, after which each fix was verified and the whole scenario was rerun) |
| Responsive check (`resp.mjs`) | passed at 320, 375, 768 and 1280 px on 6 faculty and 2 student pages, bell panel open at every width |
| API-outage check (`down.mjs`) | after the fix: error state with Try again, token kept, data loads after the API returns |

### New automated tests (`tests/api/test_qa_regression.py`, 14 tests)
- **Authorization matrix generated from the OpenAPI document**: every operation rejects anonymous callers with 401; every `/student/*` operation refuses faculty and every `/faculty/*` operation refuses students with 403; unknown IDs on every scoped endpoint are 404, never 500 or 200; shared endpoints work for both roles.
- **Cross-section isolation**: a student of another section sees nothing of an assignment (list, detail, upload, request, file, notifications), two other faculty see nothing and cannot review, decide, change the deadline or download; classmates cannot read each other's files, reviews or requests.
- **Session lifecycle on the Phase 6–7 endpoints**: logout revokes access to notifications and the board (other sessions unaffected); expired tokens are refused (401); the new endpoints fail closed when Redis is down.
- **Error envelope**: an unexpected exception returns a generic 500 `INTERNAL_ERROR` without internals; validation errors never echo a submitted password.
- **Randomized workflow, two fixed seeds, 45 steps each**: random uploads, late requests, decisions, reviews and deadline extensions at advancing times, with invariants checked after every step: buckets sum to expected, `late_approved ⊆ late`, counts equal independent SQL and the student list totals, `LATE_APPROVED ⇔ late_request_id`, `latest_version_no` = number of versions, unique notification keys; at the end storage and database agree (0 orphaned, 0 dangling, versions = objects). Every action returned < 500.

Existing coverage that already satisfied the rest of the checklist (no new test needed): authentication, expiry, logout, throttling and Redis outages (28 + 6 tests), assignment creation / publishing / deadline changes (26), status boundaries and per-version snapshots, upload validation, private downloads and version preservation (38 + 8), late-request approval / rejection / expiry / concurrency (41), review transitions and privacy, timeline completeness / ordering / actors (29), board counts and filters, notification deduplication / unread / ownership (26), database initialization and repeat initialization (6 + 11 + 5 + 15).

### Browser scenarios (all executed in the final 50/50 run)
1–2 faculty login, create and publish for an authorised class (visible in the faculty list); 3 visible to a student of that section with a countdown, invisible to a student of another section (and a direct URL shows an error; request / upload → 404); 4 upload: server timestamp within a minute of the browser clock and shown in IST with the deadline snapshot, byte-identical download, resubmission creates version 2 with version 1 kept and Resubmitted shown, identical file refused; 5 real deadline miss: no upload form, late requests, approval from the queue, rejection, approved student uploads and is shown Late (approved), rejected student stays Missing; 6 revision request with feedback, uploads reopen after the deadline, revision is version 3 (Revision), first-version status stays On time, review resets, no second revision; 7 accepted student sees Accepted and no upload form, direct upload → 409 `SUBMISSION_ACCEPTED`; 8 timelines (order, actors, snapshots, request and window), board counts (25 = 2 + 1 + 0 + 22, 1 approved late, 1 resubmitted, 1 accepted, 2 awaiting review), filters, notifications; 9 classmate download → 404, other student's faculty view → 403, own notifications only, no foreign feedback in a student's view, a student cannot open the faculty area, another faculty member gets an error page and 404 on roster / files / timeline and sees nothing on the board; 10 refresh keeps the session, logout revokes the token, protected pages redirect, an invalid token returns to login, API-down error state and retry, responsive layout.

### Operational and integrity checks (executed)
- All five services healthy. Only 5173 (frontend) and 8000 (API) are published; Redis 6379, MinIO 9000/9001 are not reachable from the host. (Port 5432 answers on the host because **your own Windows PostgreSQL** listens there; the Compose database is not published.)
- Seed counts: 50 faculty, 200 students, 48 teaching slots; 0 assignments, versions, requests, reviews and notifications left after the tests.
- Storage: 0 orphaned objects and 0 dangling references after every run (the E2E uploads were removed with `find_orphans.py --delete`; only the objects created by the tests were listed).
- **Private storage**: from inside the Compose network an anonymous `GET` of the bucket, of an object key and of the MinIO root all return **403**.
- Anonymous API sweep: 7 representative endpoints → 401; CORS: a foreign origin gets no `Access-Control-Allow-Origin`, `http://localhost:5173` does.
- **Secrets**: the six secret-like values from your `.env` were searched for in the built frontend bundle (0 hits), in all repository files except `.env` and in the logs of all five containers (0 hits; no bearer-token-shaped strings in any log). `.env` is git-ignored and `.env.example` holds placeholders. The values found in other files are the public placeholders themselves (see risks).

### Remaining limitations and risks
1. **Your `.env` uses the public placeholder values** from `.env.example` for `POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` and `SEED_DEMO_PASSWORD` (only `JWT_SECRET` is a generated 64-character value). Harmless on a laptop where only ports 5173 and 8000 are published, but anyone who has read the repository knows them, and `SEED_DEMO_PASSWORD` is the password of all 250 accounts. Change them before any hosted deployment (changing the demo password later does not re-hash existing accounts). I did not edit your `.env`.
2. **API documentation is public**: `/docs`, `/redoc` and `/openapi.json` are served unauthenticated (FastAPI defaults; the architecture does not mention them). They expose the API shape, not data. Disable for a hosted deployment.
3. **Dev-only audit finding**: pytest 8.4.2 (PYSEC-2026-1845) lives in the backend image only because tests are baked into it; it is not reachable from the running API. Upgrade to 9.x with the next dependency refresh (not done here to avoid changing the test toolchain in a QA phase).
4. Tokens are kept in `sessionStorage` (an XSS would expose them; all user text is rendered as text and no `dangerouslySetInnerHTML` is used). No virus scanning or zip-bomb inspection of uploads; uploads are ≤ 10 MB and read into memory.
5. The login throttle keys on the client IP the API sees; behind a proxy it would need `X-Forwarded-For` handling. Per-ID lockout lets anyone lock a known ID for 10 minutes (the blueprint's design).
6. No automated frontend tests (D1 and D2 were found and verified by the browser scripts, which live outside the repository).
7. Carried over: a deadline change within the milliseconds of an upload is not seen by that one upload; the bell polls every 60 s; Phase 0 decisions X1–X3 and Q2–Q9 are still not recorded.

### Architecture or schema changes proposed
None. (Optional, not required: disable the interactive API docs and bump pytest for a hosted build.)

### Readiness for Phase 9
All approved features are implemented and every automated and browser check passes on the final build; the two defects found were fixed and re-verified. Phase 9 (demo readiness: `seed_demo.py`, demo script, final README) can start. Items to settle first: AT23 (a fresh-clone `docker compose up --build` run, not executed here because it needs the published ports and a clean volume set, which would mean stopping your live stack), the open Phase 0 decisions (name X1, hosting X2/Q5, submitted PPT X3), and replacing the placeholder credentials in `.env` if the demo will be exposed beyond your laptop.

---

## Frontend redesign: academic dashboards and Three.js campus (after Phase 8)

**Scope:** frontend only. No backend, schema, API or `architecture.md` change (SHA-256 prefix `464EB56A`); no Git; nothing pushed.

### What changed
- **Design system** (`index.css` tokens, new `dashboard.css`): light theme only (the earlier dark `prefers-color-scheme` block was removed), soft-blue page, white cards, pastel stat cards, pastel badges. Timing and review badges stay separate classes.
- **Shell** (`layouts/AppLayout.tsx`): logo, role-aware top navigation, bell with the real unread count (`NotificationBell`), avatar initials, real name and login ID, log out, mobile menu below 1024 px, skip link.
- **Student routes:** `/student` Dashboard (new), `/student/assignments` (the old list), `/student/submissions`, `/student/late-requests`, `/student/timeline`. The three list views are filters of `GET /student/assignments`; Timeline shows `GET /notifications`. Each assignment page keeps its full per-assignment timeline.
- **Faculty routes:** `/faculty` Dashboard (new), `/faculty/assignments` (the old list), the board, late requests and new-assignment routes are unchanged.
- **Dashboard pieces** (`components/dash/`): `StatCard`, `ActivityPanel`, `DeadlineCalendar`, `CampusPanel`, `CampusScene3D`, `campusData`.

### Metric sources (no invented numbers)
| Card | Source |
|---|---|
| Student: Active assignments | length of `GET /student/assignments` |
| Student: Submitted | items whose server `timing` is ON_TIME or LATE |
| Student: Due this week | items with server `timing = PENDING` and a deadline in the next 7 days (the 7-day window uses the browser clock for display only) |
| Student: Late requests | items with `request_status = PENDING` |
| Faculty: Active assignments | published items of `GET /faculty/assignments` |
| Faculty: Expected / Missing / Pending late requests | `GET /faculty/overview` totals (`expected`, `missing`, `requests_pending`), filtered by the subject and section selects (server-side) |
| Recent activity | `GET /notifications` |
| Calendar | assignment deadlines from the same lists (IST days) |
| My courses | `GET /auth/me` subjects; "n of m submitted" computed from the student's own list |

### Three.js
`three@0.169.0`, `@react-three/fiber@8.18.0` (React 18 line; fiber 9 needs React 19), `@react-three/drei@9.122.0`, `@types/three@0.169.0`, `lucide-react@0.469`. `CampusScene3D` is a stylised, explicitly non-geographic campus (5 buildings, courtyard, fountain, walkways, low-poly trees). It is a separate lazy chunk (about 845 kB, 228 kB gzipped) loaded only when the panel scrolls into view. Interactions: constrained OrbitControls (no pan, limited zoom and polar angle), hover highlight, click a building (or use the keyboard-accessible building list) to move the camera and open an info panel, Reset view, 3D on/off toggle (off by default below 640 px, remembered in `localStorage` when available). `frameloop="demand"` (renders only when something changes), DPR capped at 1.5, one basic-shadow light, no post-processing, `prefers-reduced-motion` makes camera moves instant. Fallbacks: no WebGL, scene error (error boundary), or switched off show a 2D illustration and the same building list.

### Verification actually executed
| Check | Result |
|---|---|
| `npm run lint`, `npx prettier --check src`, `npm run build` | passed |
| `npm audit` (all and `--omit=dev`) | 0 vulnerabilities |
| Real browser (Edge headless, outside the repo, `ui9.mjs`) against the rebuilt Compose stack, real seeded accounts, test data created through the API | **64/64** |
| What it covered | student card values equal the API figures; table, badges, courses, calendar (select a day, legend, keyboard focus), all five student nav routes and their filters; assignment detail and versions; bell; 3D canvas rendered (WebGL), building select, reset, toggle; blocked-API error state with Try again and recovery (cards show "–", not numbers); 1440/820/390 px no horizontal overflow, mobile menu, table-as-cards; student route guard and logout; other-section student empty states; faculty cards equal `/faculty/overview`, filters, table, late-request queue, nav, Manage and late-request detail; WebGL disabled fallback; no unexpected console errors, no 5xx |
| Cleanup | only `[E2E-UI9]` rows removed; seeded users untouched |
| Backend | no backend file changed, so the 349-test suite was not rerun for this change |

### Limitations and gaps
- The Phase 8 browser scripts (`run8.mjs`, `down.mjs`) target the old student home page and were **not** rerun against the new UI.
- The assignment table has no description column: the list endpoint does not return instructions, and fetching every detail would be N extra requests.
- The faculty "recent activity" shows the notifications the backend creates (late requests, reviews, deadline changes). Faculty are not notified of new submissions, so those are not shown.
- Faculty "Timeline" is per student (open from an assignment); there is no global faculty timeline endpoint. The faculty Submissions item opens the existing health board.
- The dashboard has no automated frontend tests, and the screenshots were not compared pixel-by-pixel with the reference.
- The 3D chunk is large; it is lazy, but not loaded-size-free.
- The 3D scene was exercised only with a software (SwiftShader) WebGL in headless Edge; real-GPU performance was not measured.

## Cleanup and dataset phase A (campus removal, 15 faculty / 100 students)

**Status:** code and tests done; the dataset transition has NOT been applied to the running database (awaiting approval). The quiz feature is NOT started (phase B). No Git, no push, `architecture.md` untouched.

- **Campus Explorer removed** from both dashboards: the card, Three.js scene, building list/info, Reset view / 3D toggle, styles. `three`, `@react-three/fiber`, `@react-three/drei` and `@types/three` were uninstalled (nothing else used them). The served bundle contains no campus or WebGL code; lint, Prettier and the build pass.
- **Fabricated data:** no application code path creates assignments, submissions, versions, requests, reviews, notifications or deadline changes; startup only seeds sections, subjects, users, profiles and teaching rows. The live database currently holds 0 rows in every operational table (the earlier `[E2E-...]` rows were test data I created and removed). A test (`test_seed_creates_no_operational_records`) now asserts this. Dashboards read only the API and show empty states or errors.
- **Dataset: exactly 15 faculty and 100 students.** `seed_config.py`: semesters 3 and 5, sections A and B (CSE-3A, 3B, 5A, 5B), 25 students each, 12 subjects, 24 teaching slots. Faculty `FAC001..FAC015` (FAC001 pinned to CS503/CSE-5A); the other 23 slots are dealt round-robin, so every faculty teaches 1-2 classes and each class has exactly one teacher. Students are `STU0051..STU0150` (the original numbering of semesters 3 and 5), so every surviving account keeps its login ID, name, section and password hash. Names come from the same deterministic pool as before. Passwords: Argon2 hash per account from `SEED_DEMO_PASSWORD`, never stored in files.
- **Seed is stricter:** `verify_seed` now requires the exact configured account sets and teaching map; a database holding another dataset is refused with a hint (nothing is deleted).
- **Controlled transition:** `python -m app.db.transition_dataset` (dry run) and `--apply`. It discovers every foreign key from the live schema and refuses (changing nothing) if any record references an account, section or subject it would remove, or if a class that stays would change teacher while it has assignments. Apply runs in one transaction, then the idempotent seed and verification. Dry run on the real database: 135 accounts to remove (35 faculty, 100 students of semesters 1 and 7), 4 sections, 12 subjects, 47 teaching rows to rewrite, **no dependent records found**.
- **Tests:** 352 backend tests pass (`docker compose run --rm backend pytest`), Ruff clean. Changes: counts 115 accounts / 24 slots, a new test-only faculty `QAFAC01` without classes in the isolated test database (replaces FAC049), a legacy-database refusal and transition test.
- **Not verified yet:** the transition against the real database (not applied), migrations on the existing database (no schema change in this phase).

## Enhancement round 2, Phase A: inspection and plan (no code or data changed)

Read-only findings: the database now holds real records created through the UI (2 published assignments "DBMS" and "os" by FAC001 for CS503 / CSE-5A; one submission, one APPROVED late request and 2 ACCEPTED reviews for STU0102; 4 notifications). FAC001 and STU0102 therefore must keep their accounts, class and section. Existing seeded names (for example "Jason Thakkar", "Qadim Shenoy", "Ethan Sur") are not plausible Indian names.

Important state: the 15 faculty / 100 student seed code from the previous round exists in the repository and in a rebuilt (but not yet running) backend image; it was never applied to the database. It is superseded by this round's 15 faculty / 50 student dataset (Phase B). Until Phase B ships, a backend container recreated from the new image would refuse to start (strict dataset check); the running container is unaffected.

Plan, migrations and open decisions are in the Phase A report given to the user.

## Enhancement round 2, Phase B: dataset code, reference materials, View/Download

**Status:** code and tests complete. **The real database is unchanged** (still migration `0001`, 250 users, the existing
2 assignments / 1 submission / 1 late request / 2 reviews / 4 notifications). The dataset transition and renames are in dry-run
mode and wait for approval. The running containers on ports 5173 / 8000 still run the previous images on purpose: the new
backend refuses to start on the old 50/200 database (strict dataset check), so it must not be restarted before the transition.
No Git, no push, no `down -v`, `architecture.md` untouched.

### Dataset (15 faculty, 150 students, semester 5, sections A/B/C)
- `seed_config.py`, new `seed_names.py` (curated fictional Indian names, 165 distinct), `seed_users.py` (no Faker),
  stricter `verify_seed` (exact account sets, teaching map and student sections; refuses another dataset with a hint).
- `transition_dataset.py` extended: renames, student section moves (blocked and reported if the student has ANY dependent
  record), removals, teaching rewrites, all in one transaction, dry run by default. `--verbose` lists every change.
- Dry run on the real database: 115 renames, 75 section moves (STU0126-0150 5B->5A, STU0151-0200 7A/7B->5B), 135 accounts
  to remove (35 faculty, 100 students), 6 sections and 18 subjects to remove, 47 teaching rows to rewrite, **no dependent
  records found, no blockers**. STU0101/STU0102 stay in CSE-5A and FAC001 keeps CS503 / CSE-5A; their names would change
  (FAC001 Jason Thakkar -> Aarav Sharma, STU0101 Aadi Doshi -> Lakshmi Naidu, STU0102 Rajata Jaggi -> Gayatri Singh).
- Pending approval: `docs/DATASET_TRANSITION_DRYRUN.md` and `docs/DEMO_DATASET_NAME_MAPPING.md`.

### Reference materials and previews (requirements 1 and 2)
- Migration `0002` + model `AssignmentAttachment` (see DATABASE_SCHEMA.md). `app/services/attachments.py`,
  `file_validation.validate_reference_file` (PDF / PPT / PPTX by extension AND detected content, size <= global limit,
  PPTX needs `ppt/presentation.xml`, at most 5 files per assignment, sanitised names, server-generated keys, object removed
  if the row cannot be written).
- Endpoints: `POST /faculty/assignments/{id}/attachments` and `DELETE .../attachments/{att}` (own DRAFT only, else 404 / 409),
  `GET /files/materials/{id}` (download) and `/preview`, `GET /files/versions/{id}/preview`. Student sees `attachments` in
  the assignment detail only for a published assignment of their own section; faculty need ownership and teaching scope.
- Preview rule: `inline` only for content-detected PDF, PNG and JPEG, with the detected type, `nosniff`, `Cache-Control:
  private, no-store` and `Content-Security-Policy: default-src 'none'; sandbox`. Everything else answers 415
  `PREVIEW_UNAVAILABLE`; the UI says so and offers Download. Downloads remain `attachment` + `application/octet-stream`.
- Frontend: `DocumentPreview` modal (focus handling, Escape, blob URL revoked on close), `FileActions` ([View][Download]),
  `ReferenceMaterials`, reference picker in the Create form (drafts first, upload, then publish), "Assignment Instructions &
  Reference Materials" on the student page, materials manager on the faculty page (editable while DRAFT), View + Download
  on every submission version (student and faculty).
- Defects found by the browser run and fixed: CORS did not allow DELETE (draft document removal failed in the browser; now
  allowed and covered by a preflight test); the new-assignment page navigated with a stale cached draft after the raw
  upload / publish calls (now invalidates the caches).

### Verification actually executed
| Check | Result |
|---|---|
| `docker compose run --rm backend pytest` | **393 passed** (349 earlier + dataset/transition tests + 33 attachment/preview/CORS tests, existing tests adapted to 50-student sections) |
| Ruff | All checks passed |
| `npx prettier --check src`, `npm run lint`, `npm run build`, `npm audit` | passed, 0 vulnerabilities |
| Migration | applies to an empty database to head, matches the models, downgrade/upgrade repeatable (existing migration tests) |
| Real browser (Edge) on a separate throw-away Compose stack (project `afstage`: own network, own empty volumes, ports 5273/8100, removed afterwards) | **49/49**: fresh init gave 15 faculty / 150 students / 50 per section / 18 teaching rows / 0 operational rows / unique Argon2 hashes / 165 distinct names; faculty creates a published assignment with PDF + PPTX + PPT through the form; View (PDF modal, blob URL, Escape, PPTX honest message) and Download byte-exact for faculty and student; validation messages; draft add / remove / publish lock; other-section student 404 and anonymous 401; student upload; faculty submission page View + Download side by side, PNG preview, byte-exact download; 820 / 390 px no overflow, modal fits; no console errors; storage 0 orphans |
| Real database after all of this | unchanged (see counts in the Phase B report) |

### Limitations
- The PDF viewer inside the modal depends on the browser's built-in PDF support (the test browser exposes the frame; pixel
  rendering of the PDF was not screenshot-verified).
- Legacy `.ppt` (OLE) files are accepted and downloadable but never rendered; OLE files can carry macros, which is why they
  are download-only.
- Reference documents can only be edited on drafts. There is no workflow to replace them after publication (by design).
- `faker` is still listed in `pyproject.toml` but is no longer imported.
- Phases C-G are not started.

## Phase B correction: target corrected to 15 faculty / 50 students; startup no longer crash-loops

- **Why the runtime expected 150 students:** the approved target is 50 students (17/17/16). My Phase B implementation followed a later
  instruction that said "150 students, 50 per section", which contradicted it, so `seed_config.py` was set to 3 x 50. That was a
  misreading on my side and is now fixed (`SECTION_SIZES = {A: 17, B: 17, C: 16}`, `STU0101`-`STU0150`).
- **Why the earlier report showed "50 faculty and 250 students":** that was not a target. The backend error counted the 200 existing
  students plus the 50 new accounts the seed had inserted inside its (rolled-back) transaction. The seed now refuses BEFORE inserting
  anything, so the counts it reports are the real database counts (50 and 200).
- **Crash loop:** a dataset mismatch is now a `DatasetMismatch`; initialisation logs `DATASET TRANSITION PENDING`, inserts and deletes
  nothing, and the API starts and serves the existing data. The safeguard is kept: the dataset changes only through
  `transition_dataset --apply`. Covered by `test_init_does_not_crash_loop_when_a_dataset_transition_is_pending`.
- **Corrected dry run (real database, nothing applied):** before 250 accounts (50 faculty / 200 students, 8 sections x 25); after 65
  (15 / 50: CSE-5A 17, 5B 17, 5C 16). 65 renames, 24 students move (STU0118-0125 5A->5B, STU0135-0150 5B->5C), 185 accounts removed
  (35 faculty, 150 students), 6 sections and 18 subjects removed, 47 teaching rows rewritten. Every dependent-record check
  (assignments, notifications, deadline changes, late requests, submissions, versions, reviews, attachments, for removed accounts, moving
  students, removed sections and subjects) found 0 rows; no blockers. See `docs/DATASET_TRANSITION_DRYRUN.md`.
- **Restored availability:** `docker compose up -d` with the new images; migration `0002` was already applied; all five services healthy;
  logins for a student and a faculty account work; real database unchanged (250 users, 2 assignments, 1 submission, 1 late request, 2 reviews,
  4 notifications, 0 attachments). 394 backend tests pass, Ruff clean.
- The Phase B browser verification ran on a 150-student dataset; its dataset checks (A1-A6) need a rerun for 15 / 50 after approval. The
  document features it checked are unaffected by the dataset size.

## Pre-apply verification (read-only) and rehearsal

Backup: `backups/assignflow_pre_transition_20261010-205223.dump` (pg_dump custom format, 72,545 bytes, 14 table-data entries), verified by restoring it into a scratch database: identical row counts to the real database. Independent read-only verification (own catalog-based FK discovery, read-only transaction): the 24 moving students have 0 history rows; FAC001, STU0101, STU0102 keep their IDs and all history (fingerprint dd2c0e5b99e1c520); 185 accounts to remove (FAC016-050, STU0001-0100, STU0151-0200), 65 renames, 24 moves (8 5A->5B, 16 5B->5C), 6 sections, 18 subjects, 47 teaching rows rewritten (1 kept). Rehearsal on scratch copies of the backup: forced failure after all changes rolled back everything; a real `--apply` produced exactly 15 faculty / 50 students (17/17/16), 18 teaching rows, history fingerprint unchanged. Scratch databases dropped; the real database was not modified.

## Section-level filtering and faculty "Delete assignment"

No schema change, no migration, no data change. `architecture.md` untouched; no Git; no `down -v`.

### Diagnosis (read-only)
- The overview SQL (one grid row per student per assignment, joined to the teacher's own teaching slots) was already correct and
  counts a student once however many versions exist. Problems found: (1) the board built its Section list from *published
  assignments*, so an authorised section without assignments could not be selected; (2) an unknown or foreign `section_id` /
  `subject_id` silently returned zeros instead of being denied; (3) the assignment list and the late-request queue had no server-side
  filters (the dashboard filtered a full list in the browser); (4) the Subject and Section dropdowns were independent, and filtered
  queries showed the cached numbers of a previous visit while refreshing.
- Real database (read-only): every section has 25 students (CSE-1A, 1B, 3A, 3B, 5A, 5B, 7A, 7B; 6 teaching rows each; 50 faculty,
  200 students). The intended 17 / 17 / 16 in CSE-5A / 5B / 5C does not exist yet: the approved dataset transition has **not been
  applied** and CSE-5C does not exist. Nothing was inserted, moved or deleted. FAC001 teaches only CS503 / CSE-5A, so the real
  dashboard offers one section for it. On a fresh database seeded with the target dataset the counts are exactly 17 / 17 / 16.

### Section filtering (server + UI)
- `scope.require_filter_scope`: a subject / section filter is honoured only if the faculty member teaches it (403 `NOT_YOUR_CLASS`;
  unknown and foreign IDs behave identically, so nothing can be probed). Applied to `GET /faculty/overview`, `/overview/students`,
  `/faculty/assignments` and `/faculty/late-requests`. The last two gained optional `subject_id` / `section_id` parameters.
  A permitted but unmatched combination (a subject and a section I teach, never together) returns empty data, not an error.
- UI: shared `ScopeFilters`: options come only from `/auth/me` teaching (authorised classes), depend on each other, show an active
  filter bar with Clear, and drive the dashboard cards, assignment table, late-request queue, the assignment list page and the
  health board. Filtered queries use `gcTime: 0`, so a switch shows skeletons, never another moment's numbers. The recent-activity feed
  is not tied to a section (notifications carry no section), so it says it always covers all classes.

### Delete assignment (policy)
- `DELETE /faculty/assignments/{id}` and read-only `GET /faculty/assignments/{id}/deletion-check`. Owner only (404 for another
  teacher or an unknown ID, 403 for students, 401 anonymous).
- Allowed only when no submission, version, review, late request, deadline change or notification refers to the assignment. A DRAFT
  may carry reference documents; they are removed with it (the teacher can already remove them one by one). For a PUBLISHED assignment
  reference documents block deletion. A published assignment with no history at all may be deleted (nothing is lost; the dialog warns
  that students see it). Otherwise 409 `ASSIGNMENT_HAS_HISTORY` with the counts, and every record is kept.
- No archive / cancelled state exists in the schema (enum DRAFT / PUBLISHED), so no Archive action is offered and the message does not
  suggest one. Adding it would need a migration and a visibility policy; not done.
- Safety: row lock (`SELECT ... FOR UPDATE`) then re-check inside the transaction, one commit, ON DELETE RESTRICT foreign keys as the last
  guard (an IntegrityError becomes 409), storage objects removed only after the commit and only if nothing references the key; a failed
  object removal leaves a harmless orphan reported by `find_orphans.py` (`files_left` in the response).
- UI: Delete assignment (destructive style) on every card of the list and on the detail page; the dialog asks the server first and shows
  title, subject, section, state, and either "cannot be undone" + a Delete button or the protected-history explanation with only Close;
  the button is disabled while running (a double click sent one request); caches refresh and a message is shown.

### Verification actually executed
| Check | Result |
|---|---|
| `pytest` (isolated test DB / Redis / bucket) | **415 passed** (incl. 21 new section-filter and deletion tests) |
| Ruff, `npx prettier --check src`, `npm run lint`, `npm run build`, `npm audit` | passed; 0 vulnerabilities |
| Real browser (Edge) on a throw-away Compose stack with the target dataset (removed afterwards) | **56/56**: DB sections 17/17/16; dropdown options; 5A, 5C and combined totals equal the API and independent SQL; subject + section together; clear; empty section; skeleton while loading; board filters; unauthorised 403s; delete dialogs (protected / eligible), double click = 1 request, storage 0 orphans, dashboard refresh, student visibility, 404/403/409 statuses; 390 px; no console errors |
| Real stack redeployed with the new build | healthy; read-only smoke: FAC001 dashboard offers CS503 and CSE-5A only; unknown section filter 403; both existing assignments protected (os: late request + notification; DBMS: submission, versions, reviews, notifications); real data unchanged (250 users, 2 assignments, 1 submission, 4 notifications) |

### Limitations
- The recent-activity feed cannot be filtered by section (no section on notifications).
- Real-database section counts will only show 17 / 17 / 16 after the approved transition is applied.

## Archive / restore for published assignments; deletion limited to drafts

`architecture.md` untouched; no Git; no `down -v`; one additive migration (`0003`) applied to the real database after a backup
(`backups/assignflow_pre_archive_20261010-234403.dump`). The real data was not modified by this work: no assignment on the running
system was archived or deleted.

### Why a state and not only a blocked dialog
Deletion of an assignment with student history is (correctly) refused, but the teacher then had no way to take an unwanted published
assignment out of use. The schema had only DRAFT / PUBLISHED, so a reversible **ARCHIVED** state was added (one state, called Archive
in the UI; a separate "Cancel" would be the same behaviour under another name).

### Policy
| Assignment | Action offered | Result |
|---|---|---|
| Draft (with no history) | **Delete assignment** (permanent; its own draft reference documents go with it) | row and objects removed |
| Published, no student history | **Archive assignment** (explicit confirmation) | state ARCHIVED, everything kept |
| Published, with submissions / reviews / other history | dialog "This assignment has student history" -> **Archive assignment** or Close; archiving needs a SEPARATE confirmation step with the effects listed | state ARCHIVED, everything kept |
| Archived | **Restore assignment** | PUBLISHED again, same deadline |

* Published and archived assignments can never be permanently deleted (`DELETE` answers 409 `NOT_A_DRAFT`, and a draft with
  dependent rows is still refused). This replaces the earlier rule that allowed deleting a published assignment without history.
* Archived means: students lose it from active work, alerts and upcoming deadlines; a student who has a submission or a late request
  on it can still open it read-only (feedback, own versions, download / preview, reference documents) and sees it under "Archived
  assignments"; students without history cannot see it (404). New uploads, late requests, reviews, late-request decisions and deadline
  changes answer 409 `ASSIGNMENT_ARCHIVED`. A pending late request on an archived assignment is not counted as awaiting a decision.
* Faculty: archived assignments leave the active list, the dashboard counts and the health board, and appear under the Archived tab
  (the dashboard says "n archived assignments"); the roster, submissions, reviews and timeline remain available.
* Deadlines and review statuses are never modified. Timeline events `ASSIGNMENT_ARCHIVED` / `ASSIGNMENT_RESTORED` (actor, time, reason)
  come from the new `assignment_state_changes` table; no notification is sent (not requested; it would be noise for students
  who never submitted).
* Concurrency: archive takes the assignment row `FOR UPDATE`; upload, late request, review and decision take it `FOR SHARE` and re-check
  the status in the same transaction, so each is either stored before the archive or refused after it (tested with a real concurrent
  transaction: the upload waits, is refused, and leaves no row and no object).
* API: `POST /faculty/assignments/{id}/archive|restore` (optional `reason`), `GET /faculty/assignments?state=active|archived|all`,
  `GET /student/assignments/archived`, `GET /faculty/assignments/{id}/deletion-check` now also returns `action`
  (DELETE / ARCHIVE / RESTORE), `can_archive`, `student_history`.

### Verification actually executed
| Check | Result |
|---|---|
| `pytest` (isolated test DB / Redis / bucket) | **430 passed** (14 archive tests incl. the concurrent race, migration upgrade / refused-downgrade test, rewritten deletion tests) |
| Ruff, `npx prettier --check src`, `npm run lint`, `npm run build`, `npm audit` | passed; 0 vulnerabilities |
| Real browser (Edge) on a throw-away stack with migration `0003` on a fresh database (removed afterwards) | **51/51**: buttons by state, history dialog and the separate confirmation, one request on a double click, DB state + audit row, Active / Archived tabs, dashboard counts, student active list / archived list / read-only detail / feedback / file download, classmate 404, upload / late request / decision / review / deadline changes rejected, restore, draft deletion, 390 px dialog, no console errors |
| Real stack | redeployed healthy; migration `0003` applied; data unchanged (250 users, 2 PUBLISHED assignments, 1 submission, 2 reviews, 4 notifications, 0 state changes); read-only check: DBMS and os report action ARCHIVE with their history counts |

### Limitations
* Students are not notified when an assignment is archived or restored.
* Archive reasons are optional free text shown in the timeline.
* Reviews and late-request decisions on an archived assignment require a restore first (by design).

## Student login redesign with background video (frontend only)

Only the student login page changed. No backend, schema, seed, faculty page or dashboard change.
- Files: `frontend/public/videos/student-login-background.mp4` (byte-identical copy of `background videos/animation_generator_01.mp4`, 2,164,771 bytes, served at `/videos/student-login-background.mp4`), `pages/public/StudentLogin.tsx`, `components/login/LoginVideo.tsx`, `student-login.css` (all selectors `.sl-*`), `auth/useLoginForm.ts` (the existing validation and `AuthContext.login` flow, now shared), `pages/public/Login.tsx` (faculty page, markup unchanged, uses the shared hook), `app/router.tsx` (`/login/student` -> `StudentLogin`).
- Video facts: H.264 1920x1080, 24 fps, exactly 4.000 s (96 frames), one keyframe. The picture is a 1080x1080 square with 420 px black bars baked into each side of the frame; CSS `object-view-box` (with a `scale(1.78)` fallback) crops to the picture so `cover` never shows the bars. The file itself is untouched.
- Playback: one mounted `<video>` (muted, autoplay, loop, playsInline), never reloaded. A clip of 4 s or less uses the native loop (this clip); a longer clip would be restarted at 4 s by one frame-accurate check (`requestVideoFrameCallback`, `timeupdate` fallback) with a seek guard. Failed or refused video leaves the blue/teal gradient and a working form. Reduced motion: no autoplay and no entrance animation.
- Measured in Edge over 5 cycles: cycles 4.00 s, no black frame (darkest frame 90.6/255), no frame gap over 120 ms (max 84 ms), one network request for the file, no reload/pause/stall/error events. Each loop point fires `seeking` and `waiting` (a brief re-seek). The loop is NOT perfectly seamless: the last frame differs from the first (ffmpeg PSNR 21 dB vs 33 dB between normal neighbouring frames; measured pixel change at the loop point 5.4 vs a largest normal step of 2.4). For a truly invisible loop, re-encode the clip with its last frames cross-faded into the first, or with matching first and last frames, and keep a keyframe every second or so.
- Verification: `npx prettier --check`, `eslint`, build, `npm audit` (0 vulnerabilities) pass; real-browser run 43/43 (video, loop, layout at 1440 / 1366 / 1024 / 768 / 390, hover, focus, keyboard, empty and invalid input, double click, valid student login to `/student`, faculty page unchanged and working, fallback, reduced motion).

### Student login page: second pass to match the grey-blue reference
Presentation only (`student-login.css`; `StudentLogin.tsx` and `LoginVideo.tsx` unchanged, authentication untouched). Page background is now one continuous muted grey-blue composition whose grey equals the supplied video's edge colour (measured rgb(191, 193, 198) on all frames), 43% login area / 57% full-bleed visual, no rounded video box, translucent-white card with soft shadow, brand heading above the card. The picture is shown as an unframed square (cropped with `object-view-box` to remove the clip's baked-in black bars, with a short edge feather); measured colour step across the picture's edges: 3 of 255. The fallback when the video cannot play is the same grey-blue with soft tonal blobs (no cyan). Mobile stacks brand, card, then the visual at a reduced height. Browser suite 43/43 on the deployed build; one earlier run showed a single 134 ms frame gap right after a container restart, three clean re-measurements showed no gap over 100 ms (loop-point gaps 50-83 ms). Remaining differences from the reference: the clip's loop point is still a small visible jump (last frame differs from the first), and the left-side brush texture is a subtle CSS approximation, not the reference's painted texture.

## Teacher login page redesign with the classroom video (frontend only)

No backend, schema, seed, dashboard or workflow change. `/login/faculty` now renders `TeacherLogin.tsx`; the previous generic `Login.tsx` was no longer used by any route and was removed.
- Video: `background videos/Firefly create an realistic animated video where the concept is educational background and related t.mp4` (7,935,328 bytes; H.264 1920x1080, 24 fps, 8.000 s, 192 frames, no audio track, full 16:9 frame with no black bars) copied byte-identically (original kept) to `frontend/public/videos/teacher-login-background.mp4`, served at `/videos/teacher-login-background.mp4` (200, `video/mp4`, range requests 206, present in `dist`).
- Files: `pages/public/TeacherLogin.tsx` and `teacher-login.css` (new), `components/login/LoginVideo.tsx` (now takes `src`, `classPrefix`, `cycleSeconds`; defaults keep the student page's behaviour and 4-second logic exactly), `app/router.tsx`. The left column reuses the student page's `.sl-*` styles unchanged, so both pages share one identity; only the video panel (`.tl-*`) differs: a rounded (30 px), softly bordered panel set into the same grey-blue page, cool tint on its left edge, `object-fit: cover` with `object-position: 66% 50%`.
- Playback: continuous native loop (8 s cycle, no 4 s restart), one mounted element, muted/autoplay/playsInline, gradient fallback on failure, reduced motion shows the first frame.
- Authentication: same `useLoginForm('FACULTY')` -> `AuthContext.login` flow; payload `{role, login_id, password}` unchanged.
- Measured loop point: the last frame differs strongly from the first (ffmpeg PSNR 11.6 dB vs 25 dB between neighbouring frames), so the 8 s loop is a visible cut (average luminance 111 -> 127, no black frame). For an invisible loop, re-encode with a cross-fade or matching end frames.
- Verification: Prettier, ESLint, build, `npm audit` (0 vulnerabilities); real-browser teacher suite 44/44 and student suite 43/43.

### Teacher login: video-visibility fix (viewport robustness)
Reported: the page showed only a centred card on grey. Diagnosis: in a fresh Edge profile (headless and headed, default autoplay policy, no override flag) the page rendered correctly at 1440x900: left area 619 px, video panel 798x854 at x=619, playing (currentTime advancing), video responses 206; the served bundle contained the teacher page and all responses carried `Cache-Control: no-cache`. Reproduced two real weaknesses at in-between sizes (browser zoom / display scaling): below 761 px the layout stacked and the video dropped below the fold (a centred card on grey), and at 761 px the card overlapped the video panel. Fix (teacher page only, `teacher-login.css`): split layout kept from 641 px, fields allowed to shrink so the card fits its column, stacked layout only at phone widths (<= 640 px). Also removed the only console error (missing favicon) with an inline icon in `index.html`. The student page's CSS is untouched (it still has the same card overlap at ~761 px and stacks below 760 px). Verified: viewport matrix 390-1920 px (no overlap, video playing at every size), teacher suite 44/44, student suite 43/43.

## Faculty login: full-page warm beige composition

- `frontend/src/teacher-login.css` only (TSX, student CSS, video file, backend unchanged). The faculty page now has a warm grey-beige painted background across the whole viewport; the classroom video (same `/videos/teacher-login-background.mp4`, `LoginVideo`, native continuous loop) has no border/shadow/divider and is feathered on all edges into that beige (mask + light warm overlay). Mobile stacks with the clip feathered below the form.
- Verified in Edge: lint, prettier, tsc, build; `teacher.mjs` 44/44 (L4/L5 assertions updated for the borderless panel), `login.mjs` 43/43 (student page unchanged).

## Login pages: "Back to Home"

- `StudentLogin.tsx`, `TeacherLogin.tsx`, `student-login.css`: the existing Back link became a blue "← Back to Home" (ArrowLeft icon, hover darkens and nudges left, visible focus ring, 32 px target) pointing at `/` (the Landing route in `app/router.tsx`). Router `Link`, so no page reload; works when the login URL is opened directly. Auth, videos and layout untouched.

## Teacher-built quiz assignments

- Migration `0004_quiz_assignments` (additive, existing rows become `FILE`): `assignments.assignment_type/description/duration_minutes`; tables `quiz_questions`, `quiz_options` (answer key `is_correct`), `quiz_attempts` (UNIQUE per student and quiz), `quiz_answers` (one row per selected option; composite FKs force attempt, question and option to belong to the same quiz). All FKs ON DELETE RESTRICT (architecture rule). Downgrade refuses while a quiz exists.
- API: `POST/GET/PUT /faculty/quizzes`, `GET /faculty/quizzes/{id}/participation`, publish via the existing `/faculty/assignments/{id}/publish`; student `GET /student/quizzes/{id}`, `POST /student/quizzes/{id}/attempts`, `PUT /student/quiz-attempts/{id}/answers`, `POST .../submit` (idempotent), `GET .../result`. CORS now allows PUT.
- Policies: one attempt per student; questions are sent only after the attempt starts and never carry the key; attempt expires at min(deadline, start + duration) and the server closes it with the saved answers; all-or-nothing scoring (also multiple select); score shown at once, answer key only after the deadline; totals calculated by the server; file upload and late requests are refused for quizzes (late requests do not apply to quizzes); a quiz with attempts is archived, not deleted.
- UI: type selector on New assignment (both forms stay mounted so switching loses nothing), quiz builder (3 question types, reorder, duplicate, confirmed delete, live totals, preview, inline validation, beforeunload warning), faculty quiz panel with real participation, student quiz page (navigation, progress, server-checked timer, ordered autosave, confirm dialog, result).
- Browser run found and fixed two real defects: PUT missing from CORS; a shared debounce timer dropped an earlier question's save. Test data created in the real database (3 "E2E Quiz" quizzes) was removed afterwards by title and id only; counts are back to 250 users, 2 assignments, 1 submission, 4 notifications. A pg_dump taken before the migration is in the session scratchpad.
- Limitations: no overview/dashboard counters for quizzes (the existing overview counts file submissions only); no shuffle option; no frontend unit-test framework exists in the project, so the UI is covered by real-browser runs.

## Landing page redesign

- `pages/public/Landing.tsx` + new `landing.css` (`.lp-*`), asset `public/images/landing-hero.png` (cropped and 3x-upscaled from the reference screenshot, because the repo had no matching illustration; soft because of the source resolution). Header (Home, Features, For Students, For Faculty, About, Get Started), hero with exact headline and copy, Student / Faculty Login buttons to the existing routes, features / audience / about sections (system status kept under About), mobile menu, reduced-motion support. Routes, auth and other pages untouched.
- Verified in Edge at 1440 / 900 / 390: no horizontal overflow, image loads, nav anchors scroll, buttons route to `/login/student` and `/login/faculty`, no console errors; student 43/43 and teacher 44/44 suites still pass.

## Notification bell: unread count badge

- No migration: `notifications.read_at` already tracks read/unread. Added `GET /notifications/unread-count` (one COUNT of the caller's own rows) and `POST /notifications/read-all` (caller's own unread rows only). The bell polls the count every 30 s (visible tab only) and on tab focus; the full list loads only while the panel is open. The badge shows 1-99, `99+` above 99, white 2 px border; the panel gained "Mark all as read". Opening the panel marks nothing read. Logout already clears the query cache.
- Tests: `tests/api/test_notification_count.py` (7). Real-browser runs: 99+, mark one/all, no inherited badge after switching user, mobile layout. Temporary test notifications were deleted afterwards (notification count back to 4).

## Landing page: scroll-driven feature cards

- New `components/landing/FeaturesShowcase.tsx` (+ `.lp-fx-*` styles in `landing.css`), used by `Landing.tsx`; dependency `framer-motion@11.18.2` added. Five cards with inline SVG illustrations. Desktop (>= 820 px): a 320 vh wrapper holds a sticky 100 vh stage; `useScroll` progress is mapped to one MotionValue `pos` (0..4) and each card derives x / scale / rotate / y / opacity / z-index from it (no React render per scroll event; state changes only when the rounded index changes). Arrows, dots and each card's arrow button scroll the page to the matching position (scroll is the single source of truth; no wheel hijacking, no autoplay). Narrow screens and `prefers-reduced-motion`: a CSS scroll-snap carousel with the same arrows and dots. `.lp` uses `overflow-x: clip` (hidden would break sticky).
- Note: the project uses plain CSS, not Tailwind. Verified in Edge: order and reverse scrolling, centre card largest, arrows, 5 dots, 900 / 390 px, reduced motion, no overflow, console clean, login links intact. Note that `tsc --noEmit -p .` does not check the app project; `npm run build` (tsc -b) does and caught 13 SVG attribute-order errors, fixed.

## Teacher submission notifications

- Root cause: the upload service (`services/submissions.py`) never created a notification (only deadline changes, late requests, reviews and quizzes did), so a teacher was never told about a submission and the bell had nothing to count.
- Fix: `_notify_faculty` runs inside the upload transaction right after the version row is flushed (committed or rolled back together; failed uploads leave nothing). Recipient: the faculty member who owns the assignment and still teaches the subject x section. Types `SUBMISSION_NEW` / `SUBMISSION_VERSION`, dedup key `SUBMISSION:{version_id}:{faculty_id}`, text built from the database (student name and ID from the authenticated user), time in IST. `GET /faculty/submissions/{id}/locator` (404 unless it belongs to one of the teacher's assignments) backs the new `/faculty/submissions/:id` page that opens the existing student-submission page or shows "Submission not available". No migration. Bell: badge capped at `9+`, polled every 10 s (visible tab), list refetched on open and when the count changes (the browser run found the list was served from a 30 s cache), "Open submission" action, "You're all caught up." empty state.
- Existing tests that assumed no teacher notification after a setup upload now count only the notification kinds they are about. Tests: `test_submission_notifications.py` (8); backend 482 passed. Browser run against the real stack with a temporary assignment (removed afterwards, including its storage objects): badge updated without refresh in ~9 s, details, open, read, persisted after reload, unrelated teacher not notified. Submissions made before this fix have no teacher notification (no backfill).

## 24-hour deadline reminders

- `services/reminders.py`: a background asyncio task (started in the app lifespan, one pass per minute, `REMINDER_SCHEDULER_ENABLED`, off in tests) calls `send_due_reminders`. It works under a PostgreSQL advisory lock, picks PUBLISHED assignments whose current deadline is 22-24 h away, and notifies every student of the section who has not completed the work (file: no uploaded version; quiz: no submitted attempt). Stored notification `DEADLINE_REMINDER_24H`; dedup key `REMINDER_24H:{assignment}:{deadline epoch}:{student}` -> once per effective deadline; restarts and repeated runs add nothing; a deadline change obsoletes the old key (no reminder for the old deadline; a later new deadline earns one). Text shows the deadline in IST; times are UTC in the database. No migration. Tests: `test_deadline_reminders.py` (10); backend 492 passed.
- Real stack: a temporary assignment due in 23 h produced 17 reminders within a minute and showed in the student's bell; a backend restart added none; the test data was then removed. The existing computed "due within 24 hours" alert (Needs attention) is unchanged and shows alongside the stored reminder.
