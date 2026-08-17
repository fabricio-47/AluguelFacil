"""
Migration 003 — completa equipment_items pro backend de motos_routes.py poder
trocar de vez a view "motos" por equipment_items (documento_arquivo, ano,
galeria de imagens, DEFAULT de company/branch/categoria).

Uso:
    python migrate_equipamentos_backend.py            # dry-run (mostra o resumo e desfaz tudo no final)
    python migrate_equipamentos_backend.py --apply     # aplica de verdade (commit)

Pré-requisito: migrations/002_multiempresa.sql (Fase 1) já aplicada — este
script depende da company/branch/categoria padrão que ela criou.

Mesma lógica de segurança do migrate_multiempresa.py: tudo numa única
transação, erro em qualquer passo causa ROLLBACK completo, sem --apply
sempre termina em ROLLBACK mesmo se der tudo certo.
"""

import argparse
import os
import sys

from psycopg2 import sql

from database import get_db_connection

COMPANY_PADRAO_NOME = "Minha Locadora Original"
BRANCH_PADRAO_NOME = "Matriz"
CATEGORIA_PADRAO_NOME = "Motos"

SQL_FILE = os.path.join(os.path.dirname(__file__), "migrations", "003_equipamentos_backend.sql")


def log(msg):
    print(f"[migrate_equipamentos_backend] {msg}")


def aplicar_ddl(cur):
    log(f"Aplicando estrutura de {SQL_FILE} ...")
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        cur.execute(f.read())
    log("Estrutura aplicada (documento_arquivo, ano, equipment_item_imagens, locacoes.moto_id nullable).")


def buscar_ids_padrao(cur):
    cur.execute("SELECT id FROM companies WHERE nome = %s", (COMPANY_PADRAO_NOME,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(
            f"Company padrão '{COMPANY_PADRAO_NOME}' não encontrada — rode migrate_multiempresa.py "
            f"--apply (Fase 1) antes deste script."
        )
    company_id = row["id"]

    cur.execute("SELECT id FROM branches WHERE company_id = %s AND nome = %s", (company_id, BRANCH_PADRAO_NOME))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"Branch padrão '{BRANCH_PADRAO_NOME}' não encontrada.")
    branch_id = row["id"]

    cur.execute(
        "SELECT id FROM equipment_categories WHERE company_id = %s AND nome = %s AND categoria_pai_id IS NULL",
        (company_id, CATEGORIA_PADRAO_NOME),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"Categoria padrão '{CATEGORIA_PADRAO_NOME}' não encontrada.")
    categoria_id = row["id"]

    log(f"IDs padrão: company={company_id}, branch={branch_id}, categoria={categoria_id}.")
    return company_id, branch_id, categoria_id


def definir_defaults_equipment_items(cur, company_id, branch_id, categoria_id):
    for coluna, valor in (("company_id", company_id), ("branch_id", branch_id), ("categoria_id", categoria_id)):
        cur.execute(
            sql.SQL("ALTER TABLE equipment_items ALTER COLUMN {} SET DEFAULT %s").format(sql.Identifier(coluna)),
            (valor,),
        )
    log("equipment_items.company_id/branch_id/categoria_id agora têm DEFAULT — INSERTs que não "
        "mencionam essas colunas (como o de motos_routes.py) continuam funcionando.")


def backfill_documento_arquivo(cur):
    cur.execute(
        """
        UPDATE equipment_items ei
        SET documento_arquivo = ml.documento_arquivo
        FROM motos_legado ml
        WHERE ei.id = ml.id AND ei.documento_arquivo IS NULL AND ml.documento_arquivo IS NOT NULL
        """
    )
    log(f"{cur.rowcount} equipment_items.documento_arquivo preenchido(s) a partir de motos_legado.")


def backfill_imagens(cur):
    cur.execute(
        """
        INSERT INTO equipment_item_imagens (equipment_item_id, arquivo, data_upload)
        SELECT mi.moto_id, mi.arquivo, mi.data_upload
        FROM moto_imagens mi
        WHERE NOT EXISTS (
            SELECT 1 FROM equipment_item_imagens eii
            WHERE eii.equipment_item_id = mi.moto_id AND eii.arquivo = mi.arquivo
        )
        """
    )
    log(f"{cur.rowcount} imagem(ns) copiada(s) de moto_imagens para equipment_item_imagens.")


def backfill_ano(cur):
    cur.execute(
        r"""
        UPDATE equipment_items
        SET ano = substring(descricao from 'Ano: (\d+)')::INTEGER
        WHERE ano IS NULL AND descricao ~ 'Ano: \d+'
        """
    )
    log(f"{cur.rowcount} equipment_items.ano extraído(s) de dentro de descricao.")


def imprimir_resumo(cur):
    cur.execute("SELECT COUNT(*) AS total FROM equipment_items")
    total_items = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM equipment_items WHERE documento_arquivo IS NOT NULL")
    com_documento = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM equipment_item_imagens")
    total_imagens = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM equipment_items WHERE ano IS NOT NULL")
    com_ano = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM locacoes WHERE moto_id IS NULL")
    locacoes_sem_moto_id = cur.fetchone()["total"]

    log("----- RESUMO -----")
    log(f"equipment_items: {total_items} (com documento: {com_documento}, com ano: {com_ano})")
    log(f"equipment_item_imagens: {total_imagens}")
    log(f"locacoes com moto_id NULL (esperado: só as criadas depois desta fase): {locacoes_sem_moto_id}")


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
            company_id, branch_id, categoria_id = buscar_ids_padrao(cur)
            definir_defaults_equipment_items(cur, company_id, branch_id, categoria_id)
            backfill_documento_arquivo(cur)
            backfill_imagens(cur)
            backfill_ano(cur)
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
