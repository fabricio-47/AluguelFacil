-- Migration 009: catálogo online (slug de company) + portal do cliente (senha).
--
-- Só estrutura (DDL). Idempotente. Aditiva: nenhuma tabela existente perde coluna.
--
-- O backfill do slug de cada company (a partir do nome) fica no
-- migrate_catalogo_portal.py — precisa de lógica por linha (slugify +
-- resolução de colisão), não é DDL puro.

ALTER TABLE companies ADD COLUMN IF NOT EXISTS slug VARCHAR(100);
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_companies_slug'
    ) THEN
        ALTER TABLE companies ADD CONSTRAINT uq_companies_slug UNIQUE (slug);
    END IF;
END$$;

-- NULL = cliente ainda não fez o primeiro acesso ao portal.
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS senha TEXT;

CREATE INDEX IF NOT EXISTS idx_companies_slug ON companies(slug);
