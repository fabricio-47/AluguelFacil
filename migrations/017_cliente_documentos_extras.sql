-- Migration 017: anexos adicionais de documentos do cliente (múltiplos
-- arquivos por cliente, com tipo e data de upload), separado dos 4 slots
-- fixos já existentes (doc_frente_arquivo, doc_verso_arquivo,
-- comprovante_residencia_arquivo, foto_cliente_arquivo) — esses continuam
-- intactos e não são afetados por esta migration.

CREATE TABLE IF NOT EXISTS cliente_documentos (
    id SERIAL PRIMARY KEY,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    tipo VARCHAR(50) NOT NULL,
    tipo_outro VARCHAR(255),
    arquivo TEXT NOT NULL,
    data_upload TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cliente_documentos_cliente_id ON cliente_documentos(cliente_id);
