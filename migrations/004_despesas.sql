-- Migration 004: módulo financeiro — tabela de despesas (contas a pagar).
--
-- Só estrutura (DDL). Idempotente. Aditiva: não toca em locacoes, boletos,
-- nem em nenhuma tabela usada pelo fluxo de pagamento Asaas existente.
--
-- DEFAULT de company_id fica no migrate_despesas.py (depende do id gerado
-- em runtime pela Fase 1), mesmo padrão das migrations anteriores.

CREATE TABLE IF NOT EXISTS despesas (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),

    categoria VARCHAR(20) NOT NULL,
    descricao TEXT NOT NULL,
    valor NUMERIC(12,2) NOT NULL,
    data_vencimento DATE NOT NULL,
    data_pagamento DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'pendente',
    fornecedor TEXT,
    forma_pagamento VARCHAR(50),
    observacoes TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_despesas_categoria CHECK (categoria IN (
        'manutencao', 'fornecedor', 'funcionario', 'energia',
        'aluguel', 'marketing', 'imposto', 'outra'
    )),
    CONSTRAINT chk_despesas_status CHECK (status IN ('pendente', 'pago', 'atrasado')),
    CONSTRAINT chk_despesas_valor CHECK (valor >= 0)
);

CREATE INDEX IF NOT EXISTS idx_despesas_company_id ON despesas(company_id);
CREATE INDEX IF NOT EXISTS idx_despesas_status ON despesas(status);
CREATE INDEX IF NOT EXISTS idx_despesas_data_vencimento ON despesas(data_vencimento);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_despesas_updated') THEN
        CREATE TRIGGER trg_despesas_updated
        BEFORE UPDATE ON despesas
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END$$;
