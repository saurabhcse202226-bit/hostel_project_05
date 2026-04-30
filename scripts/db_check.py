import sys
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project.database import DB_PATH


def main() -> None:
    conn = psycopg2.connect(DB_PATH)
    cur = conn.cursor()

    print(f"DB_PATH={DB_PATH}")
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
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
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
            rows = conn.execute(query).fetchall()
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
