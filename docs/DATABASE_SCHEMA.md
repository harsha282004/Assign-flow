# AssignFlow — Database Schema (as implemented)

Source of truth: Alembic migration `backend/alembic/versions/0001_initial_schema.py` (revision `0001`), generated from the
SQLAlchemy 2.0 models in `backend/app/db/models/` and reviewed. A test (`test_migration_matches_models`) fails if the
models and the migration ever diverge. Design reference: `architecture.md` §14.

## Conventions (as built)

- PostgreSQL 16, primary keys are `uuid` (`gen_random_uuid()` server default, `uuid4` in Python).
- All timestamps are `timestamptz` (UTC). `created_at`/`updated_at`/`requested_at`/`changed_at`/`reviewed_at` default to `now()`; business timestamps such as `uploaded_at`, `decided_at` and `window_*` are supplied by the application from the server clock (later phases).
- **Every foreign key is `ON DELETE RESTRICT`** (verified by test). Nothing is cascade-deleted; users are deactivated, not deleted.
- Constraint names follow a naming convention (`pk_`, `uq_`, `ck_`, `fk_`, `ix_` prefixes).
- Insert-only tables (`submission_versions`, `deadline_changes`, `reviews`, `notifications` except `read_at`) are insert-only **by application convention**; no database trigger enforces it in Phase 2.

## Enum types

| Type | Values |
|---|---|
| `user_role` | FACULTY, STUDENT |
| `assignment_status` | DRAFT, PUBLISHED |
| `upload_context` | REGULAR, LATE_APPROVED, REVISION |
| `late_request_status` | PENDING, APPROVED, REJECTED |
| `review_status` | UNDER_REVIEW, ACCEPTED, REVISION_REQUESTED |

`users.role` is enforced by the `user_role` enum type, which replaces the blueprint's `CHECK role IN (...)` with an equivalent constraint. `EXPIRED` for late requests is derived at read time, not stored.

## Tables

| Table | Columns (type) | Constraints and indexes |
|---|---|---|
| `users` | id, login_id (varchar 32), full_name (150), role (`user_role`), password_hash (255), is_active (default true), created_at, updated_at | PK id; UNIQUE login_id |
| `sections` | id, semester (int), name (10), label (30) | UNIQUE (semester, name); UNIQUE label; CHECK semester BETWEEN 1 AND 8 |
| `subjects` | id, code (20), name (150), semester | UNIQUE code; CHECK semester BETWEEN 1 AND 8 |
| `student_profiles` | user_id (PK, FK users), section_id (FK sections) | index on section_id. Role STUDENT is verified by the seed (and later the service layer), not by the database. |
| `teaching_assignments` | id, faculty_id (FK users), subject_id (FK), section_id (FK) | UNIQUE (subject_id, section_id); index on faculty_id. Matching semesters are verified by the seed. |
| `assignments` | id, title (150), instructions (5000), subject_id, section_id, created_by (FK users), status (default DRAFT), original_deadline, deadline, allowed_types (text[]), max_file_mb (default 10), published_at, created_at, updated_at | CHECK max_file_mb BETWEEN 1 AND 10; index (section_id, status); index created_by |
| `deadline_changes` | id, assignment_id (FK), old_deadline, new_deadline, changed_by (FK users), changed_at, reason (500, nullable) | index (assignment_id, changed_at) |
| `submissions` | id, assignment_id (FK), student_id (FK users), created_at, latest_version_no (default 0) | UNIQUE (assignment_id, student_id); CHECK latest_version_no >= 0 |
| `submission_versions` | id, submission_id (FK), version_no, storage_key (300), original_filename (200), mime_type (100), size_bytes (bigint), sha256 (64), uploaded_at, uploaded_by (FK users), deadline_at_upload, upload_context (`upload_context`), late_request_id (FK late_requests, nullable) | UNIQUE (submission_id, version_no); UNIQUE storage_key; CHECK version_no >= 1; CHECK size_bytes > 0; CHECK char_length(sha256) = 64; CHECK (upload_context = 'LATE_APPROVED') = (late_request_id IS NOT NULL) |
| `late_requests` | id, assignment_id (FK), student_id (FK users), reason (1000), requested_at, deadline_at_request, status (default PENDING), decided_by (FK users, nullable), decided_at, decision_note (500), window_start, window_end | UNIQUE (assignment_id, student_id); CHECK reason length 20–1000; CHECK (status = 'PENDING') = (decided_by IS NULL AND decided_at IS NULL); CHECK (status = 'APPROVED') = (window_start IS NOT NULL AND window_end IS NOT NULL); CHECK window_end > window_start; index (assignment_id, status) |
| `reviews` | id, submission_id (FK), version_id (FK submission_versions), reviewer_id (FK users), status (`review_status`), feedback (2000, nullable), reviewed_at | index (submission_id, reviewed_at DESC) |
| `notifications` | id, user_id (FK users), type (50), title (200), body (1000), ref_type (50), ref_id (uuid), dedup_key (200), created_at, read_at | UNIQUE dedup_key; index (user_id, read_at, created_at DESC) |

Plus Alembic's own `alembic_version` table (current revision: `0001`). That makes 12 application tables.

### Choices that go slightly beyond the blueprint text
These are my reading of §14 where it was not explicit (all easy to change before Phase 3):
- `reviews.feedback` is nullable (an "Accepted" review may carry no text).
- `size_bytes > 0`, `char_length(sha256) = 64`, `version_no >= 1`, `latest_version_no >= 0` and `window_end > window_start` CHECKs were added as sanity guards consistent with §16/§18/§17.
- `submissions.latest_version_no` starts at 0 so the first version is `latest + 1` (§16.2).
- Column lengths for `notifications.type/title/body/ref_type` and `submission_versions.storage_key/mime_type` are my choice.

## Relationships

```
users 1─0..1 student_profiles ─N..1 sections
users(faculty) 1─N teaching_assignments N─1 subjects ; teaching_assignments N─1 sections
users 1─N assignments N─1 subjects ; assignments N─1 sections
assignments 1─N deadline_changes ; assignments 1─N submissions ; assignments 1─N late_requests
submissions 1─N submission_versions ; submissions 1─N reviews ; submission_versions 1─N reviews
late_requests 0..1─N submission_versions ; users 1─N notifications
```

## Seeded data (Phase 2)

Defined in `backend/app/db/seeds/seed_config.py` (edit there to change the dataset). Names use Faker `en_IN`, seed 73, Faker pinned at 40.43.0.

| Item | Result |
|---|---|
| Sections | 8: CSE-1A, 1B, 3A, 3B, 5A, 5B, 7A, 7B |
| Students | 200: `STU0001`–`STU0200`, 25 per section in section order (`STU0101`–`STU0125` are in CSE-5A) |
| Subjects | 24: `CS101`–`CS106`, `CS301`–`CS306`, `CS501`–`CS506`, `CS701`–`CS706` |
| Faculty | 50: `FAC001`–`FAC050` |
| Teaching slots | 48 (24 subjects × 2 sections). `FAC001` is pinned to **CS503 Database Systems in CSE-5A** (demo class). Remaining slots go in (semester, section, subject code) order to `FAC002`–`FAC048`. |
| Unassigned faculty | `FAC049`, `FAC050` have no teaching slot (scope-enforcement tests, AT7) |
| Passwords | One demo password from `SEED_DEMO_PASSWORD`, hashed per account with Argon2 (pwdlib), unique salt each. Existing accounts are never re-hashed. |

## Enhancement round 2, Phase B additions

### Table `assignment_attachments` (migration `0002`, additive: no existing table or row changes)
Reference documents (PDF / PPT / PPTX) that faculty attach to an assignment. The bytes live in the private MinIO bucket.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | `gen_random_uuid()` |
| assignment_id | UUID FK -> assignments.id | `ON DELETE RESTRICT` |
| original_filename | varchar(200) | sanitised display name only; never used in a storage path |
| storage_key | varchar(300) UNIQUE | server-generated: `materials/<assignment_id>/<uuid>.<ext>` |
| mime_type | varchar(100) | detected from the file content, not from the browser |
| size_bytes | bigint | `CHECK size_bytes > 0` |
| uploaded_by | UUID FK -> users.id | `ON DELETE RESTRICT` |
| created_at | timestamptz | server clock |

Index `ix_assignment_attachments_assignment_created (assignment_id, created_at)`. Rows are added or removed only while the
assignment is a DRAFT (the API answers 409 `ATTACHMENTS_LOCKED` afterwards). `find_orphans.py` knows both prefixes
(`submissions/`, `materials/`), so reference materials are never reported or deleted as orphans.

### Demo dataset (replaces the 50 / 200 and the unapplied 15 / 100 definitions)
Defined in `backend/app/db/seeds/seed_config.py` and `seed_names.py` (curated, fictional Indian names; no Faker).

| Item | Definition |
|---|---|
| Sections | 3: CSE-5A, CSE-5B, CSE-5C (semester 5) |
| Students | **50**: `STU0101`-`STU0150`: CSE-5A 17 (0101-0117), CSE-5B 17 (0118-0134), CSE-5C 16 (0135-0150) |
| Subjects | 6: CS501-CS506 |
| Faculty | **15**: `FAC001`-`FAC015` |
| Teaching slots | 18 (6 subjects x 3 sections). `FAC001` is pinned to CS503 in CSE-5A; the other 17 slots are dealt round-robin to `FAC002`-`FAC015`, so every faculty member teaches 1-2 classes and each class has one teacher |
| Names | 65 distinct names built from 60 first names and 30 surnames (see `docs/DEMO_DATASET_NAME_MAPPING.md`) |
| Passwords | one Argon2 hash per account from `SEED_DEMO_PASSWORD`; existing accounts are never re-hashed |

An existing database is moved to this dataset only by `python -m app.db.transition_dataset` (dry run by default; `--apply`
runs one transaction and refuses when any record would be affected). Dry-run result: `docs/DATASET_TRANSITION_DRYRUN.md`.

## Migration `0003`: archived assignments (additive)

* `assignment_status` gains the value `ARCHIVED` (DRAFT, PUBLISHED, ARCHIVED).
* `assignments.archived_at timestamptz NULL`, `assignments.archived_by uuid NULL -> users.id (RESTRICT)`, and
  `CHECK ((status = 'ARCHIVED') = (archived_at IS NOT NULL))`.
* New insert-only table `assignment_state_changes` (`id`, `assignment_id -> assignments RESTRICT`, `from_status`, `to_status`,
  `changed_by -> users RESTRICT`, `changed_at`, `reason varchar(500) NULL`), index `(assignment_id, changed_at)`. One row per
  archive / restore, shown in the Deadline Integrity Timeline.
* No existing row is modified. The downgrade refuses (RuntimeError, nothing changed) while an archived assignment exists; otherwise it
  drops the new objects and rebuilds the enum without `ARCHIVED`.
