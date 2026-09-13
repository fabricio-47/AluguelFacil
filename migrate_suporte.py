"""Migracao 027: sistema de suporte (tickets/mensagens) entre clientes do portal e a equipe.

Uso:
    python3 migrate_suporte.py            # dry-run
    python3 migrate_suporte.py --apply    # aplica de verdade
"""
import argparse
import os

import psycopg2
import psycopg2.extras


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Aplica de verdade (default é dry-run com rollback)")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL não definido no ambiente.")

    conn = psycopg2.connect(database_url, sslmode="require", cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()
    try:
        with open("migrations/027_suporte.sql", encoding="utf-8") as f:
            sql = f.read()
        cur.execute(sql)

        cur.execute("SELECT COUNT(*) AS n FROM suporte_tickets")
        print("suporte_tickets, total de linhas:", cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM suporte_mensagens")
        print("suporte_mensagens, total de linhas:", cur.fetchone()["n"])

        if args.apply:
            conn.commit()
            print("APLICADO com sucesso.")
        else:
            conn.rollback()
            print("DRY-RUN — nada foi salvo. Rode com --apply para aplicar de verdade.")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
