-- Migration 015: chave Asaas por empresa (multi-tenant), substitui a
-- dependência de uma única ASAAS_API_KEY global no Render.
--
-- Só estrutura (DDL). Idempotente. Aditiva.
-- Mesmo padrão de config_multas (migration 006): uma linha por empresa,
-- upsert via ON CONFLICT (company_id).

CREATE TABLE IF NOT EXISTS config_asaas (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL UNIQUE REFERENCES companies(id),

    api_key_cifrada TEXT,
    webhook_secret_cifrado TEXT,
    ambiente VARCHAR(20) NOT NULL DEFAULT 'sandbox',
    ativo BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_config_asaas_ambiente CHECK (ambiente IN ('sandbox', 'producao'))
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_config_asaas_updated') THEN
        CREATE TRIGGER trg_config_asaas_updated
        BEFORE UPDATE ON config_asaas
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END$$;
