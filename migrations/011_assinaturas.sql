-- Migration 011: assinatura digital (contrato, checklist de entrega, checklist de devolução).
--
-- Só estrutura (DDL). Idempotente. Aditiva: nenhuma tabela existente muda.
--
-- DEFAULT de company_id fica no migrate_assinaturas.py (depende do id gerado
-- em runtime pela Fase 1), mesmo padrão das migrations anteriores.

CREATE TABLE IF NOT EXISTS assinaturas (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),

    tipo_documento VARCHAR(30) NOT NULL,
    -- locacao_id (tipo_documento='contrato') ou checklist_id (tipo_documento
    -- IN ('checklist_entrega','checklist_devolucao')) -- sem FK direta, pois
    -- aponta pra tabelas diferentes dependendo do tipo.
    documento_id INTEGER NOT NULL,

    assinatura_imagem VARCHAR(255) NOT NULL,
    nome_assinante TEXT NOT NULL,
    data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45),
    user_agent TEXT,

    usuario_id INTEGER REFERENCES usuarios(id),
    cliente_id INTEGER REFERENCES clientes(id),

    -- Uma assinatura nunca é sobrescrita: uma nova substituição vira uma linha
    -- nova, com o motivo registrado e apontando pra qual assinatura ela substitui.
    motivo_substituicao TEXT,
    substitui_assinatura_id INTEGER REFERENCES assinaturas(id),

    CONSTRAINT chk_assinaturas_tipo_documento CHECK (tipo_documento IN (
        'contrato', 'checklist_entrega', 'checklist_devolucao'
    ))
);

CREATE INDEX IF NOT EXISTS idx_assinaturas_company_id ON assinaturas(company_id);
CREATE INDEX IF NOT EXISTS idx_assinaturas_documento ON assinaturas(tipo_documento, documento_id);
