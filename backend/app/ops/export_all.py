"""Everything the client owns, in files any program opens (the contract's full export at termination): one CSV per
table (UTF-8 with a BOM, so Excel reads the Arabic), a manifest of what is inside and what was left out and why, and
optionally every stored file (photos, documents, receipts) under its sha256.

Left out: what opens accounts rather than describes the business (password and code hashes, session and device
tokens, the two-step secret, the integrations' encrypted keys), and the rate limiter's counters. A full restore of the
system is a database backup (pg_dump), not this export.

python -m app.ops.export_all --out /backups/export-2026-10.zip [--with-files]
"""

import argparse
import csv
import io
import json
import mimetypes
import re
import sys
import zipfile
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import MIGRATED_SCHEMAS, new_session

# whole tables that hold only access secrets or counters
SKIP_TABLES = {
    "identity.sessions": "sign-in sessions (tokens)",
    "identity.device_tokens": "driver app tokens",
    "identity.otp_challenges": "one-time sign-in codes",
    "identity.password_reset_codes": "one-time password codes",
    "identity.rate_hits": "request limit counters",
}
# columns that would let someone into an account or a service
SECRET = re.compile(r"(^|_)(password_hash|token_hash|code_hash|otp_hash|session_hash|csrf_token|secrets)$|_enc$")

TABLES = text("""
SELECT n.nspname, c.relname
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p') AND NOT c.relispartition AND n.nspname = ANY(:schemas)
ORDER BY n.nspname, c.relname
""")
COLUMNS = text("""
SELECT column_name FROM information_schema.columns
WHERE table_schema = :schema AND table_name = :table
ORDER BY ordinal_position
""")


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def export(db: Session, out, *, with_files: bool = False) -> dict:
    """Writes the export to `out` (a path or a binary file) and returns its manifest."""
    manifest = {"exported_at": datetime.now(UTC).isoformat(), "tables": {}, "left_out": {}, "files": 0}
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for schema, table in db.execute(TABLES, {"schemas": sorted(MIGRATED_SCHEMAS)}).all():
            name = f"{schema}.{table}"
            if name in SKIP_TABLES:
                manifest["left_out"][name] = SKIP_TABLES[name]
                continue
            columns = [c for (c,) in db.execute(COLUMNS, {"schema": schema, "table": table})]
            kept = [c for c in columns if not SECRET.search(c)]
            for c in set(columns) - set(kept):
                manifest["left_out"][f"{name}.{c}"] = "an access secret"
            q = db.get_bind().dialect.identifier_preparer.quote  # names from the catalog, quoted all the same
            sql = f"SELECT {', '.join(q(c) for c in kept)} FROM {q(schema)}.{q(table)}"  # noqa: S608
            rows = db.execute(text(sql)).yield_per(5000)
            count = 0
            with z.open(f"data/{name}.csv", "w") as raw:
                writer_io = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                writer = csv.writer(writer_io)
                writer.writerow(kept)
                for row in rows:
                    writer.writerow([_cell(v) for v in row])
                    count += 1
                writer_io.flush()
                writer_io.detach()
            manifest["tables"][name] = count
        if with_files:
            from app.modules.files import service as files

            for sha, content_type in db.execute(text("SELECT sha256, content_type FROM files.files ORDER BY sha256")):
                ext = mimetypes.guess_extension(content_type or "") or ""
                z.writestr(f"files/{sha}{ext}", files.read(db, files.get(db, sha)))
                manifest["files"] += 1
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", required=True, help="the .zip to write")
    parser.add_argument("--with-files", action="store_true", help="also every stored file (photos, documents)")
    args = parser.parse_args()
    with new_session() as db:
        manifest = export(db, args.out, with_files=args.with_files)
    total = sum(manifest["tables"].values())
    print(f"{args.out}: {len(manifest['tables'])} tables, {total} rows, {manifest['files']} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
