"""
Migration 021 -- remove as tabelas mortas veiculos/imoveis/rentable_items
(arquitetura abandonada, sem nenhuma rota usando-as -- o modulo real de
veiculos/imoveis usa equipment_items, migrations 019 e 020).

Checagem de seguranca: se qualquer uma das 3 tabelas tiver linhas, o script
aborta sem apagar nada (pode ser dado que alguem inseriu manualmente e
merece investigacao antes de descartar).

Uso:
    python migrate_remove_dead_tables.py            # dry-run
    python migrate_remove_dead_tables.py --apply     # aplica de verdade (commit)
"""

import argparse
import os
import sys

from database import get_db_connection

SQL_FILE = os.path.join(os.path.dirname(__file__), "migrations", "021_remove_dead_tables.sql")
TABELAS = ("veiculos", "imoveis", "rentable_items")


def log(msg):
    print(f"[migrate_remove_dead_tables] {msg}")


def checar_vazio(cur):
    for tabela in TABELAS:
        cur.execute(f"SELECT to_regclass('public.{tabela}') AS existe")
        if not cur.fetchone()["existe"]:
            log(f"Tabela {tabela} ja nao existe, ok.")
            continue
        cur.execute(f"SELECT COUNT(*) AS total FROM {tabela}")
        total = cur.fetchone()["total"]
        if total > 0:
            raise RuntimeError(
                f"Tabela {tabela} tem {total} linha(s) -- abortando, isso nao deveria "
                f"ter dado (nenhum codigo escreve nela). Investigue antes de forcar a remocao."
            )
        log(f"Tabela {tabela}: 0 linhas, seguro remover.")


def aplicar_ddl(cur):
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        cur.execute(f.read())
    log("DROP TABLE aplicado em veiculos, imoveis, rentable_items.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Grava de verdade (COMMIT).")
    args = parser.parse_args()

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        try:
            checar_vazio(cur)
            aplicar_ddl(cur)
        except Exception:
            conn.rollback()
            log("ERRO ou abortado -- ROLLBACK completo, nada foi apagado.")
            raise
        finally:
            cur.close()

        if args.apply:
            conn.commit()
            log("--apply informado: COMMIT feito. Tabelas removidas de verdade.")
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
