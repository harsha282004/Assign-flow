"""Teacher-built quizzes: definition, publishing, scope, attempts, server-side grading, release policy."""

from datetime import timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from tests.api.test_assignments import API, NOW, World, auth, iso


@pytest.fixture
def world(client, test_password, freeze_time) -> World:
    w = World(client, test_password, freeze_time)
    w.password = test_password
    return w


def later(w: World, freeze_time, moment) -> None:
    """Move the frozen clock forward and sign in again (access tokens are short-lived)."""
    freeze_time(moment)
    w.stu_5a = w._login("STUDENT", "STU0101", w.password)


def question(kind="SINGLE_CHOICE", marks=2, correct=(0,), n=3, text_="Which is a relational database?"):
    if kind == "TRUE_FALSE":
        options = [{"text": "True", "is_correct": correct[0] == 0}, {"text": "False", "is_correct": correct[0] == 1}]
    else:
        options = [{"text": f"Option {i + 1}", "is_correct": i in correct} for i in range(n)]
    return {"question_type": kind, "text": text_, "marks": marks, "options": options}


def quiz_body(w: World, **over) -> dict:
    body = {
        "title": "Normalisation quiz",
        "description": "Short quiz",
        "instructions": "Answer all questions.",
        "subject_id": w.slot1["subject"]["id"],
        "section_id": w.slot1["section"]["id"],
        "deadline": iso(NOW + timedelta(days=2)),
        "questions": [
            question("SINGLE_CHOICE", 2, (1,)),
            question("MULTIPLE_SELECT", 3, (0, 2), n=4),
            question("TRUE_FALSE", 1, (1,)),
        ],
    }
    body.update(over)
    return body


def create(w, token=None, **over):
    return w.client.post(f"{API}/faculty/quizzes", json=quiz_body(w, **over), headers=auth(token or w.fac1))


def publish(w, quiz_id, token=None):
    return w.client.post(f"{API}/faculty/assignments/{quiz_id}/publish", headers=auth(token or w.fac1))


def published_quiz(w, **over) -> dict:
    quiz = create(w, **over).json()
    assert publish(w, quiz["id"]).status_code == 200
    return quiz


def start(w, quiz_id, token=None):
    return w.client.post(f"{API}/student/quizzes/{quiz_id}/attempts", headers=auth(token or w.stu_5a))


def answers_for(quiz: dict, picks: dict[int, list[int]]) -> list[dict]:
    """picks: question index -> option indexes."""
    return [
        {"question_id": quiz["questions"][qi]["id"], "option_ids": [quiz["questions"][qi]["options"][oi]["id"] for oi in ois]}
        for qi, ois in picks.items()
    ]


def submit(w, attempt_id, answers=None, token=None):
    return w.client.post(
        f"{API}/student/quiz-attempts/{attempt_id}/submit",
        json={"answers": answers} if answers is not None else None,
        headers=auth(token or w.stu_5a),
    )


# --- creating and publishing ------------------------------------------------------------------------------------

def test_faculty_creates_a_draft_quiz_and_the_server_calculates_total_marks(world):
    res = create(world)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["assignment_type"] == "QUIZ" and body["status"] == "DRAFT"
    assert body["question_count"] == 3 and body["total_marks"] == 6
    assert body["questions"][0]["options"][1]["is_correct"] is True  # the faculty view carries the answer key


def test_client_supplied_total_marks_and_status_are_rejected(world):
    assert create(world, total_marks=100).status_code == 422
    assert create(world, status="PUBLISHED").status_code == 422


def test_publish_creates_notifications_and_shows_the_quiz_to_students(world, seeded_engine: Engine):
    quiz = published_quiz(world)
    with Session(seeded_engine) as s:
        n = s.scalar(text("select count(*) from notifications where type = 'QUIZ_PUBLISHED'"))
        assert n > 0
    items = world.client.get(f"{API}/student/assignments", headers=auth(world.stu_5a)).json()
    item = next(i for i in items if i["id"] == quiz["id"])
    assert item["assignment_type"] == "QUIZ" and item["quiz_status"] == "NOT_STARTED"
    assert item["question_count"] == 3 and item["total_marks"] == 6 and item["timing"] == "PENDING"


def test_cannot_publish_a_quiz_without_questions(world):
    quiz = create(world, questions=[]).json()
    res = publish(world, quiz["id"])
    assert res.status_code == 422 and res.json()["error"]["code"] == "QUIZ_EMPTY"


def test_draft_quiz_can_be_replaced_but_a_published_one_is_frozen(world):
    quiz = create(world).json()
    body = quiz_body(world, title="Edited", questions=[question("TRUE_FALSE", 5, (0,))])
    for k in ("subject_id", "section_id", "publish"):
        body.pop(k, None)
    res = world.client.put(f"{API}/faculty/quizzes/{quiz['id']}", json=body, headers=auth(world.fac1))
    assert res.status_code == 200 and res.json()["total_marks"] == 5 and res.json()["title"] == "Edited"
    assert publish(world, quiz["id"]).status_code == 200
    res = world.client.put(f"{API}/faculty/quizzes/{quiz['id']}", json=body, headers=auth(world.fac1))
    assert res.status_code == 409 and res.json()["error"]["code"] == "NOT_DRAFT"


@pytest.mark.parametrize(
    "bad",
    [
        question("SINGLE_CHOICE", 1, (0, 1)),  # two correct answers
        question("SINGLE_CHOICE", 1, ()),  # none correct
        question("MULTIPLE_SELECT", 1, ()),  # none correct
        question("TRUE_FALSE", 1, (0,)) | {"options": [{"text": "Yes", "is_correct": True}, {"text": "No"}]},
        question("SINGLE_CHOICE", 0, (0,)),  # marks must be positive
        question("SINGLE_CHOICE", 1, (0,), n=1),  # fewer than two options
        question("SINGLE_CHOICE", 1, (0,)) | {"text": "   "},  # empty text
        question("SINGLE_CHOICE", 1, (0,)) | {"options": [{"text": "A", "is_correct": True}, {"text": "a"}]},  # duplicate
    ],
)
def test_invalid_questions_are_rejected_not_corrected(world, bad):
    assert create(world, questions=[bad]).status_code == 422


def test_limits_and_deadline_policy(world):
    assert create(world, questions=[question(marks=1)] * 51).status_code == 422
    assert create(world, title="").status_code == 422
    assert create(world, deadline=iso(NOW)).status_code == 422  # must be >= 1 minute ahead
    assert create(world, duration_minutes=0).status_code == 422


# --- authorisation ----------------------------------------------------------------------------------------------

def test_only_the_teaching_faculty_can_manage_a_quiz(world):
    assert create(world, token=world.fac2).status_code == 403  # does not teach 5A / that subject
    quiz = create(world).json()
    other = world.client.get(f"{API}/faculty/quizzes/{quiz['id']}", headers=auth(world.fac2))
    assert other.status_code == 404
    assert publish(world, quiz["id"], token=world.fac2).status_code == 404
    assert world.client.get(f"{API}/faculty/quizzes/{quiz['id']}", headers=auth(world.stu_5a)).status_code == 403
    assert world.client.post(f"{API}/faculty/quizzes", json=quiz_body(world), headers=auth(world.stu_5a)).status_code == 403


def test_students_outside_the_section_cannot_see_or_start_the_quiz(world):
    quiz = published_quiz(world)
    assert world.client.get(f"{API}/student/quizzes/{quiz['id']}", headers=auth(world.stu_5b)).status_code == 404
    assert start(world, quiz["id"], world.stu_5b).status_code == 404


def test_a_draft_quiz_is_not_visible_to_students(world):
    quiz = create(world).json()
    assert world.client.get(f"{API}/student/quizzes/{quiz['id']}", headers=auth(world.stu_5a)).status_code == 404


# --- taking the quiz -------------------------------------------------------------------------------------------

def test_questions_are_hidden_until_the_attempt_starts_and_never_carry_the_answer_key(world):
    quiz = published_quiz(world)
    before = world.client.get(f"{API}/student/quizzes/{quiz['id']}", headers=auth(world.stu_5a)).json()
    assert before["questions"] is None and before["can_attempt"] is True and before["total_marks"] == 6
    after = start(world, quiz["id"]).json()
    assert len(after["questions"]) == 3 and after["attempt"]["status"] == "IN_PROGRESS"
    assert "is_correct" not in str(after) and "correct" not in str(after).replace("can_attempt", "")


def test_starting_twice_returns_the_same_single_attempt(world):
    quiz = published_quiz(world)
    a = start(world, quiz["id"]).json()["attempt"]["id"]
    assert start(world, quiz["id"]).json()["attempt"]["id"] == a


def test_perfect_attempt_scores_full_marks_and_the_server_ignores_client_scores(world):
    quiz = published_quiz(world)
    attempt = start(world, quiz["id"]).json()["attempt"]["id"]
    res = submit(world, attempt, answers_for(quiz, {0: [1], 1: [0, 2], 2: [1]}))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["score"] == 6 and body["max_score"] == 6 and body["timed_out"] is False
    assert body["answers_released"] is False and all(q["correct_option_ids"] is None for q in body["questions"])


def test_scoring_single_multiple_all_or_nothing_and_unanswered(world):
    quiz = published_quiz(world)
    attempt = start(world, quiz["id"]).json()["attempt"]["id"]
    # Q1 right (2), Q2 only part of the correct set (0 under all-or-nothing), Q3 left unanswered (0)
    res = submit(world, attempt, answers_for(quiz, {0: [1], 1: [0]}))
    assert res.json()["score"] == 2
    assert [q["awarded"] for q in res.json()["questions"]] == [2, 0, 0]


def test_multiple_select_with_an_extra_wrong_option_scores_zero(world):
    quiz = published_quiz(world)
    attempt = start(world, quiz["id"]).json()["attempt"]["id"]
    res = submit(world, attempt, answers_for(quiz, {1: [0, 1, 2]}))
    assert res.json()["score"] == 0


def test_submitting_twice_is_idempotent_and_answers_cannot_change_afterwards(world):
    quiz = published_quiz(world)
    attempt = start(world, quiz["id"]).json()["attempt"]["id"]
    first = submit(world, attempt, answers_for(quiz, {0: [1]})).json()
    again = submit(world, attempt, answers_for(quiz, {0: [0], 1: [0, 2], 2: [1]})).json()  # a retry with other answers
    assert again["score"] == first["score"] == 2 and again["submitted_at"] == first["submitted_at"]
    res = world.client.put(
        f"{API}/student/quiz-attempts/{attempt}/answers",
        json={"answers": answers_for(quiz, {0: [0]})},
        headers=auth(world.stu_5a),
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "ALREADY_SUBMITTED"
    # a new attempt cannot be started either
    assert start(world, quiz["id"]).json()["attempt"]["id"] == attempt


def test_saved_answers_come_back_after_a_refresh(world):
    quiz = published_quiz(world)
    attempt = start(world, quiz["id"]).json()["attempt"]["id"]
    saved = answers_for(quiz, {0: [2], 1: [1, 3]})
    res = world.client.put(f"{API}/student/quiz-attempts/{attempt}/answers", json={"answers": saved}, headers=auth(world.stu_5a))
    assert res.status_code == 200
    view = world.client.get(f"{API}/student/quizzes/{quiz['id']}", headers=auth(world.stu_5a)).json()
    mine = view["attempt"]["answers"]
    assert mine[saved[0]["question_id"]] == saved[0]["option_ids"]
    assert sorted(mine[saved[1]["question_id"]]) == sorted(saved[1]["option_ids"])


def test_answers_must_belong_to_this_quiz_and_question(world):
    quiz = published_quiz(world)
    other = published_quiz(world, title="Other quiz")
    attempt = start(world, quiz["id"]).json()["attempt"]["id"]

    def put(answers):
        return world.client.put(
            f"{API}/student/quiz-attempts/{attempt}/answers", json={"answers": answers}, headers=auth(world.stu_5a)
        )

    foreign_q = answers_for(other, {0: [0]})
    assert put(foreign_q).status_code == 422
    wrong_option = [{"question_id": quiz["questions"][0]["id"], "option_ids": [quiz["questions"][1]["options"][0]["id"]]}]
    assert put(wrong_option).status_code == 422
    two_for_single = answers_for(quiz, {0: [0, 1]})
    assert put(two_for_single).status_code == 422
    assert put(answers_for(quiz, {0: [0]}) * 2).status_code == 422  # same question twice


def test_students_see_only_their_own_attempt(world):
    quiz = published_quiz(world)
    attempt = start(world, quiz["id"]).json()["attempt"]["id"]
    for call in (
        lambda: world.client.put(f"{API}/student/quiz-attempts/{attempt}/answers", json={"answers": []}, headers=auth(world.stu_5a2)),
        lambda: submit(world, attempt, token=world.stu_5a2),
        lambda: world.client.get(f"{API}/student/quiz-attempts/{attempt}/result", headers=auth(world.stu_5a2)),
    ):
        assert call().status_code == 404
    # nor can faculty use the student endpoints
    assert world.client.get(f"{API}/student/quiz-attempts/{attempt}/result", headers=auth(world.fac1)).status_code == 403


def test_result_is_not_available_before_submission(world):
    quiz = published_quiz(world)
    attempt = start(world, quiz["id"]).json()["attempt"]["id"]
    res = world.client.get(f"{API}/student/quiz-attempts/{attempt}/result", headers=auth(world.stu_5a))
    assert res.status_code == 409 and res.json()["error"]["code"] == "NOT_SUBMITTED"


# --- time rules ------------------------------------------------------------------------------------------------

def test_no_attempt_can_start_after_the_deadline(world, freeze_time):
    quiz = published_quiz(world)
    later(world, freeze_time, NOW + timedelta(days=3))
    res = start(world, quiz["id"])
    assert res.status_code == 409 and res.json()["error"]["code"] == "DEADLINE_PASSED"
    view = world.client.get(f"{API}/student/quizzes/{quiz['id']}", headers=auth(world.stu_5a)).json()
    assert view["can_attempt"] is False and view["blocked_reason"] == "DEADLINE_PASSED"
    items = world.client.get(f"{API}/student/assignments", headers=auth(world.stu_5a)).json()
    assert next(i for i in items if i["id"] == quiz["id"])["timing"] == "MISSING"


def test_duration_is_enforced_by_the_server_and_late_submit_uses_saved_answers(world, freeze_time):
    quiz = published_quiz(world, duration_minutes=10)
    attempt = start(world, quiz["id"]).json()["attempt"]
    assert attempt["expires_at"].startswith((NOW + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M"))
    saved = world.client.put(
        f"{API}/student/quiz-attempts/{attempt['id']}/answers",
        json={"answers": answers_for(quiz, {0: [1]})},
        headers=auth(world.stu_5a),
    )
    assert saved.status_code == 200
    later(world, freeze_time, NOW + timedelta(minutes=11))
    late_save = world.client.put(
        f"{API}/student/quiz-attempts/{attempt['id']}/answers",
        json={"answers": answers_for(quiz, {1: [0, 2]})},
        headers=auth(world.stu_5a),
    )
    assert late_save.status_code == 409 and late_save.json()["error"]["code"] == "QUIZ_TIME_UP"
    res = submit(world, attempt["id"], answers_for(quiz, {1: [0, 2], 2: [1]}))  # the late answers are ignored
    body = res.json()
    assert body["timed_out"] is True and body["score"] == 2
    assert body["submitted_at"].startswith((NOW + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M"))


def test_answer_key_is_released_only_after_the_deadline(world, freeze_time):
    quiz = published_quiz(world)
    attempt = start(world, quiz["id"]).json()["attempt"]["id"]
    submit(world, attempt, answers_for(quiz, {0: [1]}))
    later(world, freeze_time, NOW + timedelta(days=3))
    res = world.client.get(f"{API}/student/quiz-attempts/{attempt}/result", headers=auth(world.stu_5a)).json()
    assert res["answers_released"] is True
    assert res["questions"][0]["correct_option_ids"] == [quiz["questions"][0]["options"][1]["id"]]


# --- integration with the rest of the application ------------------------------------------------------------------

def test_faculty_sees_real_participation(world):
    quiz = published_quiz(world)
    attempt = start(world, quiz["id"]).json()["attempt"]["id"]
    submit(world, attempt, answers_for(quiz, {0: [1], 1: [0, 2], 2: [1]}))
    start(world, quiz["id"], world.stu_5a2)
    data = world.client.get(f"{API}/faculty/quizzes/{quiz['id']}/participation", headers=auth(world.fac1)).json()
    assert data["total_marks"] == 6 and data["submitted"] == 1 and data["started"] == 2
    assert data["average_score"] == 6.0
    assert {p["status"] for p in data["participants"]} == {"NOT_STARTED", "IN_PROGRESS", "SUBMITTED"}
    assert world.client.get(f"{API}/faculty/quizzes/{quiz['id']}/participation", headers=auth(world.fac2)).status_code == 404


def test_file_uploads_and_late_requests_are_refused_for_a_quiz(world, freeze_time):
    quiz = published_quiz(world)
    res = world.client.post(
        f"{API}/student/assignments/{quiz['id']}/submissions",
        files={"file": ("a.pdf", b"%PDF-1.4 x", "application/pdf")},
        headers=auth(world.stu_5a),
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "IS_A_QUIZ"
    later(world, freeze_time, NOW + timedelta(days=3))
    res = world.client.post(
        f"{API}/student/assignments/{quiz['id']}/late-request",
        json={"reason": "I was unwell and could not attempt the quiz."},
        headers=auth(world.stu_5a),
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "IS_A_QUIZ"


def test_faculty_assignment_list_shows_the_type_and_file_assignments_are_unchanged(world):
    quiz = create(world).json()
    file_body = world.payload()
    f = world.client.post(f"{API}/faculty/assignments", json=file_body, headers=auth(world.fac1))
    assert f.status_code == 201 and f.json()["assignment_type"] == "FILE"
    rows = world.client.get(f"{API}/faculty/assignments", headers=auth(world.fac1)).json()
    types = {r["id"]: r["assignment_type"] for r in rows}
    assert types[quiz["id"]] == "QUIZ" and types[f.json()["id"]] == "FILE"


def test_draft_quiz_can_be_deleted_but_a_quiz_with_attempts_is_archived_not_deleted(world):
    draft = create(world).json()
    res = world.client.delete(f"{API}/faculty/assignments/{draft['id']}", headers=auth(world.fac1))
    assert res.status_code == 200 and res.json()["deleted"] is True
    quiz = published_quiz(world)
    start(world, quiz["id"])
    check = world.client.get(f"{API}/faculty/assignments/{quiz['id']}/deletion-check", headers=auth(world.fac1)).json()
    assert check["can_delete"] is False and check["action"] == "ARCHIVE"
    assert world.client.delete(f"{API}/faculty/assignments/{quiz['id']}", headers=auth(world.fac1)).status_code == 409


def test_database_refuses_an_answer_that_mixes_two_quizzes(world, seeded_engine: Engine):
    """Composite foreign keys: the option must belong to the question, the question to the attempt's quiz."""
    from sqlalchemy.exc import IntegrityError

    a = published_quiz(world)
    b = published_quiz(world, title="Second")
    attempt = start(world, a["id"]).json()["attempt"]["id"]
    with Session(seeded_engine) as s:
        with pytest.raises(IntegrityError):
            s.execute(
                text(
                    "insert into quiz_answers (attempt_id, assignment_id, question_id, option_id) "
                    "values (:att, :aid, :q, :o)"
                ),
                {
                    "att": attempt,
                    "aid": a["id"],
                    "q": b["questions"][0]["id"],  # a question of ANOTHER quiz
                    "o": b["questions"][0]["options"][0]["id"],
                },
            )


def test_cors_preflight_allows_the_put_used_to_save_quiz_answers(world, settings):
    """The browser saves answers with PUT: it needs PUT in the CORS allow-list (found in the browser run)."""
    res = world.client.options(
        f"{API}/student/quiz-attempts/{'0' * 8}-0000-0000-0000-{'0' * 12}/answers",
        headers={
            "Origin": settings.frontend_origin,
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert res.status_code == 200 and "PUT" in res.headers["access-control-allow-methods"]
