"""Bell badge support: lightweight unread count and mark-all-as-read, always scoped to the caller."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from tests.api.test_assignments import API, World, auth


@pytest.fixture
def world(client, test_password, freeze_time) -> World:
    return World(client, test_password, freeze_time)


def user_id(w: World, token: str) -> str:
    return w.client.get(f"{API}/auth/me", headers=auth(token)).json()["id"]


def add(engine: Engine, uid: str, n: int, tag: str = "t") -> None:
    with Session(engine) as s:
        for _ in range(n):
            s.execute(
                text(
                    "insert into notifications (user_id, type, title, body, dedup_key) "
                    "values (:u, 'TEST', 'Hello', 'Body', :k)"
                ),
                {"u": uid, "k": f"{tag}:{uid}:{uuid.uuid4()}"},
            )
        s.commit()


def count(w: World, token: str) -> int:
    res = w.client.get(f"{API}/notifications/unread-count", headers=auth(token))
    assert res.status_code == 200
    return res.json()["unread_count"]


def test_count_is_zero_without_notifications_and_requires_login(world):
    assert count(world, world.stu_5a) == 0
    assert world.client.get(f"{API}/notifications/unread-count").status_code == 401


def test_count_reflects_new_notifications_and_only_the_callers_own(world, seeded_engine):
    me, other = user_id(world, world.stu_5a), user_id(world, world.stu_5a2)
    add(seeded_engine, me, 1)
    assert count(world, world.stu_5a) == 1
    add(seeded_engine, me, 4)
    add(seeded_engine, other, 2)
    assert count(world, world.stu_5a) == 5 and count(world, world.stu_5a2) == 2
    assert count(world, world.fac1) == 0  # a teacher never sees a student's count


def test_count_above_99_is_reported_exactly(world, seeded_engine):
    add(seeded_engine, user_id(world, world.stu_5a), 120)
    assert count(world, world.stu_5a) == 120  # the "99+" label is a display rule of the badge


def test_reading_one_decrements_and_the_count_matches_the_list(world, seeded_engine):
    add(seeded_engine, user_id(world, world.stu_5a), 3)
    listing = world.client.get(f"{API}/notifications", headers=auth(world.stu_5a)).json()
    assert listing["unread_count"] == count(world, world.stu_5a) == 3
    world.client.post(f"{API}/notifications/{listing['items'][0]['id']}/read", headers=auth(world.stu_5a))
    assert count(world, world.stu_5a) == 2


def test_cannot_read_someone_elses_notification(world, seeded_engine):
    add(seeded_engine, user_id(world, world.stu_5a2), 1)
    foreign = world.client.get(f"{API}/notifications", headers=auth(world.stu_5a2)).json()["items"][0]["id"]
    res = world.client.post(f"{API}/notifications/{foreign}/read", headers=auth(world.stu_5a))
    assert res.status_code == 404
    assert count(world, world.stu_5a2) == 1


def test_mark_all_clears_only_my_badge(world, seeded_engine):
    add(seeded_engine, user_id(world, world.stu_5a), 3)
    add(seeded_engine, user_id(world, world.stu_5a2), 2)
    res = world.client.post(f"{API}/notifications/read-all", headers=auth(world.stu_5a))
    assert res.status_code == 204
    assert count(world, world.stu_5a) == 0 and count(world, world.stu_5a2) == 2
    # items are kept, only marked read
    items = world.client.get(f"{API}/notifications", headers=auth(world.stu_5a)).json()["items"]
    assert len(items) == 3 and all(i["read_at"] for i in items)
    assert world.client.post(f"{API}/notifications/read-all").status_code == 401


def test_a_new_notification_after_mark_all_raises_the_count_again(world, seeded_engine):
    me = user_id(world, world.stu_5a)
    add(seeded_engine, me, 2)
    world.client.post(f"{API}/notifications/read-all", headers=auth(world.stu_5a))
    add(seeded_engine, me, 1, "later")
    assert count(world, world.stu_5a) == 1
