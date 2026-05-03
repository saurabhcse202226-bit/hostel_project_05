import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project.database import get_database_url


def _mask_database_url(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    user = parts.username or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    netloc = host
    if user:
        netloc = f"{user}:***@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def main() -> None:
    db_url = get_database_url()
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    print(f"DATABASE_URL={_mask_database_url(db_url)}")
    cur.execute("SELECT 1")
    print("CONNECTION=OK")

    cur.execute(
        """
        SELECT tablename
        FROM pg_catalog.pg_tables
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY tablename
        """
    )
    tables = [row[0] for row in cur.fetchall()]
    print("TABLES=" + ", ".join(tables))

    for table in tables:
        cur.execute(f'SELECT COUNT(*) FROM "{table}"')
        count = cur.fetchone()[0]
        print(f"{table}: {count}")

    # Show small preview data from key tables
    previews = {
        "students": "SELECT id, name, reg_no, room_no, fee_status FROM students ORDER BY id DESC LIMIT 5",
        "staff_users": "SELECT id, username, role FROM staff_users ORDER BY id DESC LIMIT 5",
        "leaves": "SELECT id, reg_no, from_date, to_date, warden_status, principal_status FROM leaves ORDER BY id DESC LIMIT 5",
        "complaints": "SELECT id, reg_no, status, assigned_to FROM complaints ORDER BY id DESC LIMIT 5",
    }

    for table, query in previews.items():
        print(f"\nPREVIEW {table}:")
        try:
            cur.execute(query)
            rows = cur.fetchall()
            if not rows:
                print("  (no rows)")
                continue
            for row in rows:
                print(" ", row)
        except psycopg2.Error as exc:
            print(f"  (skip: {exc})")

    conn.close()


if __name__ == "__main__":
    main()
