import argparse
import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Aplica de verdade (default é dry-run com rollback)")
    args = parser.parse_args()

    conn = psycopg2.connect(Config.DATABASE_URL, sslmode=Config.DB_SSLMODE, cursor_factory=RealDictCursor)
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
