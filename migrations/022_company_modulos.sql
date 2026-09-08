-- Migration 022: licenciamento por modulo (base da Fase 4).
--
-- Uma linha por (empresa, modulo). A AUSENCIA de linha significa "nunca
-- contratou esse modulo" -- bloqueado por padrao para empresas novas.
-- Nunca ha DELETE nem troca de modulo: uma vez criada a linha, so o
-- status muda (trial -> ativo -> bloqueado). Cliente que quiser outro
-- modulo ganha uma linha NOVA, nunca substitui uma existente.

CREATE TABLE IF NOT EXISTS company_modulos (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    modulo VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'trial',
    trial_termina_em TIMESTAMP,
    asaas_subscription_id VARCHAR(255),
    ativado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(company_id, modulo),
    CONSTRAINT chk_company_modulos_status CHECK (status IN ('trial', 'ativo', 'bloqueado', 'cancelado')),
    CONSTRAINT chk_company_modulos_modulo CHECK (modulo IN (
        'equipamentos', 'veiculos', 'imoveis', 'locacoes', 'financeiro', 'crm',
        'manutencoes', 'entregas', 'orcamentos', 'relatorios', 'assistente'
    ))
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_company_modulos_updated') THEN
        CREATE TRIGGER trg_company_modulos_updated
        BEFORE UPDATE ON company_modulos
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END$$;
