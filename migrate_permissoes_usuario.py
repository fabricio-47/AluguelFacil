"""Migracao 028: permissoes customizadas por USUARIO individual (alem de por cargo).

Uso:
    python3 migrate_permissoes_usuario.py            # dry-run
    python3 migrate_permissoes_usuario.py --apply    # aplica de verdade
"""
import argparse
import os

import psycopg2
import psycopg2.extras


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL não definido no ambiente.")

    conn = psycopg2.connect(database_url, sslmode="require", cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()
    try:
        with open("migrations/028_permissoes_usuario.sql", encoding="utf-8") as f:
            cur.execute(f.read())

        cur.execute("SELECT COUNT(*) AS n FROM permissoes_customizadas_usuario")
        print("permissoes_customizadas_usuario, total de linhas:", cur.fetchone()["n"])

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
