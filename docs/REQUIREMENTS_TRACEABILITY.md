# AssignFlow — Requirements Traceability

Team CODE24 · CBC 2.0 · Problem Statement 73
Source: `architecture.md` §4, §6, §7, §20, §24, §27, §28, §29 (last updated 2026-10-10).
Status: **Draft — Phase 0. Nothing is implemented; no test has been run.**

> §28 maps to the **draft** deck's six features (conflict X3, `architecture.md` §1.1). Re-check against the submitted PPT once it is provided.

Legend — Status: ☐ not started · ◐ in progress · ☑ done and test passed (update only with evidence in `IMPLEMENTATION_LOG.md`).

## 1. Core requirement matrix (architecture §28)

| Req | Requirement | Deck feature / slide | Planned implementation | Acceptance test | Demo step (§29) | Phase | Status |
|---|---|---|---|---|---|---|---|
| R1 | Faculty create assignments with deadlines for authorized subject + section | F2 / s4–5 | Endpoints #5–#7; `assignments`, `teaching_assignments` | AT8 (also AT7, AT9) | 2 | 4 | ☑ API + UI (create, draft, publish, list, view); AT7–AT9 executed and passing; verified in a real browser |
| R2 | Deadline management, changes with preserved history | F2, F4 / s5 | Endpoint #8; `deadline_changes`; `services/deadlines` | AT16 | 8 | 4 | ☑ API + UI (deadline change + history); AT16 executed and passing; verified in a real browser |
| R3 | Students submit files | F3 / s4–5 | Endpoint #17; `services/submissions`, `services/storage` (MinIO) | AT10 (also AT25) | 4 | 5 | ☑ API + UI; AT10 and AT25 executed and passing; verified in a real browser |
| R4 | Server-validated late/missing detection (Pending / On time / Late / Missing) | F3 / s5 | `services/status`, `services/eligibility`, `core/clock` | AT11, AT12, AT13, AT14 | 4, 5, 6 | 5, 6 | ☑ API + UI. Phase 5: PENDING / MISSING / ON_TIME / LATE (first-version rule, per-version deadline snapshots). Phase 6: LATE now arises through the approved window and is shown "Late (approved)", never on time. AT11–AT14 executed and passing; verified in a real browser |
| R5 | Resubmission creates versions; earlier versions preserved | F4 / s5 | `submission_versions` (insert-only), `UNIQUE(submission_id, version_no)` | AT15 | 5 | 5 | ☑ API + UI; AT15 executed and passing; verified in a real browser |
| R6 | Submission status and history visible | F4 / s5, s7 | Endpoints #9, #10, #16; Timeline | AT15, AT16 | 5, 9 | 5, 7 | ☑ API + UI: roster #9, versions and the full timeline with "why this status" for faculty #10 and students #16, downloads; AT15, AT16 executed and passing; verified in a real browser |
| R7 | Faculty review; final status recorded | PS workflow / s4 | Endpoint #11; `reviews`; `services/reviews` | AT24 | 10 | 7 | ☑ API + UI (record review, append-only history, notification to the student); AT24 executed and passing; verified in a real browser |
| R8 | Roster-only ID + password login (50 faculty, 200 students, fictional) | F1 / s5 | Endpoints #1–#3; `db/seeds/*`; Argon2 | AT1, AT2, AT3, AT4 | 1, 3 | 2, 3 | ☑ API: seed (Phase 2) + login/logout/me (Phase 3); AT1–AT4 executed and passing. Login UI built but not exercised in a real browser. |
| R9 | Visibility by semester / section / subject mapping | F1 / s5, s7 | Scope checks (§8.2); `student_profiles`, `teaching_assignments` | AT6, AT7, AT9 | 3 | 3, 4 | ☑ scope rules enforced on every implemented endpoint (assignments, submissions, versions, files); AT6, AT7, AT9 executed and passing |
| R10 | Teacher-approved late request (reason, decision, note, limited window) | F5 / s5, s7 | Endpoints #12, #14, #18; `late_requests`; `services/late_requests` | AT17, AT18, AT19, AT20 (also AT13) | 6, 7 | 6 | ☑ API + UI (request, list, inspect, approve/reject, 1–72 h window, derived EXPIRED/USED, LATE_APPROVED uploads); AT13, AT17–AT20 executed and passing; verified in a real browser. The faculty "new request" and student "request decided" alerts (FR-17) are Phase 7 |
| R11 | Deadline Integrity Timeline | F4 / s7 | `services/timeline`; endpoints #10, #16; `Timeline.tsx` | AT16 | 9 | 7 | ☑ API + UI (stored records only, derived markers flagged, student sees own); executed and passing; verified in a real browser |
| R12 | In-app alerts + faculty overview with real counts and filters | F6 / s5 | Endpoints #13, #20, #21; `services/overview`, `alerts`, `notifications` | AT22 | 3, 11 | 7 | ☑ API + UI (Health Board from SQL, stored notifications with dedup, computed alerts, unread count, mark as read); AT22 executed and passing; verified in a real browser |
| R13 | Security: hashed passwords, server-side role/ownership checks, private files, server UTC time | s6, s8 | §13, §18, §19; `core/security`, `core/deps` | AT4, AT5, AT6, AT7, AT21, AT25 | 3 (role-blocked action) | 3, 5 | ◐ (Phase 5 added private storage, content-type and size validation, authenticated downloads and server-side timestamps. Phase 3: Argon2, JWT, denylist, rate limits, fail-closed Redis, role guards and scope helpers done and tested; private files and upload checks wait for Phase 5) |
| — | Docker-first, reproducible, no cloud account | brief §6 (deck: fallback) | §10, §26; `docker-compose.yml`, Dockerfiles | AT23 | Setup | 1, 8, 9 | ☐ |

## 2. Functional requirements → requirement, endpoint, test

| FR | Behaviour (short) | Req | Endpoint(s) | Test(s) | Phase |
|---|---|---|---|---|---|
| FR-01 | Landing: Faculty Login / Student Login | R8 | — (frontend `/`) | Manual E2E | 3 (landing + login entry points built; not exercised in a real browser) |
| FR-02 | Login with ID + password; active, hash match, role match | R8, R13 | #1 | AT2, AT3, AT4 | 3 ☑ |
| FR-03 | Logout revokes token | R13 | #2 | AT21 | 3 ☑ (revocation tested; download part of AT21 in Phase 5) |
| FR-04 | Student dashboard (profile, subjects, assignments, status) | R6, R9 | #3, #15 | AT9; Manual E2E | 4 ◐ (student list shows title, subject, faculty, deadline, countdown and PENDING/MISSING; review status and feedback arrive in later phases), 7 |
| FR-05 | Faculty sees teaching mappings | R9 | #3 | AT7 | 3 ☑ (`/auth/me` teaching list tested; AT7 itself is Phase 4) |
| FR-06 | Create assignment (own subject × section; publish or draft) | R1 | #5 | AT7, AT8 | 4 ☑ |
| FR-07 | Publish a draft | R1 | #6 | AT8 | 4 ☑ |
| FR-08 | Change deadline with optional reason, logged | R2 | #8 | AT16 | 4 ☑ |
| FR-09 | Student upload when eligible; server timestamp; new version | R3, R4, R5 | #17 | AT10–AT15 | 5 ☑ |
| FR-10 | Version history; authorized downloads | R5, R6, R13 | #16, #9, #10, #19 | AT15, AT21 | 5 ☑ |
| FR-11 | Missing student submits one late request | R10 | #18 | AT17 | 6 ☑ |
| FR-12 | Faculty approves (1–72 h, default 24) or rejects | R10 | #12, #14 | AT18 | 6 ☑ |
| FR-13 | Upload in approved window → Late (approved) | R10, R4 | #17 | AT13, AT19, AT20 | 6 ☑ |
| FR-14 | Review: Under review / Accepted / Revision requested + feedback | R7 | #11 | AT24 | 7 ☑ |
| FR-15 | Deadline Integrity Timeline (students: own data only) | R11 | #10, #16 | AT16 (plus AT6 for scope) | 7 ☑ |
| FR-16 | Faculty overview with real counts and filters | R12 | #13, #9 | AT22 | 7 ☑ |
| FR-17 | In-app alerts (24 h, 3 h, missing, window, decision, feedback; faculty: new requests) | R12 | #20, #21 | Manual E2E (no dedicated AT — see issue I4) | 7 ☑ (executed in tests and the browser run) |

## 3. Non-functional requirements → verification

| NFR | Target | Verification | Phase |
|---|---|---|---|
| Reproducibility | `docker compose up --build` starts full stack, no cloud | AT23 | 1, 8 |
| Correctness | Timing incl. exactly-at-deadline and deadline changes | AT11–AT16 (frozen-clock unit tests) | 5 |
| Security | Server-side authz, Argon2, private files, no secrets in Git, CORS limited | AT4–AT7, AT21, AT25; DoD #7 | 3, 5 |
| Integrity | Versions, deadline changes, decisions, reviews insert-only | DB constraint tests (§24.1) | 2 (constraints, FK RESTRICT and uniqueness tested; insert-only is by convention, no DB trigger) |
| Performance | List endpoints < 500 ms locally (250 users) | Manual check during Phase 8 | 8 |
| Usability | Status badges; loading/empty/error states; laptop + phone widths | Manual E2E; DoD #6 | 7, 8 |
| Observability | Structured logs without secrets; `/health` shows db/redis/storage | Manual check; health endpoint test | 1, 8 |

## 4. Acceptance tests → requirement and phase

| AT | Test (short) | Req | Type | Phase |
|---|---|---|---|---|
| AT1 | Seed: exactly 50 FACULTY + 200 STUDENT; re-run changes nothing | R8 | DB | 2 |
| AT2 | Faculty login → 200 + FACULTY | R8 | API | 3 ☑ executed, passing |
| AT3 | Student login → 200 + STUDENT | R8 | API | 3 ☑ executed, passing |
| AT4 | Identical 401 for bad creds; 6th failure → 429 | R8, R13 | API | 3 ☑ executed, passing |
| AT5 | Student `POST /faculty/assignments` → 403 | R13 | API | 4 ☑ executed, passing (real endpoint) |
| AT6 | Student A cannot access student B's data/file → 404 | R9, R13 | API | 4/5 ☑ executed, passing (assignment, versions and file downloads) |
| AT7 | Faculty scope: FAC049 / other faculty's class → 403; other's assignment → 404 | R1, R9, R13 | API | 4 ☑ executed, passing |
| AT8 | Create in own slot → 201; draft invisible to students | R1 | API | 4 ☑ executed, passing |
| AT9 | Same-section student sees it; other section does not | R9 | API | 4 ☑ executed, passing |
| AT10 | Valid PDF upload → 201, v1, server `uploaded_at` | R3 | API | 5 ☑ executed, passing |
| AT11 | Upload at deadline − 1 s → ON_TIME | R4 | Unit + API | 5 ☑ executed, passing |
| AT12 | Upload exactly at deadline → ON_TIME | R4 | Unit + API | 5 ☑ executed, passing |
| AT13 | Deadline + 1 s: approved → Late (approved); otherwise 409 | R4, R10 | API | 5/6 ☑ executed, passing (both halves: unapproved → 409 `DEADLINE_PASSED`; approved → LATE_APPROVED, timing LATE) |
| AT14 | No submission: now > deadline → MISSING; else PENDING | R4 | Unit + API | 4 ☑ executed, passing (unit test incl. exactly-at-deadline = PENDING; student list API) |
| AT15 | v2 created; v1 row + object intact; RESUBMITTED; identical file → 409 | R5, R6 | API | 5 ☑ executed, passing |
| AT16 | Deadline extension: history row; `original_deadline` unchanged; recompute; past date → 422 | R2, R6, R11 | API | 4 ☑ executed, passing (recompute verified for PENDING/MISSING; first-version rules in Phase 5) |
| AT17 | MISSING student request → 201; duplicate → 409; non-missing → 409 | R10 | API | 6 ☑ executed, passing |
| AT18 | Owner approves/rejects → 200; other faculty → 404; student → 403; second decision → 409 | R10 | API | 6 ☑ executed, passing (incl. concurrent decisions: one winner) |
| AT19 | Upload inside window → 201 LATE_APPROVED | R10 | API | 6 ☑ executed, passing |
| AT20 | Upload after `window_end` → 409; request shows EXPIRED | R10 | API | 6 ☑ executed, passing |
| AT21 | Cross-student download → 404; no token → 401; revoked token → 401 | R13 | API | 3/5 ☑ executed, passing (cross-student, cross-section and cross-faculty downloads → 404; no token and revoked token → 401) |
| AT22 | Overview counts match independent SQL; buckets sum to expected | R12 | API | 7 ☑ executed, passing (independent SQL comparison on a mixed scenario) |
| AT23 | Fresh clone → `.env` → `docker compose up --build` → §29 works offline | Docker-first | E2E manual | 8 ☐ not executed: a fresh-clone run needs the published ports (5173, 8000) and a clean volume set, so it cannot run next to your live stack without stopping it; proposed for Phase 9 |
| AT24 | Late + Accepted together; ACCEPTED blocks upload; REVISION_REQUESTED allows after-deadline upload | R7 | API | 7 ☑ executed, passing (reviews recorded through the API) |
| AT25 | Content/extension mismatch → 415; over size → 413 | R3, R13 | Storage | 5 ☑ executed, passing |

Every AT1–AT25 appears above; none is orphaned.

## 5. Demo steps → requirement coverage (architecture §29)

| Step | Action | Requirements shown |
|---|---|---|
| 1 | Faculty login (`FAC001`); overview with real counts | R8, R12 |
| 2 | Create "[DEMO] Lab 4" for CSE-5A, deadline now + 4 min, PDF only; publish | R1 |
| 3 | Student A login: profile, section, subjects, assignment, DUE_3H alert; role-blocked check | R8, R9, R12, R13 |
| 4 | Student A uploads v1 → ON_TIME | R3, R4 (built; verified in a real browser) |
| 5 | Student A uploads v2 → RESUBMITTED; v1 downloadable | R4, R5, R6 (built; verified in a real browser) |
| 6 | Deadline passes: Student B MISSING; Student C blocked (`DEADLINE_PASSED`) | R4, R10 (MISSING and DEADLINE_PASSED verified in a real browser with a real deadline; the late-request part is Phase 6) |
| 7 | Student B requests; faculty approves (1 h); upload → Late (approved) | R10 (built; verified in a real browser with a real deadline: request → approve → upload → Late (approved); the demo seed script itself is Phase 9) |
| 8 | Faculty extends deadline; history shown | R2 |
| 9 | Deadline Integrity Timeline for Student B + "why this status" | R6, R11 | (built; verified in a real browser)
| 10 | Faculty review → Accepted with feedback (Late + Accepted) | R7 | (built; verified in a real browser)
| 11 | Overview counts updated | R12 | (built; verified in a real browser)

Fallback: second `[DEMO]` assignment with 2-min deadline (§29).

## 6. Problem Statement 73 coverage

| PS73 item | Covered by |
|---|---|
| Assignment and deadline management | R1, R2 |
| Student submission | R3 |
| Late/missing detection | R4 |
| Resubmission handling | R5 |
| Submission status/history | R6, R11 |
| Edge: submission after deadline | R4, R10 (AT13, AT20) |
| Edge: multiple versions | R5 (AT15) |
| Edge: deadline changes | R2 (AT16) |
| Stretch: late-risk alerts / analytics | R12 (alerts, overview) |
| Demo: before/after-deadline submit, late + resubmission | §29 steps 4–7 |

## 7. Issues found while building this matrix

| # | Issue | Suggested handling |
|---|---|---|
| I1 | The "Test" column in §28 for R6 and R11 relies on AT15/AT16 only. The timeline (events, "why this status") has no dedicated AT. | Propose adding an AT for timeline event ordering/content — needs your approval (it would add to the agreed AT list). |
| I2 | R12's alerts have no dedicated AT; AT22 covers only overview counts. | Same as I1; otherwise covered by manual E2E. |
| I3 | R7 AT24 mixes review statuses and upload eligibility; it also covers eligibility rule 2/4. | No change; noted for Phase 7 test design. |
| I4 | FR-17 lists alerts but not the stored "Deadline changed → students" notification that §22 defines. | Treat §22 as authoritative; confirm. |
| I5 | The demo uses `FAC001` for `CSE-5A`, but §13.4 does not say which slot is `FAC001`'s. | Fix in the seed config so FAC001 ↔ a CSE-5A subject (Phase 2). |
| I6 | The matrix points to the draft deck (X3). | Re-verify after the submitted PPT is available. |

## 8. Progress log (updated only with executed evidence)

| Phase | What changed | Evidence |
|---|---|---|
| 2 | AT1 is covered and passing: exactly 50 FACULTY + 200 STUDENT, and a second seed/init run changes nothing (`tests/db/test_seed.py`, `tests/db/test_init.py`). | `docker compose run --rm backend pytest` → 37 passed (see `IMPLEMENTATION_LOG.md`) |
| 2 | Database constraint tests (unique login IDs, subject codes, teaching slots, submissions, versions, late requests, enum/CHECK rejection, FK RESTRICT) pass. These support R5, R10 and R13 but those requirements remain not started at feature level. | same run |
| 2 | Partial: R8 (seeded accounts, Argon2 hashes) and R9 (mapping data). All other requirements are unchanged (not started). | — |
| 3 | Auth: login (both roles), `GET /auth/me`, logout with Redis `jti` revocation, JWT HS256 (2 h), per-IP 10/min (SlowAPI) and per-ID 5/10 min limits, fail-closed Redis, role guards, 404/403 scope helpers, frontend login + route guards. AT2, AT3, AT4 pass; AT5/AT6/AT7/AT21 partially covered (see rows above). | `docker compose run --rm backend pytest` → 78 passed (see `IMPLEMENTATION_LOG.md`) |
| 4 | Assignment management: faculty create (draft or publish), list, view, edit drafts, publish, deadline change with history; student list and detail scoped to own section; faculty and student pages in the UI. AT5, AT7, AT8, AT9, AT14, AT16 pass; AT6 partial. R1 and R2 done at API + UI level; R4 and R9 partial. | `docker compose run --rm backend pytest` → 120 passed; browser run 22/22 (see `IMPLEMENTATION_LOG.md`) |
| 5 | Submission engine: upload pipeline (extension + content-type + archive + size validation, server-generated keys in the private bucket), immutable versions with per-version deadline snapshots, status engine (PENDING / MISSING / ON_TIME / LATE, first-version rule), upload eligibility (reviews read-only), authenticated downloads, faculty roster and per-student versions, student submission UI. AT6, AT10, AT11, AT12, AT14, AT15, AT21, AT25 pass; AT13 and AT24 partial. R3, R5 and R9 done at API + UI level; R4, R6, R13 partial. | `docker compose run --rm backend pytest` → 203 passed; browser run 27/27 (see `IMPLEMENTATION_LOG.md`) |
| 6 | Late requests: student request (reason 20–1000, one per assignment, only while MISSING), faculty list / inspect / approve (1–72 h, default 24) / reject, race-safe single decision, derived EXPIRED / USED, eligibility rule 5 (LATE_APPROVED inside `[window_start, window_end]`) enforced on the server and re-checked under the submission lock, request badges and "Late (approved)" in the UI. AT13, AT17, AT18, AT19, AT20 pass. R4 and R10 done at API + UI level; alerts for requests wait for Phase 7. | `docker compose run --rm backend pytest` → 268 passed; browser run 40/40 (see `IMPLEMENTATION_LOG.md`) |
| 7 | Reviews (append-only, latest-version scoped, feedback private to student and teacher), Deadline Integrity Timeline with "why this status", Faculty Submission Health Board (one row per student per assignment, SQL aggregation, filters), stored notifications (late request, decision, review, deadline change; dedup keys) and computed alerts, bell with unread count and mark-as-read, all wired in the UI. AT22 and AT24 pass. R6, R7, R11, R12 done at API + UI level. | `docker compose run --rm backend pytest` → 335 passed; browser run 36/36 (see `IMPLEMENTATION_LOG.md`) |
| 8 | Final QA: full regression (349 backend tests, Ruff, ESLint, Prettier, build, `npm audit` 0 vulnerabilities), generated authorization matrix, isolation matrix, session lifecycle on newer endpoints, 500 envelope, randomized-workflow invariants (new `test_qa_regression.py`, 14 tests); real-browser run 50/50 covering every acceptance workflow and R1–R13; 2 application defects fixed and re-verified (session lost on API outage; bell panel / top bar overflow on narrow screens). AT1–AT22 and AT24, AT25 remain executed and passing; AT23 (fresh-clone reproducibility) was NOT executed in Phase 8 (it needs the published ports and a clean volume set, so it cannot run beside your live stack); proposed for Phase 9. | `docker compose run --rm backend pytest` → 349 passed; browser run 50/50 (see `IMPLEMENTATION_LOG.md`) |

## 6. Enhancement round 2 (Phase B)

| Requirement | Implementation | Verification | Status |
|---|---|---|---|
| E1 Faculty reference documents (PDF/PPT/PPTX), private storage, locked after publish | migration `0002`, `services/attachments.py`, `POST/DELETE /faculty/assignments/{id}/attachments`, create/draft forms, student section | `tests/api/test_attachments.py`, browser run B1-B12, C1-C3, D1-D5, E1-E3 | Done (Phase B) |
| E2 View and Download side by side; in-app preview for PDF and images; PPT/PPTX honest message | `/files/{versions,materials}/{id}/preview` + download, `DocumentPreview`, `FileActions`, `VersionList` | `test_attachments.py` (headers, 415, scope), browser run B7-B12, E4-E8, F1-F8 | Done (Phase B) |
| E3 Google Forms quiz activities | not started | not run | Phase E |
| E4 Student work ordered by deadline | not started | not run | Phase D |
| E5 Late-request supporting documents (multipart) | not started | not run | Phase C |
| E6 Missing-assignment notifications | not started | not run | Phase F |
| E7 Dataset: 15 faculty, 50 students (5A 17 / 5B 17 / 5C 16), Indian names | `seed_config.py`, `seed_names.py`, `transition_dataset.py` | `tests/db/test_seed.py`, fresh-database browser run A1-A6; **transition on the real database NOT applied (awaiting approval)** | Code done; data transition pending |

## 7. Section filtering and assignment deletion

| Requirement | Implementation | Verification | Status |
|---|---|---|---|
| Section / subject filters work end to end, authorised options only | `scope.require_filter_scope`, filters on overview, students, assignment list, late requests; `ScopeFilters` | `tests/api/test_section_filters_and_delete.py`, browser run B1-B20, C1-C5, D1-D4, E1 | Done |
| Counts per student-assignment pair, versions never inflate | single SQL grid in `services/overview.py` | `test_versions_never_inflate_the_counts`, browser B6, D4 | Done |
| Intended dataset 17 / 17 / 16 | seed config; transition tool | fresh-database browser check A1 (17/17/16); real database still 25 per section until the transition is applied | Code done, data pending approval |
| Faculty delete with protection of history | `services/assignment_deletion.py`, `DELETE` + `deletion-check`, `DeleteAssignmentDialog` | 15 deletion tests, browser F1-F14, G2 | Done (no archive state: not implemented) |

## 8. Archive / restore and draft-only deletion

| Requirement | Implementation | Verification | Status |
|---|---|---|---|
| Permanent deletion only for eligible drafts | `services/assignment_deletion.py` (409 `NOT_A_DRAFT` otherwise) | `tests/api/test_section_filters_and_delete.py`, browser D1, E9 | Done |
| Archive published assignments (with or without history), reversible, history preserved | migration `0003`, `services/assignment_archive.py`, `archive_guard.py`, routes, `AssignmentActionDialog` | `tests/api/test_archive.py` (14), `test_migration.py`, browser B1-B21, R1-R5 | Done |
| Archived: gone from active student work, no new submissions / late requests, history still readable, files downloadable | scope rules, guards in upload / late request / review / decision / deadline | `test_archive.py`, browser S1-S8, E1-E8 | Done |
| Faculty dashboard distinguishes active from archived; counts and section filters update | `state` filter, overview excludes archived, dashboard "n archived" | `test_archive.py`, browser B16-B18, R5 | Done |
| Concurrency, authorization, audit event | row locks; owner-only (404 / 403 / 401); `assignment_state_changes` + timeline events | `test_an_upload_racing_an_archive...`, `test_only_the_owner...`, `test_the_timeline_shows...` | Done |
