"""
Migration 010 — super admin da plataforma + planos SaaS.

Uso:
    python migrate_saas_admin.py            # dry-run (mostra o resumo e desfaz tudo no final)
    python migrate_saas_admin.py --apply     # aplica de verdade (commit)

Mesma lógica de segurança dos scripts anteriores: tudo numa única transação,
erro em qualquer passo causa ROLLBACK completo, sem --apply sempre termina
em ROLLBACK mesmo se der tudo certo.
"""

import argparse
import os
import sys

from database import get_db_connection

COMPANY_PADRAO_NOME = "Minha Locadora Original"
ADMIN_BOOTSTRAP_USERNAME = "admin"

SQL_FILE = os.path.join(os.path.dirname(__file__), "migrations", "010_saas_admin.sql")


def log(msg):
    print(f"[migrate_saas_admin] {msg}")


def aplicar_ddl(cur):
    log(f"Aplicando estrutura de {SQL_FILE} ...")
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        cur.execute(f.read())
    log("Estrutura aplicada (companies: status/limites/trial/bloqueio, usuarios.eh_admin_plataforma).")


def zerar_limites_company_padrao(cur):
    """A company original não deve ficar retroativamente restrita por este bloco."""
    cur.execute("""
        UPDATE companies SET limite_usuarios=NULL, limite_equipamentos=NULL, limite_filiais=NULL
        WHERE nome=%s
        RETURNING id
    """, (COMPANY_PADRAO_NOME,))
    row = cur.fetchone()
    if row:
        log(f"Limites da company padrão (id={row['id']}) zerados (sem limite).")
    else:
        log(f"AVISO: company padrão '{COMPANY_PADRAO_NOME}' não encontrada — nada a zerar.")


def marcar_admin_bootstrap(cur):
    """Sem isso, /admin-plataforma fica inacessível até alguém rodar SQL manual."""
    cur.execute("""
        UPDATE usuarios SET eh_admin_plataforma=TRUE WHERE username=%s
        RETURNING id
    """, (ADMIN_BOOTSTRAP_USERNAME,))
    row = cur.fetchone()
    if row:
        log(f"Usuário '{ADMIN_BOOTSTRAP_USERNAME}' (id={row['id']}) marcado como eh_admin_plataforma=TRUE.")
    else:
        log(f"AVISO: usuário '{ADMIN_BOOTSTRAP_USERNAME}' não encontrado — nenhum admin de plataforma foi criado.")


def imprimir_resumo(cur):
    cur.execute("SELECT id, nome, plano, status, limite_usuarios, limite_equipamentos, limite_filiais FROM companies ORDER BY id")
    companies = cur.fetchall()
    cur.execute("SELECT id, username FROM usuarios WHERE eh_admin_plataforma=TRUE")
    admins_plataforma = cur.fetchall()
    log("----- RESUMO -----")
    for c in companies:
        log(f"company id={c['id']} nome={c['nome']!r} plano={c['plano']!r} status={c['status']!r} "
            f"limites(usu/equip/fil)={c['limite_usuarios']}/{c['limite_equipamentos']}/{c['limite_filiais']}")
    log(f"admins de plataforma: {[(a['id'], a['username']) for a in admins_plataforma]}")


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
            zerar_limites_company_padrao(cur)
            marcar_admin_bootstrap(cur)
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
