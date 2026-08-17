"""
Migration 008 — CRM (orçamentos, pipeline de vendas, tarefas).

Uso:
    python migrate_crm_orcamentos.py            # dry-run (mostra o resumo e desfaz tudo no final)
    python migrate_crm_orcamentos.py --apply     # aplica de verdade (commit)

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

SQL_FILE = os.path.join(os.path.dirname(__file__), "migrations", "008_crm_orcamentos.sql")


def log(msg):
    print(f"[migrate_crm_orcamentos] {msg}")


def aplicar_ddl(cur):
    log(f"Aplicando estrutura de {SQL_FILE} ...")
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        cur.execute(f.read())
    log("Estrutura aplicada (orcamentos, orcamento_itens, pipeline_clientes, tarefas_crm, índices, triggers).")


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
    for tabela in ("orcamentos", "tarefas_crm"):
        cur.execute(
            sql.SQL("ALTER TABLE {} ALTER COLUMN company_id SET DEFAULT %s").format(sql.Identifier(tabela)),
            (company_id,),
        )
    log("orcamentos.company_id e tarefas_crm.company_id agora têm DEFAULT.")


def backfill_pipeline_clientes(cur):
    """Todo cliente que já existia antes deste bloco precisa entrar no pipeline
    na etapa inicial — sem isso, 'um cliente sempre tem uma etapa atual' fica
    falso pros clientes antigos. Idempotente: só insere quem ainda não tem linha."""
    cur.execute("""
        INSERT INTO pipeline_clientes (cliente_id, etapa)
        SELECT c.id, 'novo_cliente'
        FROM clientes c
        WHERE NOT EXISTS (SELECT 1 FROM pipeline_clientes p WHERE p.cliente_id = c.id)
    """)
    log(f"Backfill de pipeline_clientes: {cur.rowcount} cliente(s) existente(s) receberam etapa 'novo_cliente'.")


def imprimir_resumo(cur):
    cur.execute("SELECT COUNT(*) AS total FROM orcamentos")
    total_orcamentos = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM pipeline_clientes")
    total_pipeline = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM clientes")
    total_clientes = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM tarefas_crm")
    total_tarefas = cur.fetchone()["total"]
    log("----- RESUMO -----")
    log(f"orcamentos: {total_orcamentos} linha(s)")
    log(f"tarefas_crm: {total_tarefas} linha(s)")
    log(f"pipeline_clientes: {total_pipeline} linha(s) (clientes totais: {total_clientes})")
    if total_pipeline != total_clientes:
        log("AVISO: pipeline_clientes não cobre todos os clientes — investigar antes de aplicar.")


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
            backfill_pipeline_clientes(cur)
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
