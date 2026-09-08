"""
Migration 022 -- cria company_modulos (licenciamento por modulo, Fase 4) e
"adota" (grandfather) as empresas que ja existiam ANTES do licenciamento
existir: elas ganham status 'ativo' automatico nos modulos que ja tinham
acesso de graca (locacoes, financeiro, crm, manutencoes, entregas,
orcamentos, relatorios, assistente), pra ninguem ser bloqueado do dia
pra noite numa empresa que ja estava rodando em producao.

Equipamentos/veiculos/imoveis ficam DE FORA do backfill de proposito --
ainda nao tem o filtro por categoria implementado (compartilham a mesma
tela/tabela), entao ainda nao sao gateados em nenhuma rota.

Empresas NOVAS (criadas depois desta migration) nao ganham nada de graca:
precisam passar pelo fluxo de trial/assinatura (ainda a implementar) pra
cada modulo.

Uso:
    python migrate_company_modulos.py            # dry-run
    python migrate_company_modulos.py --apply     # aplica de verdade (commit)
"""

import argparse
import os
import sys

from database import get_db_connection

SQL_FILE = os.path.join(os.path.dirname(__file__), "migrations", "022_company_modulos.sql")

MODULOS_GRANDFATHER = (
    "locacoes", "financeiro", "crm", "manutencoes",
    "entregas", "orcamentos", "relatorios", "assistente",
)


def log(msg):
    print(f"[migrate_company_modulos] {msg}")


def aplicar_ddl(cur):
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        cur.execute(f.read())
    log("Tabela company_modulos criada (se ainda nao existia).")


def grandfather_empresas_existentes(cur):
    cur.execute("SELECT id, nome FROM companies")
    empresas = cur.fetchall()
    total_linhas = 0
    for empresa in empresas:
        for modulo in MODULOS_GRANDFATHER:
            cur.execute("""
                INSERT INTO company_modulos (company_id, modulo, status)
                VALUES (%s, %s, 'ativo')
                ON CONFLICT (company_id, modulo) DO NOTHING
            """, (empresa["id"], modulo))
            total_linhas += cur.rowcount
        log(f"Empresa '{empresa['nome']}' (id={empresa['id']}): adotada com status 'ativo' em {len(MODULOS_GRANDFATHER)} modulos.")
    log(f"Total de linhas inseridas: {total_linhas}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Grava de verdade (COMMIT).")
    args = parser.parse_args()

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        try:
            aplicar_ddl(cur)
            grandfather_empresas_existentes(cur)
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
