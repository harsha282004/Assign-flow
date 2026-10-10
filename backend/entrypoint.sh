#!/bin/sh
set -eu

# With arguments (e.g. `docker compose run --rm backend pytest`), run that command directly
# without initialising the demo database.
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

# wait -> advisory lock -> migrate -> seed -> bucket (architecture §10.3). Non-zero exit aborts startup.
python -m app.db.init_db

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
