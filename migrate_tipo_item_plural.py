"""Migracao 026: corrige tipo_item de singular pra plural (bug da 025).

Uso:
    python3 migrate_tipo_item_plural.py            # dry-run
    python3 migrate_tipo_item_plural.py --apply    # aplica de verdade
"""
import argparse
import os
import sys

import psycopg2
import psycopg2.extras


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Defina DATABASE_URL no ambiente.", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(database_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    with open("migrations/026_tipo_item_plural.sql", "r", encoding="utf-8") as f:
        sql = f.read()
    cur.execute(sql)
    print("DDL de migrations/026_tipo_item_plural.sql aplicado.")

    cur.execute("SELECT tipo_item, COUNT(*) AS total FROM equipment_items GROUP BY tipo_item")
    print("Distribuicao por tipo apos correcao:", cur.fetchall())

    if args.apply:
        conn.commit()
        print("APLICADO (commit).")
    else:
        conn.rollback()
        print("DRY-RUN (rollback) -- rode com --apply pra aplicar de verdade.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
