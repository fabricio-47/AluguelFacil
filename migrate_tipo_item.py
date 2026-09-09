"""Migracao 025: adiciona tipo_item em equipment_items + grandfathering da
empresa original (Minha Locadora Original) com os 3 modulos de estoque ativos,
pra nao travar ninguem quando o gate por modulo entrar em vigor.

Uso:
    python3 migrate_tipo_item.py            # dry-run (mostra o que faria, sem commitar)
    python3 migrate_tipo_item.py --apply    # aplica de verdade
"""
import argparse
import datetime as dt
import os
import sys

import psycopg2
import psycopg2.extras


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Aplica de verdade (default: dry-run com rollback).")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Defina DATABASE_URL no ambiente.", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(database_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    with open("migrations/025_tipo_item.sql", "r", encoding="utf-8") as f:
        sql = f.read()
    cur.execute(sql)
    print("DDL de migrations/025_tipo_item.sql aplicado.")

    cur.execute("SELECT tipo_item, COUNT(*) AS total FROM equipment_items GROUP BY tipo_item")
    print("Distribuicao por tipo apos backfill:", cur.fetchall())

    # Grandfathering: empresa original (id=1) ganha os 3 modulos de estoque como 'ativo'.
    cur.execute("SELECT id, nome FROM companies WHERE id = 1")
    empresa = cur.fetchone()
    if empresa:
        print("Grandfathering para:", dict(empresa))
        for slug in ("equipamentos", "veiculos", "imoveis"):
            cur.execute("""
                INSERT INTO company_modulos (company_id, modulo, status, trial_termina_em)
                VALUES (1, %s, 'ativo', NULL)
                ON CONFLICT (company_id, modulo) DO UPDATE SET status='ativo', trial_termina_em=NULL
            """, (slug,))
        print("Modulos equipamentos/veiculos/imoveis ativados para company_id=1.")
    else:
        print("AVISO: company_id=1 nao encontrada, pulando grandfathering.")

    if args.apply:
        conn.commit()
        print("APLICADO (commit).")
    else:
        conn.rollback()
        print("DRY-RUN (rollback) -- rode com --apply pra aplicar de verdade.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
