"""
Migration 012 — log de auditoria genérico (usado pela tela de QR Code dos
equipamentos neste bloco, reaproveitável por outros blocos depois).

Uso:
    python migrate_auditoria.py            # dry-run (mostra o resumo e desfaz tudo no final)
    python migrate_auditoria.py --apply     # aplica de verdade (commit)

Mesma lógica de segurança dos scripts anteriores: tudo numa única transação,
erro em qualquer passo causa ROLLBACK completo, sem --apply sempre termina
em ROLLBACK mesmo se der tudo certo.
"""

import argparse
import os
import sys

from database import get_db_connection

SQL_FILE = os.path.join(os.path.dirname(__file__), "migrations", "012_auditoria.sql")


def log(msg):
    print(f"[migrate_auditoria] {msg}")


def aplicar_ddl(cur):
    log(f"Aplicando estrutura de {SQL_FILE} ...")
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        cur.execute(f.read())
    log("Estrutura aplicada (auditoria, índices).")


def buscar_company_padrao(cur):
    cur.execute("SELECT id FROM companies WHERE nome = %s", ("Minha Locadora Original",))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(
            "Company padrão 'Minha Locadora Original' não encontrada — rode migrate_multiempresa.py "
            "--apply (Fase 1) antes deste script."
        )
    log(f"Company padrão encontrada (id={row['id']}).")
    return row["id"]


def definir_default_company(cur, company_id):
    cur.execute("ALTER TABLE auditoria ALTER COLUMN company_id SET DEFAULT %s", (company_id,))
    log("auditoria.company_id agora tem DEFAULT.")


def imprimir_resumo(cur):
    cur.execute("SELECT COUNT(*) AS total FROM auditoria")
    log("----- RESUMO -----")
    log(f"auditoria: {cur.fetchone()['total']} linha(s)")


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
            definir_default_company(cur, company_id)
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
