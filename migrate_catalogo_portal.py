"""
Migration 009 — catálogo online (slug de company) + portal do cliente (senha).

Uso:
    python migrate_catalogo_portal.py            # dry-run (mostra o resumo e desfaz tudo no final)
    python migrate_catalogo_portal.py --apply     # aplica de verdade (commit)

Mesma lógica de segurança dos scripts anteriores: tudo numa única transação,
erro em qualquer passo causa ROLLBACK completo, sem --apply sempre termina
em ROLLBACK mesmo se der tudo certo.
"""

import argparse
import os
import sys

from database import get_db_connection
from text_utils import slugify

SQL_FILE = os.path.join(os.path.dirname(__file__), "migrations", "009_catalogo_portal.sql")


def log(msg):
    print(f"[migrate_catalogo_portal] {msg}")


def aplicar_ddl(cur):
    log(f"Aplicando estrutura de {SQL_FILE} ...")
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        cur.execute(f.read())
    log("Estrutura aplicada (companies.slug, clientes.senha, índice).")


def backfill_slugs(cur):
    """Gera um slug único pra cada company que ainda não tem um."""
    cur.execute("SELECT id, nome FROM companies WHERE slug IS NULL ORDER BY id ASC")
    pendentes = cur.fetchall()

    cur.execute("SELECT slug FROM companies WHERE slug IS NOT NULL")
    usados = {r["slug"] for r in cur.fetchall()}

    for company in pendentes:
        base = slugify(company["nome"])
        slug = base
        contador = 2
        while slug in usados:
            slug = f"{base}-{contador}"
            contador += 1
        usados.add(slug)
        cur.execute("UPDATE companies SET slug=%s WHERE id=%s", (slug, company["id"]))
        log(f"company id={company['id']} ({company['nome']!r}) -> slug={slug!r}")

    log(f"Backfill de slug: {len(pendentes)} company(ies) atualizada(s).")


def imprimir_resumo(cur):
    cur.execute("SELECT id, nome, slug FROM companies ORDER BY id ASC")
    companies = cur.fetchall()
    cur.execute("SELECT COUNT(*) AS total FROM clientes WHERE senha IS NOT NULL")
    total_com_senha = cur.fetchone()["total"]
    log("----- RESUMO -----")
    for c in companies:
        log(f"company id={c['id']} nome={c['nome']!r} slug={c['slug']!r}")
    log(f"clientes com senha já definida: {total_com_senha}")


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
            backfill_slugs(cur)
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
