"""
Migration 002 — banco genérico (equipamentos) + multi-tenant (companies).

Uso:
    python migrate_multiempresa.py            # dry-run (mostra o resumo e desfaz tudo no final)
    python migrate_multiempresa.py --apply     # aplica de verdade (commit)

Tudo roda dentro de uma única transação. Qualquer erro no meio de qualquer
passo causa ROLLBACK completo — nenhum estado parcial fica gravado no banco.
Sem --apply, o script sempre termina com ROLLBACK mesmo se tudo correr bem,
só para você conferir o resumo antes de decidir aplicar de verdade.

Requer DATABASE_URL (ou DB_HOST/DB_NAME/DB_USER/DB_PASSWORD) configurado,
igual ao resto do projeto (database.py).
"""

import argparse
import os
import sys

from psycopg2 import sql

from database import get_db_connection

COMPANY_PADRAO_NOME = "Minha Locadora Original"
BRANCH_PADRAO_NOME = "Matriz"
CATEGORIA_PADRAO_NOME = "Motos"

SQL_FILE = os.path.join(os.path.dirname(__file__), "migrations", "002_multiempresa.sql")


def log(msg):
    print(f"[migrate_multiempresa] {msg}")


def aplicar_ddl(cur):
    log(f"Aplicando estrutura de {SQL_FILE} ...")
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        cur.execute(f.read())
    log("Estrutura aplicada (tabelas novas, colunas novas, view de compatibilidade, índices, triggers).")


def obter_ou_criar_company_padrao(cur):
    cur.execute("SELECT id FROM companies WHERE nome = %s", (COMPANY_PADRAO_NOME,))
    row = cur.fetchone()
    if row:
        log(f"Company padrão já existe (id={row['id']}).")
        return row["id"]

    cur.execute(
        "INSERT INTO companies (nome, plano, ativo) VALUES (%s, %s, %s) RETURNING id",
        (COMPANY_PADRAO_NOME, "padrao", True),
    )
    company_id = cur.fetchone()["id"]
    log(f"Company padrão criada (id={company_id}).")
    return company_id


def obter_ou_criar_branch_padrao(cur, company_id):
    cur.execute("SELECT id FROM branches WHERE company_id = %s AND nome = %s", (company_id, BRANCH_PADRAO_NOME))
    row = cur.fetchone()
    if row:
        log(f"Branch padrão já existe (id={row['id']}).")
        return row["id"]

    cur.execute(
        "INSERT INTO branches (company_id, nome) VALUES (%s, %s) RETURNING id",
        (company_id, BRANCH_PADRAO_NOME),
    )
    branch_id = cur.fetchone()["id"]
    log(f"Branch padrão criada (id={branch_id}).")
    return branch_id


def obter_ou_criar_categoria_padrao(cur, company_id):
    cur.execute(
        "SELECT id FROM equipment_categories WHERE company_id = %s AND nome = %s AND categoria_pai_id IS NULL",
        (company_id, CATEGORIA_PADRAO_NOME),
    )
    row = cur.fetchone()
    if row:
        log(f"Categoria padrão já existe (id={row['id']}).")
        return row["id"]

    cur.execute(
        "INSERT INTO equipment_categories (company_id, nome) VALUES (%s, %s) RETURNING id",
        (company_id, CATEGORIA_PADRAO_NOME),
    )
    categoria_id = cur.fetchone()["id"]
    log(f"Categoria padrão '{CATEGORIA_PADRAO_NOME}' criada (id={categoria_id}).")
    return categoria_id


def migrar_motos_para_equipment_items(cur, company_id, branch_id, categoria_id):
    # Reaproveita o mesmo id de motos_legado (evita tabela de tradução de id).
    # status/quantidade_disponivel calculados a partir de locação ativa, não do
    # campo motos.disponivel (que tem um bug pré-existente e não é confiável).
    # "ano" (sem coluna equivalente) vai embutido em descricao como "Ano: N".
    cur.execute(
        """
        INSERT INTO equipment_items (
            id, company_id, branch_id, categoria_id,
            codigo_interno, nome, modelo, foto, descricao,
            status, quantidade_disponivel
        )
        SELECT
            m.id, %(company_id)s, %(branch_id)s, %(categoria_id)s,
            m.placa, m.modelo, m.modelo, m.imagem,
            CASE WHEN m.ano IS NOT NULL THEN 'Ano: ' || m.ano ELSE NULL END,
            CASE WHEN EXISTS (
                SELECT 1 FROM locacoes l WHERE l.moto_id = m.id AND l.cancelado = FALSE
            ) THEN 'alugado' ELSE 'disponivel' END,
            CASE WHEN EXISTS (
                SELECT 1 FROM locacoes l WHERE l.moto_id = m.id AND l.cancelado = FALSE
            ) THEN 0 ELSE 1 END
        FROM motos_legado m
        WHERE NOT EXISTS (SELECT 1 FROM equipment_items ei WHERE ei.id = m.id)
        """,
        {"company_id": company_id, "branch_id": branch_id, "categoria_id": categoria_id},
    )
    log(f"{cur.rowcount} equipamento(s) migrado(s) de motos_legado para equipment_items nesta execução.")

    cur.execute(
        "SELECT setval(pg_get_serial_sequence('equipment_items', 'id'), "
        "COALESCE((SELECT MAX(id) FROM equipment_items), 1))"
    )
    log("Sequence de equipment_items.id ajustada.")


def backfill_company_id(cur, company_id):
    for tabela in ("usuarios", "clientes", "locacoes"):
        cur.execute(
            sql.SQL("UPDATE {} SET company_id = %s WHERE company_id IS NULL").format(sql.Identifier(tabela)),
            (company_id,),
        )
        log(f"{cur.rowcount} linha(s) de {tabela} vinculada(s) à company padrão nesta execução.")

    cur.execute("UPDATE locacoes SET equipment_item_id = moto_id WHERE equipment_item_id IS NULL")
    log(f"{cur.rowcount} locação(ões) com equipment_item_id preenchido nesta execução.")


def travar_constraints(cur, company_id):
    for tabela in ("usuarios", "clientes", "locacoes"):
        cur.execute(
            sql.SQL("ALTER TABLE {} ALTER COLUMN company_id SET DEFAULT %s").format(sql.Identifier(tabela)),
            (company_id,),
        )
        cur.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN company_id SET NOT NULL").format(sql.Identifier(tabela)))

    cur.execute("ALTER TABLE locacoes ALTER COLUMN equipment_item_id SET NOT NULL")
    log("company_id (usuarios/clientes/locacoes) e locacoes.equipment_item_id agora são NOT NULL, com DEFAULT "
        "apontando pra company padrão.")


def imprimir_resumo(cur):
    cur.execute("SELECT COUNT(*) AS total FROM companies")
    total_companies = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM equipment_items")
    total_equipment_items = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM motos_legado")
    total_motos_legado = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM usuarios WHERE company_id IS NULL")
    usuarios_sem_company = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM clientes WHERE company_id IS NULL")
    clientes_sem_company = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM locacoes WHERE company_id IS NULL OR equipment_item_id IS NULL")
    locacoes_incompletas = cur.fetchone()["total"]

    log("----- RESUMO -----")
    log(f"companies: {total_companies}")
    log(f"equipment_items: {total_equipment_items} (motos_legado: {total_motos_legado})")
    log(f"usuarios sem company_id: {usuarios_sem_company}")
    log(f"clientes sem company_id: {clientes_sem_company}")
    log(f"locacoes sem company_id/equipment_item_id: {locacoes_incompletas}")

    if total_equipment_items != total_motos_legado:
        log("ATENÇÃO: total de equipment_items difere de motos_legado — investigar antes de aplicar.")
    if usuarios_sem_company or clientes_sem_company or locacoes_incompletas:
        log("ATENÇÃO: ainda há linhas sem company_id/equipment_item_id — não deveria acontecer neste ponto.")


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

            company_id = obter_ou_criar_company_padrao(cur)
            branch_id = obter_ou_criar_branch_padrao(cur, company_id)
            categoria_id = obter_ou_criar_categoria_padrao(cur, company_id)

            migrar_motos_para_equipment_items(cur, company_id, branch_id, categoria_id)
            backfill_company_id(cur, company_id)
            travar_constraints(cur, company_id)

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
