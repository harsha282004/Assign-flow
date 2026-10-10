"""Report storage objects not referenced by the database (dry run). Add --delete to remove them.

Run inside the backend container:
    docker compose exec backend python scripts/find_orphans.py
    docker compose exec backend python scripts/find_orphans.py --delete
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.services import orphans  # noqa: E402
from app.services.storage import make_s3_client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delete", action="store_true", help="delete the orphaned objects (default: report only)")
    args = parser.parse_args()

    settings = get_settings()
    client = make_s3_client(settings)
    with get_sessionmaker()() as db:
        orphaned = orphans.find_orphans(client, settings.s3_bucket, db)
        dangling = orphans.find_dangling(client, settings.s3_bucket, db)

    print(f"orphaned objects (stored, not referenced): {len(orphaned)}")
    for key in orphaned:
        print(f"  {key}")
    print(f"dangling references (referenced, not stored): {len(dangling)}")
    for key in dangling:
        print(f"  {key}")
    if args.delete:
        for key in orphaned:
            client.delete_object(Bucket=settings.s3_bucket, Key=key)
        print(f"deleted {len(orphaned)} orphaned object(s)")
    elif orphaned:
        print("dry run: nothing deleted (use --delete to remove the orphans)")
    return 1 if dangling else 0


if __name__ == "__main__":
    sys.exit(main())
