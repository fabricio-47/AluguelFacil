-- Migration 012: log de auditoria genérico + QR Code nos equipamentos.
--
-- Só estrutura (DDL). Idempotente. Aditiva.
--
-- Genérica de propósito (tabela_afetada/registro_id) pra ser reaproveitada
-- por outros blocos no futuro — este bloco só liga ela na mudança de status
-- de equipamento via tela de QR Code.

CREATE TABLE IF NOT EXISTS auditoria (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    usuario_id INTEGER REFERENCES usuarios(id),

    acao VARCHAR(50) NOT NULL,
    tabela_afetada VARCHAR(50) NOT NULL,
    registro_id INTEGER NOT NULL,
    valores_antes JSONB,
    valores_depois JSONB,

    data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_auditoria_company_id ON auditoria(company_id);
CREATE INDEX IF NOT EXISTS idx_auditoria_registro ON auditoria(tabela_afetada, registro_id);
