"""
Migration 005 — checklist de entrega/devolução + manutenção.

Uso:
    python migrate_checklists_manutencoes.py            # dry-run (mostra o resumo e desfaz tudo no final)
    python migrate_checklists_manutencoes.py --apply     # aplica de verdade (commit)

Pré-requisito: migrations/002_multiempresa.sql (Fase 1) já aplicada — este
script depende da company padrão que ela criou.

Mesma lógica de segurança dos scripts anteriores: tudo numa única transação,
erro em qualquer passo causa ROLLBACK completo, sem --apply sempre termina
em ROLLBACK mesmo se der tudo certo.
"""

import argparse
import os
import sys

from psycopg2 import sql

from database import get_db_connection

COMPANY_PADRAO_NOME = "Minha Locadora Original"

SQL_FILE = os.path.join(os.path.dirname(__file__), "migrations", "005_checklists_manutencoes.sql")


def log(msg):
    print(f"[migrate_checklists_manutencoes] {msg}")


def aplicar_ddl(cur):
    log(f"Aplicando estrutura de {SQL_FILE} ...")
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        cur.execute(f.read())
    log("Estrutura aplicada (checklists, checklist_fotos, manutencoes, índices, trigger).")


def buscar_company_padrao(cur):
    cur.execute("SELECT id FROM companies WHERE nome = %s", (COMPANY_PADRAO_NOME,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(
            f"Company padrão '{COMPANY_PADRAO_NOME}' não encontrada — rode migrate_multiempresa.py "
            f"--apply (Fase 1) antes deste script."
        )
    log(f"Company padrão encontrada (id={row['id']}).")
    return row["id"]


def definir_defaults_company(cur, company_id):
    for tabela in ("checklists", "manutencoes"):
        cur.execute(
            sql.SQL("ALTER TABLE {} ALTER COLUMN company_id SET DEFAULT %s").format(sql.Identifier(tabela)),
            (company_id,),
        )
    log("checklists.company_id e manutencoes.company_id agora têm DEFAULT — INSERTs que não "
        "mencionam essa coluna continuam funcionando.")


def imprimir_resumo(cur):
    cur.execute("SELECT COUNT(*) AS total FROM checklists")
    total_checklists = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM manutencoes")
    total_manutencoes = cur.fetchone()["total"]
    log("----- RESUMO -----")
    log(f"checklists: {total_checklists} linha(s)")
    log(f"manutencoes: {total_manutencoes} linha(s)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Grava de verdade (COMMIT). Sem essa flag, roda tudo e desfaz (ROLLBACK) no final.",
    )
    args = parser.parse_args()

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        try:
            aplicar_ddl(cur)
            company_id = buscar_company_padrao(cur)
            definir_defaults_company(cur, company_id)
            imprimir_resumo(cur)
        except Exception:
            conn.rollback()
            log("ERRO durante a migração — ROLLBACK completo, nada foi gravado.")
            raise
        finally:
            cur.close()

        if args.apply:
            conn.commit()
            log("--apply informado: COMMIT feito. Migração aplicada de verdade.")
        else:
            conn.rollback()
            log("Modo dry-run (padrão): ROLLBACK feito. Nada foi gravado. Rode com --apply para aplicar de verdade.")
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"Falhou: {e}")
        sys.exit(1)
