"""Deterministic demo-dataset definition (architecture §13.4). Edit here to change the dataset."""

from dataclasses import dataclass

from app.db.seeds.seed_names import full_name

PROGRAMME_PREFIX = "CSE"  # section label = f"{PROGRAMME_PREFIX}-{semester}{name}", e.g. CSE-5A
SEMESTERS = (5,)
SECTION_NAMES = ("A", "B", "C")  # CSE-5A, CSE-5B, CSE-5C
SECTION_SIZES = {"A": 17, "B": 17, "C": 16}  # 17 + 17 + 16 = exactly 50 students
FACULTY_COUNT = 15  # exactly 15 faculty

FACULTY_ID_FORMAT = "FAC{:03d}"  # FAC001..FAC015
STUDENT_ID_FORMAT = "STU{:04d}"
# STU0101..STU0150. The original dataset numbered semester 5 from STU0101, so STU0101 and STU0102 (CSE-5A) keep
# their accounts, and the numbering stays contiguous: 5A = 0101-0117, 5B = 0118-0134, 5C = 0135-0150.
STUDENT_ID_START = 101

# Fictional subject catalogue: semester -> [(code, name)] (six per semester).
SUBJECTS: dict[int, list[tuple[str, str]]] = {
    5: [
        ("CS501", "Operating Systems"),
        ("CS502", "Computer Networks"),
        ("CS503", "Database Systems"),
        ("CS504", "Software Engineering"),
        ("CS505", "Theory of Computation"),
        ("CS506", "Web Technologies"),
    ],
}


@dataclass(frozen=True)
class Slot:
    subject_code: str
    semester: int
    section_name: str

    @property
    def section_label(self) -> str:
        return section_label(self.semester, self.section_name)


def section_label(semester: int, name: str) -> str:
    return f"{PROGRAMME_PREFIX}-{semester}{name}"


# The demo script (architecture §29) has FAC001 create "[DEMO] Lab 4" for CSE-5A. Pinned explicitly so
# it never depends on insertion order: FAC001 teaches CS503 Database Systems in CSE-5A.
PINNED_SLOTS: dict[str, Slot] = {
    "FAC001": Slot(subject_code="CS503", semester=5, section_name="A"),
}


def sections() -> list[tuple[int, str]]:
    return [(sem, name) for sem in SEMESTERS for name in SECTION_NAMES]


def all_slots() -> list[Slot]:
    return [Slot(code, sem, name) for sem, name in sections() for code, _ in SUBJECTS[sem]]


def display_name(login_id: str) -> str:
    """Curated fictional Indian name of an account: faculty first (indexes 0-14), then students (15-164)."""
    number = int(login_id[3:])
    index = number - 1 if login_id.startswith("FAC") else FACULTY_COUNT + number - STUDENT_ID_START
    return full_name(index)


def faculty_ids() -> list[str]:
    return [FACULTY_ID_FORMAT.format(i) for i in range(1, FACULTY_COUNT + 1)]


def student_ids() -> list[str]:
    total = sum(SECTION_SIZES[name] for _, name in sections())
    return [STUDENT_ID_FORMAT.format(i) for i in range(STUDENT_ID_START, STUDENT_ID_START + total)]


def faculty_slot_map() -> dict[str, list[Slot]]:
    """faculty login_id -> teaching slots (one faculty per subject+section, a faculty may teach several).

    Pinned slots first; the remaining slots, in (semester, section, code) order, are dealt round-robin to the
    other faculty, so each of the 15 faculty teaches 1-2 classes of different subjects/sections. With the
    default dataset: 18 slots -> FAC001, FAC005, FAC006 and FAC007..FAC012 teach 1 or 2 (see the mapping doc).
    """
    pinned = set(PINNED_SLOTS.values())
    remaining = [s for s in all_slots() if s not in pinned]
    mapping: dict[str, list[Slot]] = {fid: [] for fid in faculty_ids()}
    for fid, slot in PINNED_SLOTS.items():
        mapping[fid].append(slot)
    free = [f for f in faculty_ids() if f not in PINNED_SLOTS]
    for i, slot in enumerate(remaining):
        mapping[free[i % len(free)]].append(slot)
    return mapping


def student_section_map() -> dict[str, tuple[int, str]]:
    """student login_id -> (semester, section name); SECTION_SIZES[name] students per section, in order."""
    ids = iter(student_ids())
    mapping: dict[str, tuple[int, str]] = {}
    for sem, name in sections():
        for _ in range(SECTION_SIZES[name]):
            mapping[next(ids)] = (sem, name)
    return mapping
