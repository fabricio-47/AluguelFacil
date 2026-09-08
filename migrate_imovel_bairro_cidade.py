"""
Migration 023 -- adiciona bairro e cidade em equipment_items (imovel).

Uso:
    python migrate_imovel_bairro_cidade.py            # dry-run
    python migrate_imovel_bairro_cidade.py --apply     # aplica de verdade
"""
import argparse
import os
import sys

from database import get_db_connection

SQL_FILE = os.path.join(os.path.dirname(__file__), "migrations", "023_imovel_bairro_cidade.sql")


def log(msg):
    print(f"[migrate_imovel_bairro_cidade] {msg}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        try:
            with open(SQL_FILE, "r", encoding="utf-8") as f:
                cur.execute(f.read())
            log("Colunas bairro e cidade adicionadas (se ainda nao existiam).")
        except Exception:
            conn.rollback()
            log("ERRO -- ROLLBACK completo.")
            raise
        finally:
            cur.close()

        if args.apply:
            conn.commit()
            log("--apply informado: COMMIT feito.")
        else:
            conn.rollback()
            log("Modo dry-run: ROLLBACK feito.")
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"Falhou: {e}")
        sys.exit(1)
