"""
Migration 019 -- adiciona campos de veiculo (placa, chassi, renavam,
quilometragem, combustivel, cambio) em equipment_items, para o modulo de
locacao de veiculos reaproveitar o motor generico ja existente.

Uso:
    python migrate_veiculo_fields.py            # dry-run (mostra e desfaz no final)
    python migrate_veiculo_fields.py --apply     # aplica de verdade (commit)
"""

import argparse
import os
import sys

from database import get_db_connection

SQL_FILE = os.path.join(os.path.dirname(__file__), "migrations", "019_veiculo_fields.sql")


def log(msg):
    print(f"[migrate_veiculo_fields] {msg}")


def aplicar_ddl(cur):
    log(f"Aplicando estrutura de {SQL_FILE} ...")
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        cur.execute(f.read())
    log("Colunas placa/chassi/renavam/quilometragem/combustivel/cambio adicionadas (se ainda nao existiam).")


def imprimir_resumo(cur):
    cur.execute("SELECT COUNT(*) AS total FROM equipment_items WHERE placa IS NOT NULL")
    log(f"equipment_items com placa preenchida: {cur.fetchone()['total']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Grava de verdade (COMMIT).")
    args = parser.parse_args()

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        try:
            aplicar_ddl(cur)
            imprimir_resumo(cur)
        except Exception:
            conn.rollback()
            log("ERRO -- ROLLBACK completo, nada foi gravado.")
            raise
        finally:
            cur.close()

        if args.apply:
            conn.commit()
            log("--apply informado: COMMIT feito.")
        else:
            conn.rollback()
            log("Modo dry-run: ROLLBACK feito. Rode com --apply para aplicar de verdade.")
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"Falhou: {e}")
        sys.exit(1)
