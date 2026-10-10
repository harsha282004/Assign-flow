"""Curated, deterministic, fictional Indian names for the demo dataset.

Every full name is built from one first name and one surname of these lists. The combination rule below never
repeats a (first name, surname) pair for fewer than 180 accounts, so all 65 demo names are distinct. The names
are fictional: they do not represent any real staff member or student of any institution.
"""

FIRST_NAMES: tuple[str, ...] = (
    # 30 masculine
    "Aarav", "Vivaan", "Aditya", "Arjun", "Rohan", "Karthik", "Siddharth", "Rahul", "Vikram", "Sanjay",
    "Manish", "Nikhil", "Pranav", "Harsh", "Kunal", "Varun", "Ankit", "Deepak", "Suresh", "Ramesh",
    "Anil", "Prakash", "Mahesh", "Ganesh", "Naveen", "Kiran", "Srinivas", "Venkatesh", "Harish", "Raghav",
    # 30 feminine
    "Ananya", "Diya", "Isha", "Kavya", "Meera", "Neha", "Pooja", "Priya", "Riya", "Sneha",
    "Shreya", "Swati", "Tanvi", "Aditi", "Divya", "Lakshmi", "Nandini", "Radhika", "Sahana", "Sowmya",
    "Anjali", "Deepika", "Gayatri", "Jyoti", "Kritika", "Lavanya", "Madhuri", "Pallavi", "Rashmi", "Shruti",
)

SURNAMES: tuple[str, ...] = (
    "Sharma", "Verma", "Iyer", "Nair", "Reddy", "Rao", "Patel", "Shah", "Gupta", "Agarwal",
    "Joshi", "Kulkarni", "Deshpande", "Menon", "Pillai", "Naidu", "Gowda", "Hegde", "Shetty", "Bhat",
    "Kamath", "Prabhu", "Singh", "Chauhan", "Mishra", "Banerjee", "Chatterjee", "Das", "Mukherjee", "Bose",
)

MAX_DISTINCT_NAMES = 180  # 3 cycles of the 60 first names


def full_name(index: int) -> str:
    """Name number `index` (0-based). Consecutive indexes alternate between different first names and surnames."""
    if not 0 <= index < MAX_DISTINCT_NAMES:
        raise ValueError(f"name index {index} is outside the {MAX_DISTINCT_NAMES} distinct names available")
    first = FIRST_NAMES[(index * 7) % len(FIRST_NAMES)]
    last = SURNAMES[(index * 7 + (index // len(FIRST_NAMES)) * 11) % len(SURNAMES)]
    return f"{first} {last}"
