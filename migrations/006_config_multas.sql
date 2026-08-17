-- Migration 006: configuração de multas por atraso + campo de fechamento no checklist.
--
-- Só estrutura (DDL). Idempotente. Aditiva.
--
-- DEFAULT de company_id fica no migrate_config_multas.py (depende do id
-- gerado em runtime pela Fase 1), mesmo padrão das migrations anteriores.

CREATE TABLE IF NOT EXISTS config_multas (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL UNIQUE REFERENCES companies(id),

    tipo VARCHAR(20) NOT NULL,
    valor_fixo NUMERIC(12,2),
    percentual NUMERIC(5,2),
    juros_dia_percentual NUMERIC(5,2),
    ativo BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_config_multas_tipo CHECK (tipo IN ('fixa', 'percentual', 'nova_diaria'))
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_config_multas_updated') THEN
        CREATE TRIGGER trg_config_multas_updated
        BEFORE UPDATE ON config_multas
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END$$;

-- Retrato definitivo do atraso/multa no momento do fechamento (checklist de
-- devolução), calculado com a data_fim planejada antes dela ser sobrescrita
-- pelo cancelamento.
ALTER TABLE checklists ADD COLUMN IF NOT EXISTS dias_atraso_final INTEGER;
ALTER TABLE checklists ADD COLUMN IF NOT EXISTS valor_multa_final NUMERIC(12,2);
