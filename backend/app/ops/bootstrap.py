"""First administrator of a new installation.

ADMIN_PASSWORD=... python -m app.ops.bootstrap --username admin --full-name "System Administrator"
"""

import argparse
import os
import sys

from app.core.db import new_session
from app.core.errors import AppError
from app.modules.identity import service as identity


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--full-name", required=True)
    args = parser.parse_args()
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        print("set ADMIN_PASSWORD in the environment", file=sys.stderr)
        return 2
    with new_session() as db:
        try:
            public_id = identity.bootstrap_superuser(
                db, username=args.username, full_name=args.full_name, password=password
            )
        except AppError as exc:
            print(f"refused: {exc.code} {exc.detail or ''}", file=sys.stderr)
            return 1
    print(f"superuser created: {public_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
