"""Applies a client's settings file (deploy/tenants/<client>/settings.json) section by section.

python -m app.ops.apply_settings ../deploy/tenants/<client>/settings.json
"""

import json
import sys

from app.core.db import new_session
from app.modules.org import service as org


def main(path: str) -> int:
    wanted = json.loads(open(path, encoding="utf-8").read())
    with new_session() as db:
        for section, value in wanted.items():
            current = org.all_sections(db)[section][0]
            version, _ = org.update_section(db, section, value, expected_version=current, actor_user_id=None)
            print(f"{section}: version {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
